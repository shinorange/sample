import lzma
import struct
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from xauforecast.backtest import backtest
from xauforecast.core import FeatureSet, Grid, estimate_profile
from xauforecast.data import load_csv, localize_to_utc, save_csv, synthetic
from xauforecast.model import QLEVELS, Forecaster
from xauforecast.sources import _decode_candles, _decode_ticks
from xauforecast.stats import collect_stats


@pytest.fixture(scope="module")
def syn():
    # seed=0: 150 日で +6%（典型的）。2σ 級のトレンドが出るシード（例: seed=3 は +31%）だと、
    # 50 日程度の検証期間では中央区間のカバー率がトレンドに支配され、較正の検査にならない。
    return synthetic(days=150, seed=0)


FAST = dict(gbm_rows=6000, knn_k=50)


@pytest.fixture(scope="module")
def fitted(syn):
    g = Grid(syn)
    m = Forecaster(**FAST)
    fs = m.fit(g)
    return m, g, fs


# --------------------------------------------------------------------- data
def test_timezones():
    idx = pd.DatetimeIndex(["2025-07-01 00:00", "2025-01-15 00:00"])
    # NY+7: サーバー 0:00 = NY 17:00 = 夏 21:00 UTC / 冬 22:00 UTC
    u = localize_to_utc(idx, "NY+7")
    assert [t.hour for t in u] == [21, 22]
    assert localize_to_utc(idx, "UTC+2")[0].hour == 22
    assert localize_to_utc(idx, "Asia/Tokyo")[0].hour == 15


def test_load_formats(tmp_path):
    mt5 = "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n" \
          "2025.03.03\t10:00:00\t2860.1\t2861.0\t2859.5\t2860.7\t120\t0\t15\n" \
          "2025.03.03\t10:01:00\t2860.7\t2862.0\t2860.2\t2861.9\t98\t0\t15\n"
    p = tmp_path / "mt5.csv"
    p.write_text(mt5)
    df = load_csv(p, tz="NY+7")
    assert len(df) == 2 and df.index[0] == pd.Timestamp("2025-03-03 08:00", tz="UTC")
    assert df["volume"].iloc[0] == 120

    hd = "20250303 100000;2860.1;2861.0;2859.5;2860.7;0\n20250303 100100;2860.7;2862.0;2860.2;2861.9;0\n"
    p = tmp_path / "hd.csv"
    p.write_text(hd)
    df = load_csv(p)
    assert df.index[0] == pd.Timestamp("2025-03-03 15:00", tz="UTC")  # EST 固定 = UTC-5

    duk = "Gmt time,Open,High,Low,Close,Volume\n03.03.2025 10:00:00.000,2860.1,2861.0,2859.5,2860.7,1.2\n"
    p = tmp_path / "duk.csv"
    p.write_text(duk)
    df = load_csv(p)
    assert df.index[0] == pd.Timestamp("2025-03-03 10:00", tz="UTC")


def test_save_roundtrip(tmp_path, syn):
    p = tmp_path / "x.csv.gz"
    save_csv(syn.iloc[:1000], p)
    back = load_csv(p)
    assert len(back) == 1000
    np.testing.assert_allclose(back["close"].to_numpy(), syn["close"].iloc[:1000].to_numpy(), rtol=1e-8)


def test_dukascopy_decoding():
    day = datetime(2025, 3, 3, tzinfo=timezone.utc)
    recs = b"".join(struct.pack(">5if", 60 * i, 2860100 + i, 2860500 + i, 2859900 + i, 2860900 + i, 1.5) for i in range(3))
    df = _decode_candles(lzma.compress(recs, format=lzma.FORMAT_ALONE), day, 1000.0)
    assert len(df) == 3
    assert df.index[1] == pd.Timestamp("2025-03-03 00:01", tz="UTC")
    assert df["open"].iloc[0] == pytest.approx(2860.1) and df["close"].iloc[0] == pytest.approx(2860.5)
    assert df["high"].iloc[0] == pytest.approx(2860.9) and df["low"].iloc[0] == pytest.approx(2859.9)

    hour = datetime(2025, 3, 3, 10, tzinfo=timezone.utc)
    ticks = b"".join(struct.pack(">3I2f", ms, 2860300 + k, 2860100 + k, 1.0, 1.0)
                     for k, ms in enumerate([500, 30_000, 59_000, 61_000]))
    t = _decode_ticks(lzma.compress(ticks, format=lzma.FORMAT_ALONE), hour, 1000.0)
    assert len(t) == 2 and t["volume"].iloc[0] == 3
    assert t["open"].iloc[0] == pytest.approx(2860.2) and t["close"].iloc[0] == pytest.approx(2860.204)


