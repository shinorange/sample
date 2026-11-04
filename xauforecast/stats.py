"""XAUUSD 1 分足から収集する統計情報の一式。

collect_stats(df) が返す dict のセクション:
  basic          基本情報（期間、本数、欠損、価格、年率ボラ）
  horizons       1分〜24時間の各ホライズンのリターン分布（モーメント、分位点、裾指数、正規性）
  scaling        分散比検定（Lo-MacKinlay, 不均一分散頑健）、Hurst 指数（スケーリング）
  autocorr       リターン / 絶対リターンの自己相関と Ljung-Box 検定（1分・5分・1時間・日次）
  seasonality    NY 時間別・曜日別・分（毎時何分）別・セッション別・月別・月初月末効果
  top_slots      週内で最もボラが高い時刻（指標発表時刻など）
  time_events    ロンドン・フィキシング、COMEX 開始、NY クローズ等の時刻イベント効果
  nfp            米雇用統計（第1金曜 8:30 NY と推定）前後の値動き
  events         ユーザー指定の経済指標カレンダー（任意）前後の値動き
  volatility     実現ボラ推定量（CC/Parkinson/GK/RS/YZ）、GJR-GARCH、日次 HAR、ボラのボラ
  ranges         ホライズン別の高安レンジ、最大上昇幅/下落幅（MFE/MAE）
  touch          ±x% に h 以内で到達する経験確率、先に上下どちらへ到達するか
  conditional    モメンタム/リバーサル（過去リターン五分位）、RSI、移動平均乖離、ボラ局面、連続陽線・陰線、ラン検定
  sessions       セッション間（アジア→ロンドン→NY）のリターン相関
  gaps           週明け・日次再開ギャップの分布と窓埋め確率
  round_numbers  キリ番（$10/$50/$100）付近での反発/突破の頻度
  volume         ティック出来高とボラの関係、時間帯別出来高
  trend          移動平均との位置関係、最大ドローダウン、直近の騰落
  extremes       最大の 1分 / 1時間 / 1日 変動
  current        現在の状況（ボラの分位、トレンド、RSI 等）
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import optimize, stats as sps

from .core import HORIZONS, NY, Grid, estimate_profile, horizon_label

SESSIONS = {  # NY 時間（時）
    "アジア(18-03 NY)": (18, 3),
    "ロンドン(03-08 NY)": (3, 8),
    "NY午前(08-12 NY)": (8, 12),
    "NY午後(12-17 NY)": (12, 17),
}


def _f(x):
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_clean(v) for v in obj.tolist()]
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    return _f(obj)


def _tstat(x: np.ndarray, overlap: int = 1) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std() == 0:
        return float("nan")
    n_eff = max(len(x) / max(overlap, 1), 2)
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(n_eff)))


def _hill(x: np.ndarray, frac: float = 0.025) -> float:
    x = np.sort(np.abs(x[x != 0]))[::-1]
    k = max(int(len(x) * frac), 10)
    if len(x) <= k + 1:
        return float("nan")
    return float(1.0 / np.mean(np.log(x[:k] / x[k])))


def _acf(x: np.ndarray, lags) -> list[float]:
    x = x - x.mean()
    v = np.dot(x, x)
    return [float(np.dot(x[l:], x[:-l]) / v) if v > 0 else float("nan") for l in lags]


def _ljung_box(x: np.ndarray, m: int) -> tuple[float, float]:
    n = len(x)
    ac = np.array(_acf(x, range(1, m + 1)))
    q = n * (n + 2) * np.sum(ac ** 2 / (n - np.arange(1, m + 1)))
    return float(q), float(sps.chi2.sf(q, m))


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 * up / (up + dn)


def _hour_in(h: np.ndarray, a: int, b: int) -> np.ndarray:
    return (h >= a) & (h < b) if a < b else (h >= a) | (h < b)


# ---------------------------------------------------------------------------
def daily_bars(grid: Grid) -> pd.DataFrame:
    df = grid.df
    ny = df.index.tz_convert(NY)
    td = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)
    g = df.groupby(td)
    d = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                      "close": g["close"].last(), "volume": g["volume"].sum(), "n": g["close"].size()})
    d = d[d["n"] >= 60]
    d.index.name = "trading_day"
    return d


def resample_bars(grid: Grid, rule: str) -> pd.DataFrame:
    df = grid.df
    g = df.resample(rule, label="right", closed="right")
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum()})
    return out.dropna()


# ---------------------------------------------------------------------------
def basic(grid: Grid, daily: pd.DataFrame) -> dict:
    df = grid.df
    dr = np.log(daily["close"]).diff().dropna()
    open_minutes_expected = int(np.sum(_expected_open(grid)))
    return {
        "start_utc": str(df.index[0]), "end_utc": str(df.index[-1]),
        "bars": int(len(df)), "trading_days": int(len(daily)),
        "coverage_vs_expected_open_minutes": len(df) / max(open_minutes_expected, 1),
        "first_price": float(df["close"].iloc[0]), "last_price": float(df["close"].iloc[-1]),
        "min_price": float(df["low"].min()), "max_price": float(df["high"].max()),
        "total_return_pct": float((df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100),
        "annualized_return_pct": float(dr.mean() * 252 * 100),
        "annualized_vol_pct": float(dr.std() * np.sqrt(252) * 100),
        "avg_bars_per_day": float(daily["n"].mean()),
        "zero_return_share_1m": float(np.mean(np.diff(df["close"].to_numpy()) == 0)),
    }


def _expected_open(grid: Grid) -> np.ndarray:
    dow, mod = grid.dow, grid.mod
    closed = (dow == 5) | ((dow == 4) & (mod >= 1020)) | ((dow == 6) & (mod < 1080)) | ((mod >= 1020) & (mod < 1080))
    return ~closed


def horizon_stats(grid: Grid, horizons=HORIZONS) -> list[dict]:
    open_pos = np.where(grid.is_open)[0]
    p0 = grid.close[-1]
    out = []
    for h in horizons:
        stride = max(1, h // 5)
        pos = open_pos[open_pos + h < grid.n][::stride]
        r = grid.logp[pos + h] - grid.logp[pos]
        moving = r != 0
        r_nz = r[moving] if moving.mean() > 0.5 else r
        hi = np.array([0.0])
        qs = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975, 0.99, 0.995]
        qv = np.quantile(r, qs)
        sd = r.std()
        jb = sps.jarque_bera(r_nz[:200000]) if len(r_nz) > 30 else (np.nan, np.nan)
        out.append({
            "h": h, "label": horizon_label(h), "n": int(len(r)),
            "mean_bp": r.mean() * 1e4, "mean_t": _tstat(r, overlap=max(1, h // stride)),
            "std_bp": sd * 1e4, "std_usd_at_last": sd * p0,
            "mean_abs_bp": np.abs(r).mean() * 1e4, "mean_abs_usd_at_last": np.abs(r).mean() * p0,
            "skew": float(sps.skew(r)), "excess_kurtosis": float(sps.kurtosis(r)),
            "p_up": float(np.mean(r > 0)), "p_down": float(np.mean(r < 0)), "p_flat": float(np.mean(r == 0)),
            "p_abs_gt_1sd": float(np.mean(np.abs(r) > sd)), "p_abs_gt_2sd": float(np.mean(np.abs(r) > 2 * sd)),
            "p_abs_gt_3sd": float(np.mean(np.abs(r) > 3 * sd)), "p_abs_gt_4sd": float(np.mean(np.abs(r) > 4 * sd)),
            "quantiles_bp": {f"{q:g}": v * 1e4 for q, v in zip(qs, qv)},
            "quantiles_usd_at_last": {f"{q:g}": float(p0 * np.expm1(v)) for q, v in zip(qs, qv)},
            "hill_tail_index": _hill(r), "jarque_bera": float(jb[0]), "jarque_bera_p": float(jb[1]),
        })
    return out


def scaling(grid: Grid, hstats: list[dict]) -> dict:
    hs = np.array([d["h"] for d in hstats], dtype=float)
    sd = np.array([d["std_bp"] for d in hstats])
    slope = np.polyfit(np.log(hs), np.log(sd), 1)[0]
    slope_long = np.polyfit(np.log(hs[hs >= 30]), np.log(sd[hs >= 30]), 1)[0] if (hs >= 30).sum() >= 3 else np.nan
    # Lo-MacKinlay 分散比（取引足ベース、不均一分散頑健 z*）
    r = np.diff(np.log(grid.df["close"].to_numpy()))
    r = r[-400_000:]
    mu = r.mean()
    e = r - mu
    e2 = e ** 2
    var1 = e2.mean()
    vr = []
    c = np.concatenate([[0.0], np.cumsum(r)])
    for q in (2, 5, 15, 60, 240, 1440):
        if len(r) < 5 * q:
            continue
        rq = c[q:] - c[:-q]
        varq = np.mean((rq - q * mu) ** 2) / q
        v = varq / var1
        theta = 0.0
        den = e2.sum() ** 2
        for j in range(1, q):
            delta = np.dot(e2[j:], e2[:-j]) / den * len(r)
            theta += (2 * (q - j) / q) ** 2 * delta
        z = (v - 1) * np.sqrt(len(r)) / np.sqrt(theta) if theta > 0 else np.nan
        vr.append({"q_bars": q, "variance_ratio": v, "z_robust": z, "p_value": 2 * sps.norm.sf(abs(z))})
    return {"hurst_scaling_all": slope, "hurst_scaling_30m_plus": slope_long, "variance_ratio": vr,
            "interpretation": "H≈0.5 ならランダムウォーク、>0.5 でトレンド持続、<0.5 で平均回帰。VR<1 は平均回帰、>1 はモメンタム。"}


def autocorr(grid: Grid, daily: pd.DataFrame) -> dict:
    out = {}
    series = {
        "1m": np.diff(np.log(grid.df["close"].to_numpy()))[-400_000:],
        "5m": np.diff(np.log(resample_bars(grid, "5min")["close"].to_numpy())),
        "1h": np.diff(np.log(resample_bars(grid, "1h")["close"].to_numpy())),
        "1d": np.diff(np.log(daily["close"].to_numpy())),
    }
    for k, r in series.items():
        if len(r) < 50:
            continue
        lags = list(range(1, min(11, len(r) // 5)))
        q, p = _ljung_box(r, len(lags))
        qa, pa = _ljung_box(np.abs(r), len(lags))
        out[k] = {"lags": lags, "acf_return": _acf(r, lags), "acf_abs_return": _acf(np.abs(r), lags),
                  "ljung_box_q": q, "ljung_box_p": p, "ljung_box_abs_q": qa, "ljung_box_abs_p": pa,
                  "se_approx": 1 / np.sqrt(len(r))}
    r1 = series["1m"]
    lags = [1, 2, 5, 10, 30, 60, 120, 240, 480, 720, 1440, 2880]
    out["abs_1m_long_memory"] = {"lags": lags, "acf": _acf(np.abs(r1), lags)}
    return out


def seasonality(grid: Grid, daily: pd.DataFrame) -> dict:
    df = grid.df
    ny = df.index.tz_convert(NY)
    r = np.log(df["close"]).diff()
    gap = df.index.to_series().diff() > pd.Timedelta(minutes=1)
    r = r.where(~gap.to_numpy())  # 再開ギャップは除外
    x = pd.DataFrame({"r": r.to_numpy(), "hour": ny.hour, "minute": ny.minute, "dow": ny.dayofweek,
                      "rng": np.log(df["high"] / df["low"]).to_numpy(), "vol": df["volume"].to_numpy()}).dropna()
    tot_var = (x["r"] ** 2).sum()

    def agg(key):
        g = x.groupby(key)
        res = pd.DataFrame({
            "n": g["r"].size(), "mean_bp": g["r"].mean() * 1e4, "std_bp": g["r"].std() * 1e4,
            "share_of_variance_pct": g["r"].apply(lambda s: (s ** 2).sum() / tot_var * 100),
            "p_up": g["r"].apply(lambda s: (s > 0).mean()), "avg_range_bp": g["rng"].mean() * 1e4,
            "avg_volume": g["vol"].mean()})
        return res

    by_hour = agg("hour")
    # 時間ごとの累積リターン（1時間全体の）と t 値
    hb = resample_bars(grid, "1h")
    hr = np.log(hb["close"]).diff().dropna()
    hrh = hr.index.tz_convert(NY).hour
    hour_ret = pd.DataFrame({"r": hr.to_numpy(), "h": hrh}).groupby("h")["r"]
    by_hour["hourly_return_mean_bp"] = hour_ret.mean() * 1e4
    by_hour["hourly_return_t"] = hour_ret.apply(lambda s: _tstat(s.to_numpy()))
    by_hour["hourly_p_up"] = hour_ret.apply(lambda s: (s > 0).mean())
    by_minute = agg("minute")
    by_minute["vol_ratio_vs_avg"] = by_minute["std_bp"] / by_minute["std_bp"].mean()

    dr = np.log(daily["close"]).diff().dropna()
    di = pd.DatetimeIndex(dr.index)
    dd = pd.DataFrame({"r": dr.to_numpy(), "dow": di.dayofweek, "month": di.month, "dom": di.day})
    # trading day はその日の NY 17:00 終了日。曜日は NY+7 基準の日付の曜日
    by_dow = dd.groupby("dow")["r"].agg(["size", "mean", "std"]).rename(columns={"size": "n"})
    by_dow["mean_bp"] = by_dow["mean"] * 1e4
    by_dow["std_bp"] = by_dow["std"] * 1e4
    by_dow["t"] = dd.groupby("dow")["r"].apply(lambda s: _tstat(s.to_numpy()))
    by_dow["p_up"] = dd.groupby("dow")["r"].apply(lambda s: (s > 0).mean())
    by_dow = by_dow.drop(columns=["mean", "std"])
    by_month = dd.groupby("month")["r"].agg(["size", "mean", "std"]).rename(columns={"size": "n"})
    by_month["mean_bp"] = by_month["mean"] * 1e4
    by_month["t"] = dd.groupby("month")["r"].apply(lambda s: _tstat(s.to_numpy()))
    by_month = by_month.drop(columns=["mean", "std"])
    # 月末月初（最終2営業日＋最初3営業日）
    ym = di.to_period("M")
    rank_f = pd.Series(1, index=di).groupby(ym).cumsum().to_numpy()
    rank_b = pd.Series(1, index=di)[::-1].groupby(ym[::-1]).cumsum()[::-1].to_numpy()
    tom = (rank_f <= 3) | (rank_b <= 2)
    turn = {"turn_of_month_mean_bp": dr[tom].mean() * 1e4, "turn_of_month_t": _tstat(dr[tom].to_numpy()),
            "rest_mean_bp": dr[~tom].mean() * 1e4, "rest_t": _tstat(dr[~tom].to_numpy())}

    # セッション別
    sess = {}
    for name, (a, b) in SESSIONS.items():
        m = _hour_in(x["hour"].to_numpy(), a, b)
        sub = x[m]
        sess[name] = {"share_of_variance_pct": (sub["r"] ** 2).sum() / tot_var * 100,
                      "std_bp_per_min": sub["r"].std() * 1e4, "avg_volume": sub["vol"].mean()}
    return {"by_ny_hour": by_hour.reset_index().to_dict("records"),
            "by_minute_of_hour": by_minute.reset_index().to_dict("records"),
            "by_weekday": by_dow.reset_index().to_dict("records"),
            "by_month": by_month.reset_index().to_dict("records"),
            "turn_of_month": turn, "sessions_intraday": sess,
            "note": "時刻はすべて米国東部時間(NY, 夏時間自動調整)。日本時間は概ね +13〜14 時間。"}


def top_slots(grid: Grid, f: np.ndarray, k: int = 15) -> list[dict]:
    order = np.argsort(f)[::-1][:k]
    names = ["月", "火", "水", "木", "金", "土", "日"]
    return [{"ny_time": f"{names[s // 1440]} {(s % 1440) // 60:02d}:{s % 60:02d}", "vol_multiple": float(np.sqrt(f[s]))}
            for s in order]


def time_events(grid: Grid) -> list[dict]:
    """毎日決まった時刻のイベント前後のボラティリティ倍率と方向の持続性。"""
    events = [("ロンドン AM フィキシング", "Europe/London", 10, 30), ("ロンドン PM フィキシング", "Europe/London", 15, 0),
              ("COMEX 開場", NY, 8, 20), ("米指標 8:30", NY, 8, 30), ("米指標 10:00", NY, 10, 0),
              ("NY 株式開場", NY, 9, 30), ("COMEX 終了", NY, 13, 30), ("NY クローズ前", NY, 16, 55),
              ("東京 9:00", "Asia/Tokyo", 9, 0), ("上海金 開場(北京 9:00)", "Asia/Shanghai", 9, 0)]
    pos_all = np.arange(grid.n)
    r2 = grid.r ** 2
    C = grid.Cr2
    out = []
    for name, tz, hh, mm in events:
        loc = grid.idx.tz_convert(tz)
        hit = np.where((loc.hour == hh) & (loc.minute == mm) & grid.is_open & (loc.dayofweek < 5))[0]
        hit = hit[(hit > 60) & (hit + 60 < grid.n)]
        if len(hit) < 10:
            continue
        before = (C[hit] - C[hit - 30]) / 30
        after5 = (C[hit + 5] - C[hit]) / 5
        after30 = (C[hit + 30] - C[hit]) / 30
        r5 = grid.logp[hit + 4] - grid.logp[hit - 1]
        r5_60 = grid.logp[hit + 59] - grid.logp[hit + 4]
        out.append({"event": name, "local_time": f"{tz} {hh:02d}:{mm:02d}", "n_days": int(len(hit)),
                    "vol_ratio_first5m_vs_prior30m": float(np.sqrt(after5.mean() / max(before.mean(), 1e-18))),
                    "vol_ratio_next30m_vs_prior30m": float(np.sqrt(after30.mean() / max(before.mean(), 1e-18))),
                    "mean_abs_move_5m_bp": float(np.abs(r5).mean() * 1e4),
                    "corr_first5m_vs_next55m": float(np.corrcoef(r5, r5_60)[0, 1]) if r5.std() > 0 and r5_60.std() > 0 else None,
                    "mean_return_5m_bp": float(r5.mean() * 1e4), "t_5m": _tstat(r5)})
    return out


def _event_window_stats(grid: Grid, times: pd.DatetimeIndex, label: str) -> dict | None:
    pos = np.array([grid.idx.searchsorted(t) for t in times if grid.idx[0] + pd.Timedelta(hours=2) < t < grid.idx[-1] - pd.Timedelta(hours=25)])
    if len(pos) < 3:
        return None
    C = grid.Cr2
    res = {"event": label, "n": int(len(pos))}
    base = (C[pos - 60] - C[pos - 1440]) / 1380
    for w in (1, 5, 30, 60, 240):
        res[f"vol_ratio_{w}m"] = float(np.sqrt(((C[pos + w] - C[pos]) / w).mean() / max(base.mean(), 1e-18)))
    for w in (1, 5, 15, 60, 240, 1440):
        r = grid.logp[np.minimum(pos + w - 1, grid.n - 1)] - grid.logp[pos - 1]
        res[f"abs_move_{w}m_bp_median"] = float(np.median(np.abs(r)) * 1e4)
        res[f"abs_move_{w}m_usd_median_at_last"] = float(np.median(np.abs(r)) * grid.close[-1])
        res[f"p_up_{w}m"] = float(np.mean(r > 0))
    r5 = grid.logp[pos + 4] - grid.logp[pos - 1]
    r_after = grid.logp[np.minimum(pos + 239, grid.n - 1)] - grid.logp[pos + 4]
    res["corr_first5m_vs_next4h"] = float(np.corrcoef(r5, r_after)[0, 1]) if len(pos) > 5 else None
    res["p_continuation_4h"] = float(np.mean(np.sign(r5) == np.sign(r_after)))
    return res


def nfp(grid: Grid) -> dict | None:
    ny = grid.idx.tz_convert(NY)
    m = (ny.dayofweek == 4) & (ny.day <= 7) & (ny.hour == 8) & (ny.minute == 30)
    times = grid.idx[m]
    r = _event_window_stats(grid, times, "米雇用統計(推定: 第1金曜 8:30 NY)")
    if r:
        r["note"] = "発表日は第1金曜と推定（祝日等でずれる月あり）。正確な分析には --events で日付を指定してください。"
    return r


def user_events(grid: Grid, events: pd.DataFrame | None) -> list[dict]:
    if events is None or events.empty:
        return []
    out = []
    for name, g in events.groupby("name"):
        r = _event_window_stats(grid, pd.DatetimeIndex(g["time"]), str(name))
        if r:
            out.append(r)
    return out


def load_events(path: str) -> pd.DataFrame:
    """CSV: time,name[,tz]  (time は ISO 形式。tz 列が無ければ UTC。例: 2025-01-10 08:30,NFP,America/New_York)"""
    ev = pd.read_csv(path)
    ev.columns = [c.lower().strip() for c in ev.columns]
    times = []
    for _, row in ev.iterrows():
        t = pd.Timestamp(row["time"])
        if t.tzinfo is None:
            t = t.tz_localize(row["tz"] if "tz" in ev.columns and isinstance(row["tz"], str) else "UTC")
        times.append(t.tz_convert("UTC"))
    return pd.DataFrame({"time": times, "name": ev["name"].astype(str)})


# ---------------------------------------------------------------------------
def _gjr_garch(r: np.ndarray, n_fit: int = 30000) -> dict:
    """GJR-GARCH(1,1) の擬似最尤推定（正規 QMLE）。分散再帰は線形フィルタで高速計算。"""
    from scipy.signal import lfilter

    r = r[-n_fit:]
    r = r - r.mean()
    x = r / r.std()
    x2 = x ** 2
    neg = (x < 0).astype(float)

    def nll(p):
        w, a, g, b = p
        if w <= 0 or a < 0 or not (0 <= b < 1) or a + g < 0 or a + b + g / 2 >= 0.9999:
            return 1e10
        drive = w + (a + g * neg[:-1]) * x2[:-1]
        h = lfilter([1.0], [1.0, -b], drive, zi=[b * 1.0])[0]
        h = np.r_[1.0, h]
        if np.any(h <= 0):
            return 1e10
        return 0.5 * np.sum(np.log(h) + x2 / h)

    best = None
    for start in ([0.05, 0.08, 0.0, 0.88], [0.02, 0.05, 0.02, 0.93], [0.1, 0.15, -0.02, 0.75]):
        res = optimize.minimize(nll, start, method="Nelder-Mead",
                                options={"maxiter": 4000, "xatol": 1e-7, "fatol": 1e-6})
        if best is None or res.fun < best.fun:
            best = res
    w, a, g, b = best.x
    pers = a + g / 2 + b
    return {"omega_std_units": w, "alpha": a, "gamma_leverage": g, "beta": b, "persistence": pers,
            "half_life_steps": float(np.log(0.5) / np.log(pers)) if 0 < pers < 1 else None,
            "n_obs": int(len(x)), "converged": bool(best.success),
            "leverage_note": "gamma>0: 下落後にボラ上昇（株式型）。gamma<0: 上昇後にボラ上昇（金で見られる逆レバレッジ）。"}


def volatility(grid: Grid, daily: pd.DataFrame, f: np.ndarray) -> dict:
    o, h, l, c = (np.log(daily[k].to_numpy()) for k in ("open", "high", "low", "close"))
    cc = np.diff(c)
    park = (h - l) ** 2 / (4 * np.log(2))
    gk = 0.5 * (h - l) ** 2 - (2 * np.log(2) - 1) * (c - o) ** 2
    rs = (h - c) * (h - o) + (l - c) * (l - o)
    on = o[1:] - c[:-1]
    oc = c - o
    k = 0.34 / (1.34 + (len(oc) + 1) / max(len(oc) - 1, 1))
    yz = on.var() + k * oc[1:].var() + (1 - k) * rs[1:].mean()
    ann = lambda v: float(np.sqrt(v * 252) * 100)
    est = {"close_to_close": ann(cc.var()), "parkinson": ann(park.mean()), "garman_klass": ann(gk.mean()),
           "rogers_satchell": ann(rs.mean()), "yang_zhang": ann(yz)}

    # 日次実現ボラ（1分足の二乗和）
    tday = pd.Series(grid.r ** 2).groupby(grid.tday).sum()
    n_open = pd.Series(grid.is_open.astype(int)).groupby(grid.tday).sum()
    rv = tday[n_open >= 600]
    rv_ann = np.sqrt(rv * 252) * 100
    lrv = np.log(rv.to_numpy())
    # HAR-RV (日次): log RV_t+1 = b0 + bd log RV_t + bw mean5 + bm mean22
    s = pd.Series(lrv)
    X = pd.DataFrame({"d": s, "w": s.rolling(5).mean(), "m": s.rolling(22).mean()}).shift(1)
    dfh = pd.concat([s.rename("y"), X], axis=1).dropna()
    har = {}
    if len(dfh) > 40:
        A = np.column_stack([np.ones(len(dfh)), dfh[["d", "w", "m"]].to_numpy()])
        b, *_ = np.linalg.lstsq(A, dfh["y"].to_numpy(), rcond=None)
        pred = A @ b
        har = {"b0": b[0], "b_daily": b[1], "b_weekly": b[2], "b_monthly": b[3],
               "r2": float(1 - np.var(dfh["y"] - pred) / np.var(dfh["y"]))}

    # GJR-GARCH（脱季節化 5 分リターン）
    r = grid.r
    fs = f[grid.slot]
    n5 = (grid.n // 5) * 5
    r5 = r[:n5].reshape(-1, 5).sum(1)
    f5 = fs[:n5].reshape(-1, 5).sum(1)
    m = f5 > 0.5
    z5 = r5[m] / np.sqrt(f5[m])
    garch = _gjr_garch(z5)
    if garch.get("half_life_steps"):
        garch["half_life_hours_of_trading"] = garch["half_life_steps"] * 5 / 60

    # 返り値と将来ボラの関係（レバレッジ効果）: 当日リターン vs 翌日 RV
    dr = np.log(daily["close"]).diff()
    rvd = pd.Series(rv.to_numpy(), index=daily.index[: len(rv)]) if len(rv) == len(daily) else None
    lev = None
    if rvd is not None and len(rvd) > 30:
        nxt = np.log(rvd).shift(-1)
        dd = pd.concat([dr, nxt], axis=1).dropna()
        lev = {"corr_return_vs_next_day_logRV": float(np.corrcoef(dd.iloc[:, 0], dd.iloc[:, 1])[0, 1]),
               "corr_neg_return_vs_next_logRV": float(np.corrcoef(np.minimum(dd.iloc[:, 0], 0), dd.iloc[:, 1])[0, 1]),
               "corr_pos_return_vs_next_logRV": float(np.corrcoef(np.maximum(dd.iloc[:, 0], 0), dd.iloc[:, 1])[0, 1])}

    atr = (daily["high"] - daily["low"]).rolling(14).mean()
    return {
        "annualized_vol_estimators_pct": est,
        "daily_realized_vol_ann_pct": {"mean": float(rv_ann.mean()), "median": float(rv_ann.median()),
                                       "p10": float(rv_ann.quantile(0.1)), "p90": float(rv_ann.quantile(0.9)),
                                       "last": float(rv_ann.iloc[-1]), "last_percentile": float((rv_ann < rv_ann.iloc[-1]).mean())},
        "vol_of_vol_logRV_std": float(np.std(np.diff(lrv))) if len(lrv) > 2 else None,
        "logRV_acf": _acf(lrv, [1, 2, 5, 10, 22]) if len(lrv) > 30 else None,
        "har_rv_daily": har, "gjr_garch_5m_deseasonalized": garch, "leverage_effect": lev,
        "atr14_usd_last": float(atr.iloc[-1]) if atr.notna().any() else None,
        "daily_range_usd": {"mean": float((daily["high"] - daily["low"]).mean()),
                            "median": float((daily["high"] - daily["low"]).median()),
                            "p90": float((daily["high"] - daily["low"]).quantile(0.9))},
    }


def ranges(grid: Grid, horizons=HORIZONS) -> list[dict]:
    open_pos = np.where(grid.is_open)[0]
    out = []
    p_last = grid.close[-1]
    hi_s = pd.Series(grid.high)
    lo_s = pd.Series(grid.low)
    for h in horizons:
        if h == 1:
            pos = open_pos[open_pos + 1 < grid.n]
            hh = grid.high[pos + 1]
            ll = grid.low[pos + 1]
        else:
            # (pos, pos+h] の最大・最小（ローリング）
            fmax = hi_s[::-1].rolling(h, min_periods=1).max()[::-1].shift(-1).to_numpy()
            fmin = lo_s[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1).to_numpy()
            pos = open_pos[open_pos + h < grid.n][:: max(1, h // 5)]
            hh, ll = fmax[pos], fmin[pos]
        p0 = grid.close[pos]
        up = np.log(hh / p0)
        dn = np.log(p0 / ll)
        rg = np.log(hh / ll)
        q = lambda x, a: float(np.quantile(x, a))
        out.append({"h": h, "label": horizon_label(h),
                    "range_bp": {"mean": rg.mean() * 1e4, "p10": q(rg, .1) * 1e4, "p50": q(rg, .5) * 1e4, "p90": q(rg, .9) * 1e4},
                    "range_usd_at_last": {"p10": q(rg, .1) * p_last, "p50": q(rg, .5) * p_last, "p90": q(rg, .9) * p_last},
                    "max_up_bp": {"p50": q(up, .5) * 1e4, "p75": q(up, .75) * 1e4, "p90": q(up, .9) * 1e4, "p99": q(up, .99) * 1e4},
                    "max_down_bp": {"p50": q(dn, .5) * 1e4, "p75": q(dn, .75) * 1e4, "p90": q(dn, .9) * 1e4, "p99": q(dn, .99) * 1e4}})
    return out


def touch_probs(grid: Grid, pcts=(0.1, 0.25, 0.5, 1.0, 2.0), horizons=(15, 60, 240, 1440), max_origins: int = 6000) -> list[dict]:
    open_pos = np.where(grid.is_open)[0]
    H = max(horizons)
    pos = open_pos[open_pos + H < grid.n]
    if len(pos) == 0:
        return []
    pos = pos[np.linspace(0, len(pos) - 1, min(max_origins, len(pos))).astype(int)]
    out = []
    ups = {(h, p): [] for h in horizons for p in pcts}
    dns = {(h, p): [] for h in horizons for p in pcts}
    first_up = {p: [] for p in pcts}
    for p in pos:
        p0 = grid.close[p]
        hi = np.maximum.accumulate(grid.high[p + 1:p + H + 1])
        lo = np.minimum.accumulate(grid.low[p + 1:p + H + 1])
        for pct in pcts:
            u, d = p0 * (1 + pct / 100), p0 * (1 - pct / 100)
            for h in horizons:
                ups[(h, pct)].append(hi[h - 1] >= u)
                dns[(h, pct)].append(lo[h - 1] <= d)
            iu = np.argmax(hi >= u) if hi[-1] >= u else H + 1
            idn = np.argmax(lo <= d) if lo[-1] <= d else H + 1
            if min(iu, idn) <= H and iu != idn:
                first_up[pct].append(iu < idn)
    for pct in pcts:
        row = {"pct": pct, "usd_at_last": grid.close[-1] * pct / 100}
        for h in horizons:
            row[f"p_touch_up_{h}m"] = float(np.mean(ups[(h, pct)]))
            row[f"p_touch_down_{h}m"] = float(np.mean(dns[(h, pct)]))
        row["p_up_first_within_24h"] = float(np.mean(first_up[pct])) if first_up[pct] else None
        out.append(row)
    return out


def conditional(grid: Grid, daily: pd.DataFrame) -> dict:
    out: dict[str, Any] = {}
    open_pos = np.where(grid.is_open)[0]
    # モメンタム / リバーサル（非重複サンプル）
    mom = []
    for h in (5, 15, 60, 240, 1440):
        pos = open_pos[(open_pos >= h) & (open_pos + h < grid.n)][::h]
        past = grid.logp[pos] - grid.logp[pos - h]
        fut = grid.logp[pos + h] - grid.logp[pos]
        if len(pos) < 50:
            continue
        qcut = pd.qcut(past, 5, labels=False, duplicates="drop")
        rows = []
        for qi in range(int(np.nanmax(qcut)) + 1):
            m = qcut == qi
            rows.append({"quintile": qi + 1, "past_mean_bp": past[m].mean() * 1e4, "next_mean_bp": fut[m].mean() * 1e4,
                         "next_t": _tstat(fut[m]), "next_p_up": float(np.mean(fut[m] > 0))})
        rho, p = sps.spearmanr(past, fut)
        mom.append({"h": h, "label": horizon_label(h), "n": int(len(pos)), "spearman": float(rho), "p_value": float(p),
                    "autocorr": float(np.corrcoef(past, fut)[0, 1]), "table": rows})
    out["momentum_reversal"] = mom

    # RSI（15分足・1時間足）
    rsi_tbl = []
    for rule, nxt in (("15min", 1), ("1h", 1), ("1h", 4)):
        b = resample_bars(grid, rule)
        rsi = _rsi(b["close"])
        fut = np.log(b["close"]).shift(-nxt) - np.log(b["close"])
        d = pd.DataFrame({"rsi": rsi, "fut": fut}).dropna()
        bins = [0, 20, 30, 45, 55, 70, 80, 100]
        d["b"] = pd.cut(d["rsi"], bins)
        for k, g in d.groupby("b", observed=True):
            rsi_tbl.append({"bars": rule, "ahead_bars": nxt, "rsi_bin": str(k), "n": int(len(g)),
                            "next_mean_bp": g["fut"].mean() * 1e4, "t": _tstat(g["fut"].to_numpy(), nxt),
                            "p_up": float((g["fut"] > 0).mean())})
    out["rsi"] = rsi_tbl

    # 移動平均乖離（1時間足、EMA20/EMA100 からの乖離 z）
    b = resample_bars(grid, "1h")
    lc = np.log(b["close"])
    hr = lc.diff()
    ma_tbl = []
    for n in (20, 100):
        dev = (lc - lc.ewm(span=n, adjust=False).mean()) / (hr.rolling(100).std() * np.sqrt(n))
        for ahead in (1, 4, 24):
            fut = lc.shift(-ahead) - lc
            d = pd.DataFrame({"dev": dev, "fut": fut}).dropna()
            if len(d) < 100:
                continue
            d["q"] = pd.qcut(d["dev"], 5, labels=False, duplicates="drop")
            for qi, g in d.groupby("q"):
                ma_tbl.append({"ema": n, "ahead_h": ahead, "quintile": int(qi) + 1, "dev_mean": g["dev"].mean(),
                               "next_mean_bp": g["fut"].mean() * 1e4, "t": _tstat(g["fut"].to_numpy(), ahead),
                               "p_up": float((g["fut"] > 0).mean())})
    out["ema_deviation_1h"] = ma_tbl

    # ボラ局面別（過去 1 日の実現ボラの三分位）→ 次の 1 日
    rvd = pd.Series(grid.r ** 2).groupby(grid.tday).sum()
    retd = pd.Series(grid.r).groupby(grid.tday).sum()
    d = pd.DataFrame({"rv": rvd, "ret": retd})
    d = d[d["rv"] > 0]
    d["next_rv"] = d["rv"].shift(-1)
    d["next_ret"] = d["ret"].shift(-1)
    d = d.dropna()
    if len(d) > 30:
        d["t"] = pd.qcut(d["rv"], 3, labels=["低ボラ", "中ボラ", "高ボラ"])
        out["vol_regime_daily"] = [
            {"regime": str(k), "n": int(len(g)), "next_day_vol_ann_pct": float(np.sqrt(g["next_rv"].mean() * 252) * 100),
             "next_day_mean_bp": g["next_ret"].mean() * 1e4, "next_day_t": _tstat(g["next_ret"].to_numpy()),
             "next_day_p_up": float((g["next_ret"] > 0).mean())} for k, g in d.groupby("t", observed=True)]

    # 連続陽線/陰線（1時間足・日足）→ 次の足が同方向の確率
    streak = []
    for name, ser in (("1h", hr.dropna()), ("1d", np.log(daily["close"]).diff().dropna())):
        s = np.sign(ser.to_numpy())
        s = s[s != 0]
        run = np.zeros(len(s), dtype=int)
        for i in range(len(s)):
            run[i] = run[i - 1] + 1 if i > 0 and s[i] == s[i - 1] else 1
        for k in range(1, 7):
            for sign, lab in ((1, "陽線"), (-1, "陰線")):
                m = (run[:-1] == k) & (s[:-1] == sign)
                if m.sum() >= 10:
                    streak.append({"bars": name, "after": f"{k}連続{lab}", "n": int(m.sum()),
                                   "p_same_direction_next": float(np.mean(s[1:][m] == sign))})
        # ラン検定 (Wald-Wolfowitz)
        n1, n2 = (s > 0).sum(), (s < 0).sum()
        runs = 1 + np.sum(s[1:] != s[:-1])
        mu = 2 * n1 * n2 / (n1 + n2) + 1
        var = (mu - 1) * (mu - 2) / (n1 + n2 - 1)
        streak.append({"bars": name, "runs_test_z": float((runs - mu) / np.sqrt(var)),
                       "note": "z<0: 同方向が続きやすい（トレンド的）、z>0: 反転しやすい"})
    out["streaks"] = streak
    return out


def session_links(grid: Grid) -> dict:
    df = grid.df
    ny = df.index.tz_convert(NY)
    td = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)
    lc = np.log(df["close"].to_numpy())
    r = pd.Series(np.r_[0.0, np.diff(lc)], index=df.index)
    sess_ret = {}
    hours = ny.hour.to_numpy()
    for name, (a, b) in SESSIONS.items():
        m = _hour_in(hours, a, b)
        sess_ret[name] = r[m].groupby(td[m]).sum()
    t = pd.DataFrame(sess_ret).dropna()
    names = list(SESSIONS)
    links = []
    for i in range(len(names)):
        a = names[i]
        b = names[(i + 1) % len(names)]
        x = t[a].to_numpy() if i + 1 < len(names) else t[a].to_numpy()[:-1]
        y = t[b].to_numpy() if i + 1 < len(names) else t[b].to_numpy()[1:]
        if len(x) > 20:
            links.append({"from": a, "to": b, "corr": float(np.corrcoef(x, y)[0, 1]),
                          "p_same_sign": float(np.mean(np.sign(x) == np.sign(y))), "n": int(len(x))})
    return {"session_return_mean_bp": {k: float(t[k].mean() * 1e4) for k in names},
            "session_return_t": {k: _tstat(t[k].to_numpy()) for k in names},
            "session_return_std_bp": {k: float(t[k].std() * 1e4) for k in names},
            "consecutive_session_links": links, "corr_matrix": t.corr().round(4).to_dict()}


def gaps(grid: Grid) -> dict:
    df = grid.df
    dt = df.index.to_series().diff()
    m = dt > pd.Timedelta(minutes=30)
    idx = np.where(m.to_numpy())[0]
    rows = []
    close = df["close"].to_numpy()
    hi = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    for i in idx:
        prev = close[i - 1]
        g = np.log(df["open"].iloc[i] / prev)
        end = min(i + 1440, len(df))
        filled = (lo[i:end].min() <= prev) if g > 0 else (hi[i:end].max() >= prev)
        rows.append({"weekend": dt.iloc[i] > pd.Timedelta(hours=24), "gap": g, "filled_24h": bool(filled), "gap_open_close": np.log(close[i] / prev)})
    if not rows:
        return {}
    t = pd.DataFrame(rows)
    out = {}
    for w, g in t.groupby("weekend"):
        k = "weekend" if w else "daily_break"
        a = np.abs(g["gap"])
        out[k] = {"n": int(len(g)), "mean_bp": g["gap"].mean() * 1e4, "mean_abs_bp": a.mean() * 1e4,
                  "p90_abs_bp": float(a.quantile(0.9) * 1e4), "max_abs_bp": float(a.max() * 1e4),
                  "p_up": float((g["gap"] > 0).mean()), "p_fill_within_24h": float(g["filled_24h"].mean()),
                  "mean_abs_usd_at_last": float(a.mean() * grid.close[-1])}
    return out


def round_numbers(grid: Grid, levels=(10, 50, 100), band_usd: float = 1.0, ahead: int = 60) -> list[dict]:
    df = grid.df
    c = df["close"].to_numpy()
    out = []
    for step in levels:
        near = np.round(c / step) * step
        dist = c - near
        inband = np.abs(dist) <= band_usd
        # 帯の外(3倍以上)から初めて帯に入った足
        far = np.abs(dist) > 3 * band_usd
        last_far_side = pd.Series(np.where(far, np.sign(dist), np.nan)).ffill().to_numpy()
        entry = inband & ~np.r_[False, inband[:-1]] & ~np.isnan(last_far_side)
        idx = np.where(entry)[0]
        idx = idx[idx + ahead < len(c)]
        if len(idx) < 20:
            continue
        side = last_far_side[idx]
        lvl = near[idx]
        fut = c[idx + ahead]
        rejected = np.sign(fut - lvl) == side
        # 比較: 任意の価格（キリ番の中間）に同条件で接近したケース
        mid = near + step / 2
        dmid = c - mid
        inb2 = np.abs(dmid) <= band_usd
        far2 = np.abs(dmid) > 3 * band_usd
        lfs2 = pd.Series(np.where(far2, np.sign(dmid), np.nan)).ffill().to_numpy()
        e2 = inb2 & ~np.r_[False, inb2[:-1]] & ~np.isnan(lfs2)
        i2 = np.where(e2)[0]
        i2 = i2[i2 + ahead < len(c)]
        rej2 = np.sign(c[i2 + ahead] - mid[i2]) == lfs2[i2]
        out.append({"level_step_usd": step, "n_touches": int(len(idx)), "p_reject_after_60m": float(rejected.mean()),
                    "baseline_p_reject_mid_levels": float(rej2.mean()) if len(i2) else None,
                    "note": "接近してきた側に 60 分後に戻っている確率。基準（キリ番の中間価格）と比べて高ければ反発傾向。"})
    return out


def volume_stats(grid: Grid) -> dict:
    df = grid.df
    if df["volume"].sum() <= 0:
        return {}
    r = np.abs(np.log(df["close"]).diff()).to_numpy()[1:]
    v = df["volume"].to_numpy()[1:]
    m = np.isfinite(r) & (v > 0)
    ny = df.index.tz_convert(NY)
    byh = df.groupby(ny.hour)["volume"].mean()
    # 出来高急増後の 15 分ボラ
    vv = pd.Series(df["volume"].to_numpy())
    rel = (vv / vv.rolling(1440, min_periods=100).mean()).to_numpy()
    lr = np.log(df["close"].to_numpy())
    fut = np.abs(np.r_[lr[15:] - lr[:-15], np.full(15, np.nan)])
    q = np.nanquantile(rel, [0.5, 0.9, 0.99])
    return {"corr_volume_abs_return_1m": float(np.corrcoef(v[m], r[m])[0, 1]),
            "spearman_volume_abs_return_1m": float(sps.spearmanr(v[m][:200000], r[m][:200000])[0]),
            "avg_volume_by_ny_hour": {int(k): float(x) for k, x in byh.items()},
            "next15m_abs_move_bp_by_rel_volume": {
                "rel<median": float(np.nanmean(fut[rel < q[0]]) * 1e4),
                "rel>p90": float(np.nanmean(fut[rel > q[1]]) * 1e4),
                "rel>p99": float(np.nanmean(fut[rel > q[2]]) * 1e4)}}


def trend(grid: Grid, daily: pd.DataFrame) -> dict:
    c = daily["close"]
    out = {}
    for n in (20, 50, 100, 200):
        if len(c) > n:
            ma = c.rolling(n).mean()
            out[f"dist_from_ma{n}_pct"] = float((c.iloc[-1] / ma.iloc[-1] - 1) * 100)
            out[f"share_days_above_ma{n}"] = float((c > ma)[ma.notna()].mean())
    dd = c / c.cummax() - 1
    out["max_drawdown_pct"] = float(dd.min() * 100)
    out["current_drawdown_pct"] = float(dd.iloc[-1] * 100)
    for n, lab in ((1, "1d"), (5, "1w"), (21, "1m"), (63, "3m"), (252, "1y")):
        if len(c) > n:
            out[f"return_{lab}_pct"] = float((c.iloc[-1] / c.iloc[-1 - n] - 1) * 100)
    return out


def extremes(grid: Grid, daily: pd.DataFrame, k: int = 10) -> dict:
    df = grid.df
    out = {}
    r1 = np.log(df["close"]).diff().dropna()
    gap = df.index.to_series().diff() > pd.Timedelta(minutes=1)
    r1 = r1[~gap.reindex(r1.index).to_numpy()]
    hb = resample_bars(grid, "1h")
    rh = np.log(hb["close"]).diff().dropna()
    rd = np.log(daily["close"]).diff().dropna()
    for name, r in (("1m", r1), ("1h", rh), ("1d", rd)):
        top = r.abs().sort_values(ascending=False).head(k)
        out[name] = [{"time": str(t), "return_pct": float(r.loc[t] * 100)} for t in top.index]
    return out


def current_state(grid: Grid, daily: pd.DataFrame, f: np.ndarray) -> dict:
    c = grid.df["close"]
    out = {"last_time_utc": str(c.index[-1]), "last_time_ny": str(c.index[-1].tz_convert(NY)),
           "last_time_tokyo": str(c.index[-1].tz_convert("Asia/Tokyo")), "last_price": float(c.iloc[-1])}
    r2 = grid.r ** 2
    fs = f[grid.slot]
    for w, lab in ((60, "1h"), (240, "4h"), (1440, "1d"), (7200, "5d")):
        lv = pd.Series(r2).rolling(w).sum() / (pd.Series(fs).rolling(w).sum() + 0.02 * w)
        lv = lv[grid.is_open]
        out[f"deseasonalized_vol_{lab}_percentile"] = float((lv.dropna() < lv.iloc[-1]).mean())
        out[f"deseasonalized_vol_{lab}_vs_median"] = float(np.sqrt(lv.iloc[-1] / lv.median()))
    for rule in ("15min", "1h"):
        b = resample_bars(grid, rule)
        out[f"rsi14_{rule}"] = float(_rsi(b["close"]).iloc[-1])
    return out


# ---------------------------------------------------------------------------
def collect_stats(df: pd.DataFrame, events: pd.DataFrame | None = None, verbose: bool = True) -> dict:
    grid = Grid(df)
    daily = daily_bars(grid)
    f = estimate_profile(grid)
    steps = [
        ("basic", lambda: basic(grid, daily)),
        ("horizons", lambda: horizon_stats(grid)),
        ("autocorr", lambda: autocorr(grid, daily)),
        ("seasonality", lambda: seasonality(grid, daily)),
        ("top_slots", lambda: top_slots(grid, f)),
        ("time_events", lambda: time_events(grid)),
        ("nfp", lambda: nfp(grid)),
        ("events", lambda: user_events(grid, events)),
        ("volatility", lambda: volatility(grid, daily, f)),
        ("ranges", lambda: ranges(grid)),
        ("touch", lambda: touch_probs(grid)),
        ("conditional", lambda: conditional(grid, daily)),
        ("sessions", lambda: session_links(grid)),
        ("gaps", lambda: gaps(grid)),
        ("round_numbers", lambda: round_numbers(grid)),
        ("volume", lambda: volume_stats(grid)),
        ("trend", lambda: trend(grid, daily)),
        ("extremes", lambda: extremes(grid, daily)),
        ("current", lambda: current_state(grid, daily, f)),
    ]
    out: dict[str, Any] = {}
    for name, fn in steps:
        if verbose:
            print(f"  統計: {name}", flush=True)
        try:
            out[name] = fn()
        except Exception as e:  # 一部が失敗しても他は出力する
            out[name] = {"error": f"{type(e).__name__}: {e}"}
    out["scaling"] = scaling(grid, out["horizons"]) if isinstance(out["horizons"], list) else {}
    return _clean(out)