# --------------------------------------------------------------------- model
def test_features_have_no_lookahead(syn):
    g1 = Grid(syn)
    cut = int(np.where(g1.is_open[:120_000])[0][-1])  # 取引のある分で切る
    f = estimate_profile(g1, end=cut)
    fs1 = FeatureSet(g1, f, end=cut)
    g2 = Grid(syn[syn.index <= g1.idx[cut]])
    fs2 = FeatureSet(g2, f, end=cut)
    assert len(fs1.names) > 120
    pos = np.r_[np.arange(cut - 5000, cut, 97), cut]
    # 未来のデータを削っても、過去時点の特徴量はすべて一致する（先読みなし）
    a, b = fs1.matrix(pos), fs2.matrix(pos)
    bad = [n for j, n in enumerate(fs1.names) if not np.allclose(a[:, j], b[:, j], rtol=1e-5, atol=1e-6)]
    assert not bad, bad
    np.testing.assert_allclose(fs1.har_matrix(pos), fs2.har_matrix(pos), rtol=1e-6, atol=1e-9)


def test_every_feature_has_label(fitted):
    from xauforecast.features import feature_label

    m, _, _ = fitted
    assert [n for n in m.feature_names if feature_label(n) == n] == []


def test_forecast_shape_and_monotone(fitted):
    m, g, fs = fitted
    pos = g.pos_of("2025-05-14 14:00")
    fc = m.forecast(g, fs, pos=pos, n_paths=500)
    assert len(fc["horizons"]) == 10
    sig = [h["sigma_usd"] for h in fc["horizons"]]
    assert all(b >= a * 0.95 for a, b in zip(sig, sig[1:]))  # 平日昼間は期間とともに σ が増える
    for h in fc["horizons"]:
        q = [h["quantiles"][f"{x:g}"] for x in QLEVELS]
        assert all(b >= a for a, b in zip(q, q[1:]))
        assert 0.3 < h["p_up"] < 0.7
    for t in fc["touch"]:
        assert t["p_up_60"] <= t["p_up_240"] + 1e-9 <= t["p_up_1440"] + 2e-9
    ex = fc["explain"]
    assert ex["feature_stats"] and ex["analogs"]["by_horizon"] and len(ex["model_summary"]) == 10
    from xauforecast import report

    assert "予測の根拠" in report.forecast_text(fc) and "類似局面" in report.forecast_html(fc)


def test_weekend_has_no_volatility(fitted):
    m, g, fs = fitted
    ny = g.idx.tz_convert("America/New_York")
    fri = np.where((ny.dayofweek == 4) & (ny.hour == 16) & (ny.minute == 50) & g.is_open)[0][-1]
    wed = np.where((ny.dayofweek == 2) & (ny.hour == 16) & (ny.minute == 50) & g.is_open)[0][-1]
    pr = m.predict_batch(fs, np.array([fri, wed]))
    # 金 16:50 からの 24 時間で取引があるのは 17:00 までの 10 分だけ → 60 分先とほぼ同じ σ
    assert pr[1440]["sigma"][0] == pytest.approx(pr[60]["sigma"][0], rel=0.5)
    # 平日（水曜）の 24 時間 σ よりずっと小さい
    assert pr[1440]["sigma"][0] < 0.3 * pr[1440]["sigma"][1]


def test_save_load(tmp_path, fitted):
    m, g, fs = fitted
    p = tmp_path / "m.pkl"
    m.save(p)
    m2 = Forecaster.load(p)
    a = m.predict_batch(fs, np.array([g.n - 100]))[60]["sigma"]
    b = m2.predict_batch(fs, np.array([g.n - 100]))[60]["sigma"]
    np.testing.assert_allclose(a, b)


def test_backtest_calibration(syn):
    r = backtest(syn, n_folds=2, test_frac=0.35, eval_stride=30, touch_origins=0, verbose=False, **FAST)
    # ボラ局面が数日続くため、短い検証期間の独立サンプルは少ない（数十日）。
    # カバー率は期間ごとに数ポイント揺れるので、全ホライズン平均と、個別の緩い範囲で確認する。
    c90 = [h["cover_90"] for h in r["horizons"]]
    c50 = [h["cover_50"] for h in r["horizons"]]
    assert 0.84 < np.mean(c90) < 0.95, c90
    assert 0.42 < np.mean(c50) < 0.58, c50
    assert all(0.76 < c < 0.98 for c in c90), c90
    # 季節性 + クラスタリングを使うボラ予測は無条件ボラより良いはず
    assert np.mean([h["qlike_skill_pct"] for h in r["horizons"]]) > 10


def test_stats_run(syn):
    st = collect_stats(syn.iloc[-60_000:], verbose=False)
    errors = {k: v["error"] for k, v in st.items() if isinstance(v, dict) and "error" in v}
    assert not errors, errors
    assert len(st["horizons"]) == 10
    assert st["volatility"]["gjr_garch_5m_deseasonalized"]["persistence"] < 1
    assert 0.9 < st["advanced"]["permutation_entropy"]["1m"] <= 1.0


def test_feature_report(fitted):
    from xauforecast import report

    m, _, _ = fitted
    md = report.features_markdown(m)
    assert "予測力が高い統計量" in md and len(m.feature_ic_table()) == len(m.feature_names)


# --------------------------------------------------------------------- rules
def test_rule_search_rejects_noise_and_finds_planted_edge():
    from xauforecast.rules import search

    # 優位性のないデータでは何も採用しない（偽陽性の抑制）
    # 検証期間（後半 40%）が短いと本物の優位性でも t が足りず不採用になるため、約 1.2 年分を使う
    null = search(synthetic(days=420, seed=11), B=200, verbose=False)
    assert len(null["accepted"]) == 0
    # 既知の優位性（アジアの方向にロンドン序盤が続く）を埋め込むと、そのルールを見つける（検出力）
    res = search(synthetic(days=420, seed=11, edge=0.07), B=200, verbose=False)
    acc = res["accepted"]["rule"].tolist()
    assert any("アジア(18-3時)の方向" in r and "順張り" in r for r in acc), acc[:5]
    assert all(r.startswith("J ") or "アジア" in r for r in acc), acc


def test_simulate_stop_and_target():
    from xauforecast.rules import T, DayData, simulate

    D = 2
    C = np.full((D, T), 100.0)
    H, L = C.copy(), C.copy()
    H[0, 10] = 103.0   # 1 日目: 利確に先に到達
    L[1, 10] = 97.0    # 2 日目: 損切に先に到達
    dd = DayData(pd.DatetimeIndex(["2025-01-06", "2025-01-07"]), C.copy(), H, L, C, np.zeros((D, T)),
                 np.ones((D, T), bool), np.ones(D), np.ones(D), np.ones(D), np.ones(D), np.zeros(D, int), np.zeros(D, bool))
    r = simulate(dd, np.array([5, 5]), np.array([1, 1]), np.array([100.0, 100.0]), np.array([98.0, 98.0]),
                 np.array([102.0, 102.0]), np.array([100, 100]), spread=0.3, slip=0.1)
    assert r["pnl_usd"][0] == pytest.approx(2.0 - 0.3)
    assert r["pnl_usd"][1] == pytest.approx(-2.0 - 0.3 - 0.1)


# --------------------------------------------------------------------- candles
def test_candle_conditions_null_and_planted():
    from xauforecast.candles import analyze

    # 優位性なし: 方向の条件は何も再現しない
    r0 = analyze(synthetic(days=420, seed=7), tfs=(60,), verbose=False)["tfs"][60]
    assert int(r0["hour_direction"]["replicated"].sum()) == 0
    assert int(r0["direction"]["replicated"].sum()) == 0
    # 値幅（上下問わず大きく動く）はボラの統計量で予測できる
    big = r0["single"][(r0["single"].target == "big") & r0["single"]["replicated"]]
    assert (big["group"] == "ボラ").any()
    # 埋め込んだ優位性（アジアの方向にロンドン序盤が続く）は NY 3〜4 時の足で見つかる
    r1 = analyze(synthetic(days=420, seed=7, edge=0.05), tfs=(60,), verbose=False)["tfs"][60]
    hd = r1["hour_direction"]
    rep = hd[hd["replicated"]]
    assert len(rep) > 0 and set(rep["ny_hour"]) <= {3, 4}, rep[["ny_hour", "feature"]].head()
    assert (rep["diff_is"] > 0).all()
