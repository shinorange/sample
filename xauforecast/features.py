"""予測に使う大規模な特徴量ライブラリ（約 150 個、すべて時点 t までのデータのみ使用）。

グループ:
  リターン     多時間軸の正規化リターン（1分〜5日）
  ボラ         脱季節化実現分散、ボラ比率、Parkinson レンジボラ、下方セミ分散比、
               バイパワー変動によるジャンプ比率、実現歪度・尖度、最大変動、ボラのボラ
  季節性       日中季節性の現在値と将来値、時刻・曜日・月の周期、取引日内の経過時間、月末月初
  イベント     米指標 8:30/10:00、FOMC 14:00、ロンドン・フィキシング、COMEX 開閉、東京・NY 開場
               までの近さ / 経過、雇用統計日、ユーザー指定の指標カレンダー
  テクニカル   EMA 乖離と傾き、RSI(6 期間)、ボリンジャー z、ストキャスティクス、MACD、
               効率比（トレンドの強さ）、ローリング自己相関、ローリング分散比、連続足
  価格構造     当日高安内の位置、前日高値/安値/終値、週高安・週始値、当日始値、ロンドン/NY 始値、
               キリ番（$10/$50/$100）からの距離、週明けギャップ
  出来高       相対出来高、季節調整出来高、VWAP 乖離、売買の偏り（符号付き出来高）
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .core import NY, slots_of

LN2x4 = 4 * np.log(2.0)


def _wsum(C: np.ndarray, w: int) -> np.ndarray:
    """(t-w, t] の和。C は長さ n+1 の累積和。"""
    n = len(C) - 1
    pos = np.arange(n)
    return C[pos + 1] - C[np.clip(pos + 1 - w, 0, None)]


def _cs(x: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(x)])


def _clock_kernel(local: pd.DatetimeIndex, hh: int, mm: int, scale: float = 60.0, weekday_only: bool = True):
    """毎日 hh:mm（現地時間）のイベントまでの近さ exp(-分/scale) と、経過の近さ。"""
    m = local.hour.to_numpy() * 60 + local.minute.to_numpy()
    t = hh * 60 + mm
    nxt = (t - m) % 1440
    since = (m - t) % 1440
    wk = (local.dayofweek.to_numpy() < 5).astype(float) if weekday_only else 1.0
    return np.exp(-nxt / scale) * wk, np.exp(-since / scale) * wk


def volume_profile(grid, end: int) -> np.ndarray:
    v = grid.volume[:end]
    op = grid.is_open[:end]
    s = np.bincount(grid.slot[:end][op], weights=v[op], minlength=10080)
    c = np.bincount(grid.slot[:end][op], minlength=10080)
    prof = s / np.maximum(c, 1)
    med = np.median(prof[c > 0]) if (c > 0).any() else 1.0
    return np.where(c > 5, prof, med) + 1e-9


def compute_features(grid, f: np.ndarray, Cf: np.ndarray, L: dict, eps: float,
                     vprofile: np.ndarray, events: pd.DatetimeIndex | None = None) -> tuple[dict, dict]:
    g = grid
    n = g.n
    r = g.r
    r2 = r ** 2
    X: dict[str, np.ndarray] = {}
    G: dict[str, str] = {}

    def add(name, arr, group):
        X[name] = arr
        G[name] = group

    Lref = np.maximum(L[1440], eps)
    day_unit = np.sqrt(Lref * 1380.0)
    fw = {w: _wsum(Cf, w) + 0.02 * w for w in (1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 480, 720, 1440, 2880, 7200, 30240)}
    Cr = _cs(r)
    Cr2 = g.Cr2

    # ------------------------------------------------------------ リターン
    for w in (1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 480, 720, 1440, 2880, 7200):
        add(f"nr_{w}", _wsum(Cr, w) / np.sqrt(Lref * fw[w]), "リターン")

    # ------------------------------------------------------------ ボラ
    Lw = {}
    for w in (5, 15, 30, 60, 120, 240, 480, 1440, 2880, 7200, 30240):
        Lw[w] = L[w] if w in L else _wsum(Cr2, w) / fw[w]
        add(f"logL_{w}", np.log(Lw[w] + eps), "ボラ")
    for a, b in ((15, 240), (60, 1440), (240, 7200), (1440, 30240), (5, 60)):
        add(f"vr_{a}_{b}", np.log((Lw[a] + eps) / (Lw[b] + eps)), "ボラ")
    pk = np.log(np.maximum(g.high, 1e-12) / np.maximum(g.low, 1e-12)) ** 2 / LN2x4
    Cpk = _cs(pk)
    for w in (15, 60, 240, 1440):
        P = _wsum(Cpk, w) / fw[w]
        add(f"logPark_{w}", np.log(P + eps), "ボラ")
        if w in (60, 1440):
            add(f"park_rv_{w}", np.log((P + eps) / (Lw[w] + eps)), "ボラ")
    Cneg = _cs(r2 * (r < 0))
    Cbp = _cs(np.abs(r) * np.abs(np.r_[0.0, r[:-1]]))
    Cr3 = _cs(r ** 3)
    Cr4 = _cs(r ** 4)
    Cop = _cs(g.is_open.astype(float))
    for w in (60, 1440):
        rv = _wsum(Cr2, w) + 1e-18
        add(f"downshare_{w}", _wsum(Cneg, w) / rv - 0.5, "ボラ")
    for w in (240, 1440):
        rv = _wsum(Cr2, w) + 1e-18
        bv = (np.pi / 2) * _wsum(Cbp, w)
        add(f"jump_{w}", np.clip(1 - bv / rv, 0, 1), "ボラ")
    rv1440 = _wsum(Cr2, 1440) + 1e-18
    nop = np.maximum(_wsum(Cop, 1440), 1)
    add("rskew_1440", np.sqrt(nop) * _wsum(Cr3, 1440) / rv1440 ** 1.5, "ボラ")
    add("rkurt_1440", np.log(nop * _wsum(Cr4, 1440) / rv1440 ** 2 + 1e-9), "ボラ")
    absr = pd.Series(np.abs(r))
    for w in (60, 1440):
        add(f"maxabs_{w}", absr.rolling(w, min_periods=1).max().to_numpy() / np.sqrt(Lref), "ボラ")
    add("volvol_1440", pd.Series(np.log(Lw[15] + eps)).rolling(1440, min_periods=60).std().to_numpy(), "ボラ")

    # ------------------------------------------------------------ 季節性
    ext = pd.date_range(g.idx[-1] + pd.Timedelta(minutes=1), periods=1441, freq="min")
    f_ext = np.concatenate([f[g.slot], f[slots_of(ext)]])
    Cfe = _cs(f_ext)
    pos = np.arange(n)
    add("logf_now", np.log(f[g.slot]), "季節性")
    for h in (15, 60, 240, 1440):
        add(f"logF_next_{h}", np.log((Cfe[pos + h + 1] - Cfe[pos + 1]) / h + 1e-6), "季節性")
    ang = 2 * np.pi * g.mod / 1440
    add("tod_sin", np.sin(ang), "季節性")
    add("tod_cos", np.cos(ang), "季節性")
    add("tod_sin2", np.sin(2 * ang), "季節性")
    add("tod_cos2", np.cos(2 * ang), "季節性")
    wang = 2 * np.pi * (g.dow * 1440 + g.mod) / 10080
    add("dow_sin", np.sin(wang), "季節性")
    add("dow_cos", np.cos(wang), "季節性")
    ny = g.idx.tz_convert(NY)
    # 年内の時期（dayofyear）は使わない: 1〜2 年のデータでは「その時期のボラ水準」を暗記してしまうため
    dom = ny.day.to_numpy()
    add("turn_of_month", ((dom >= 27) | (dom <= 3)).astype(float), "季節性")
    add("session_elapsed", ((g.mod - 1080) % 1440) / 1440.0, "季節性")
    add("is_friday", (g.dow == 4).astype(float), "季節性")

    # ------------------------------------------------------------ イベント
    lon = g.idx.tz_convert("Europe/London")
    tyo = g.idx.tz_convert("Asia/Tokyo")
    for name, loc, hh, mm in (("ny0830", ny, 8, 30), ("ny1000", ny, 10, 0), ("ny1400", ny, 14, 0),
                              ("ny0820", ny, 8, 20), ("ny1330", ny, 13, 30), ("ny0930", ny, 9, 30),
                              ("lon1030", lon, 10, 30), ("lon1500", lon, 15, 0), ("tyo0900", tyo, 9, 0)):
        a, b = _clock_kernel(loc, hh, mm)
        add(f"ev_{name}_next", a, "イベント")
        add(f"ev_{name}_since", b, "イベント")
    nfp_day = ((ny.dayofweek.to_numpy() == 4) & (dom <= 7)).astype(float)
    add("nfp_day", nfp_day, "イベント")
    add("nfp_near", nfp_day * np.exp(-np.abs(g.mod - 510) / 60.0), "イベント")
    if events is not None and len(events):
        et = np.sort(pd.DatetimeIndex(events).tz_convert("UTC").as_unit("ns").asi8)
        t = g.idx.as_unit("ns").asi8
        i = np.searchsorted(et, t, side="left")
        nxt = np.where(i < len(et), (et[np.minimum(i, len(et) - 1)] - t) / 6e10, 1e9)
        j = np.searchsorted(et, t, side="right") - 1
        since = np.where(j >= 0, (t - et[np.maximum(j, 0)]) / 6e10, 1e9)
        add("ev_user_next", np.exp(-nxt / 60.0), "イベント")
        add("ev_user_since", np.exp(-since / 120.0), "イベント")

    # ------------------------------------------------------------ テクニカル
    lp = pd.Series(g.logp)
    emas = {}
    for s in (15, 30, 60, 120, 240, 480, 1440, 2880, 7200):
        emas[s] = lp.ewm(span=s, adjust=False).mean().to_numpy()
        add(f"ema_{s}", (g.logp - emas[s]) / np.sqrt(Lref * s), "テクニカル")
    for s in (60, 240, 1440):
        e = pd.Series(emas[s])
        add(f"emaslope_{s}", (e - e.shift(max(s // 4, 1))).to_numpy() / np.sqrt(Lref * s), "テクニカル")
    up = pd.Series(np.clip(r, 0, None))
    dn = pd.Series(np.clip(-r, 0, None))
    for p in (7, 14, 28, 56, 210, 840):
        a = up.ewm(alpha=1 / p, adjust=False).mean().to_numpy()
        b = dn.ewm(alpha=1 / p, adjust=False).mean().to_numpy()
        add(f"rsi_{p}", a / (a + b + 1e-18) - 0.5, "テクニカル")
    for w in (20, 60, 240, 1440):
        m = lp.rolling(w, min_periods=2).mean().to_numpy()
        sd = lp.rolling(w, min_periods=2).std().to_numpy()
        add(f"boll_{w}", (g.logp - m) / (sd + 1e-9), "テクニカル")
    hi_s = pd.Series(g.high)
    lo_s = pd.Series(g.low)
    for w in (15, 60, 240, 1440):
        hh = hi_s.rolling(w, min_periods=1).max().to_numpy()
        ll = lo_s.rolling(w, min_periods=1).min().to_numpy()
        add(f"stoch_{w}", (g.close - ll) / np.maximum(hh - ll, 1e-9) - 0.5, "テクニカル")
    for name, a, b, c in (("macd_15m", 180, 390, 135), ("macd_1h", 720, 1560, 540)):
        macd = lp.ewm(span=a, adjust=False).mean() - lp.ewm(span=b, adjust=False).mean()
        sig = macd.ewm(span=c, adjust=False).mean()
        add(name, (macd - sig).to_numpy() / np.sqrt(Lref * b), "テクニカル")
    Cabs = _cs(np.abs(r))
    for w in (15, 60, 240, 1440):
        add(f"er_{w}", np.abs(_wsum(Cr, w)) / (_wsum(Cabs, w) + 1e-12), "テクニカル")
    Cac = _cs(r * np.r_[0.0, r[:-1]])
    for w in (240, 1440):
        add(f"rac1_{w}", _wsum(Cac, w) / (_wsum(Cr2, w) + 1e-18), "テクニカル")
    r5 = g.logp - np.r_[np.full(5, g.logp[0]), g.logp[:-5]]
    add("vr5_1440", _wsum(_cs(r5 ** 2), 1440) / (5 * _wsum(Cr2, 1440) + 1e-18), "テクニカル")
    sgn = np.sign(r)
    run = np.zeros(n)
    last, cnt = 0.0, 0.0
    for i in range(n):  # 連続して同じ方向に動いた 1 分足の数（符号付き）
        s = sgn[i]
        if s != 0:
            cnt = cnt + 1 if s == last else 1.0
            last = s
        run[i] = cnt * last
    add("streak_1m", np.clip(run, -20, 20), "テクニカル")

    # ------------------------------------------------------------ 価格構造
    td = g.tday
    dh = hi_s.groupby(td).cummax().to_numpy()
    dl = lo_s.groupby(td).cummin().to_numpy()
    add("daypos", (g.close - dl) / np.maximum(dh - dl, 1e-9) - 0.5, "価格構造")
    add("dist_dayhigh", np.log(g.close / dh) / day_unit, "価格構造")
    add("dist_daylow", np.log(g.close / dl) / day_unit, "価格構造")
    dfr = pd.DataFrame({"h": g.high, "l": g.low, "c": g.close, "o": g.open, "td": td})
    agg = dfr.groupby("td").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"), o=("o", "first"))
    prev = agg.shift(1)
    for k, lab in (("h", "prevhigh"), ("l", "prevlow"), ("c", "prevclose")):
        ref = prev[k].reindex(td).to_numpy()
        add(f"dist_{lab}", np.nan_to_num(np.log(g.close / ref) / day_unit), "価格構造")
    dopen = agg["o"].reindex(td).to_numpy()
    add("dist_dayopen", np.log(g.close / dopen) / day_unit, "価格構造")
    td_dates = pd.DatetimeIndex(g.tday_dates)
    wk_of_td = pd.factorize((td_dates - pd.to_timedelta(td_dates.dayofweek, unit="D")).normalize())[0]
    wk = wk_of_td[td]
    wh = hi_s.groupby(wk).cummax().to_numpy()
    wl = lo_s.groupby(wk).cummin().to_numpy()
    wagg = dfr.assign(wk=wk).groupby("wk").agg(o=("o", "first"), c=("c", "last"))
    wopen = wagg["o"].reindex(wk).to_numpy()
    wprevc = wagg["c"].shift(1).reindex(wk).to_numpy()
    add("dist_weekhigh", np.log(g.close / wh) / day_unit, "価格構造")
    add("dist_weeklow", np.log(g.close / wl) / day_unit, "価格構造")
    add("dist_weekopen", np.log(g.close / wopen) / day_unit, "価格構造")
    add("week_gap", np.nan_to_num(np.log(wopen / wprevc) / day_unit), "価格構造")
    for name, hm in (("london_open", 180), ("ny_open", 500)):
        mark = pd.Series(np.where((g.mod == hm) & g.is_open, g.close, np.nan))
        ref = mark.groupby(td).ffill().to_numpy()
        add(f"dist_{name}", np.nan_to_num(np.log(g.close / ref) / day_unit), "価格構造")
    for step in (10.0, 50.0, 100.0):
        d = g.close - np.round(g.close / step) * step
        add(f"round_{int(step)}", d / (g.close * day_unit), "価格構造")
    add("round50_pos", np.mod(g.close, 50.0) / 50.0 - 0.5, "価格構造")

    # ------------------------------------------------------------ 出来高
    v = g.volume
    Cv = _cs(v)
    base = _wsum(Cv, 1440) / 1440 + 1e-9
    for w in (1, 15, 60):
        add(f"relvol_{w}", np.log((_wsum(Cv, w) / w + 1e-9) / base), "出来高")
    add("vol_vs_season", np.log((v + 1) / (vprofile[g.slot] + 1)) * g.is_open, "出来高")
    cpv = pd.Series(v * g.close).groupby(td).cumsum().to_numpy()
    cvv = pd.Series(v).groupby(td).cumsum().to_numpy()
    vwap = np.where(cvv > 0, cpv / np.maximum(cvv, 1e-9), g.close)
    add("vwap_dev", np.log(g.close / vwap) / day_unit, "出来高")
    Csv = _cs(np.sign(r) * v)
    for w in (15, 60, 240):
        add(f"imb_{w}", _wsum(Csv, w) / (_wsum(Cv, w) + 1e-9), "出来高")

    for k in X:
        X[k] = np.clip(np.nan_to_num(X[k], nan=0.0, posinf=0.0, neginf=0.0), -50, 50).astype(np.float32)
    return X, G


# kNN（類似局面検索）で使う特徴量
ANALOG_FEATURES = [
    "nr_5", "nr_15", "nr_60", "nr_240", "nr_1440", "nr_7200", "ema_240", "ema_1440", "ema_7200",
    "rsi_14", "rsi_210", "logL_60", "logL_1440", "vr_60_1440", "vr_1440_30240", "daypos",
    "tod_sin", "tod_cos", "dow_sin", "dow_cos", "er_60", "er_1440", "ev_ny0830_next", "relvol_60",
    "stoch_1440", "jump_1440", "dist_prevclose", "dist_weekopen",
]


def _span(w: str) -> str:
    w = int(w)
    if w % 1440 == 0:
        return f"{w // 1440}日"
    if w % 60 == 0:
        return f"{w // 60}時間"
    return f"{w}分"


_EV = {"ny0830": "米指標8:30", "ny1000": "米指標10:00", "ny1400": "FOMC等14:00", "ny0820": "COMEX開場",
       "ny1330": "COMEX終了", "ny0930": "NY株開場", "lon1030": "ロンドンAMフィックス", "lon1500": "ロンドンPMフィックス",
       "tyo0900": "東京9:00", "user": "指定イベント"}


def feature_label(name: str) -> str:
    """特徴量名の日本語説明。"""
    import re

    rules = [
        (r"nr_(\d+)$", lambda m: f"過去{_span(m[1])}のリターン(σ単位)"),
        (r"logL_(\d+)$", lambda m: f"過去{_span(m[1])}の実現ボラ(脱季節化)"),
        (r"vr_(\d+)_(\d+)$", lambda m: f"ボラ比 {_span(m[1])}/{_span(m[2])}"),
        (r"logPark_(\d+)$", lambda m: f"過去{_span(m[1])}のレンジボラ(Parkinson)"),
        (r"park_rv_(\d+)$", lambda m: f"レンジボラ/実現ボラ比 {_span(m[1])}"),
        (r"downshare_(\d+)$", lambda m: f"下方セミ分散の比率 {_span(m[1])}"),
        (r"jump_(\d+)$", lambda m: f"ジャンプ比率 {_span(m[1])}"),
        (r"rskew_(\d+)$", lambda m: f"実現歪度 {_span(m[1])}"),
        (r"rkurt_(\d+)$", lambda m: f"実現尖度 {_span(m[1])}"),
        (r"maxabs_(\d+)$", lambda m: f"過去{_span(m[1])}の最大1分変動"),
        (r"volvol_(\d+)$", lambda m: "ボラのボラ"),
        (r"logf_now$", lambda m: "現在時刻の季節的ボラ"),
        (r"logF_next_(\d+)$", lambda m: f"今後{_span(m[1])}の季節的ボラ"),
        (r"tod_(sin|cos)2?$", lambda m: "時刻(周期)"),
        (r"dow_(sin|cos)$", lambda m: "曜日(周期)"),
        (r"doy_(sin|cos)$", lambda m: "年内の時期(周期)"),
        (r"turn_of_month$", lambda m: "月末月初"),
        (r"session_elapsed$", lambda m: "取引日内の経過時間"),
        (r"is_friday$", lambda m: "金曜日"),
        (r"ev_(\w+?)_next$", lambda m: f"{_EV.get(m[1], m[1])}までの近さ"),
        (r"ev_(\w+?)_since$", lambda m: f"{_EV.get(m[1], m[1])}からの近さ"),
        (r"nfp_day$", lambda m: "雇用統計日"),
        (r"nfp_near$", lambda m: "雇用統計発表の近さ"),
        (r"ema_(\d+)$", lambda m: f"EMA({_span(m[1])})からの乖離"),
        (r"emaslope_(\d+)$", lambda m: f"EMA({_span(m[1])})の傾き"),
        (r"rsi_(\d+)$", lambda m: f"RSI({m[1]}分)"),
        (r"boll_(\d+)$", lambda m: f"ボリンジャーz({_span(m[1])})"),
        (r"stoch_(\d+)$", lambda m: f"ストキャスティクス({_span(m[1])})"),
        (r"macd_(\w+)$", lambda m: f"MACD({m[1]})"),
        (r"er_(\d+)$", lambda m: f"効率比(トレンド度) {_span(m[1])}"),
        (r"rac1_(\d+)$", lambda m: f"1分リターンの自己相関 {_span(m[1])}"),
        (r"vr5_(\d+)$", lambda m: f"分散比(5分) {_span(m[1])}"),
        (r"streak_1m$", lambda m: "1分足の連続同方向本数"),
        (r"daypos$", lambda m: "当日レンジ内の位置"),
        (r"dist_(\w+)$", lambda m: {"dayhigh": "当日高値からの距離", "daylow": "当日安値からの距離",
                                    "prevhigh": "前日高値からの距離", "prevlow": "前日安値からの距離",
                                    "prevclose": "前日終値からの距離", "dayopen": "当日始値からの距離",
                                    "weekhigh": "週高値からの距離", "weeklow": "週安値からの距離",
                                    "weekopen": "週始値からの距離", "london_open": "ロンドン始値からの距離",
                                    "ny_open": "NY始値からの距離"}.get(m[1], m[1])),
        (r"week_gap$", lambda m: "週明けギャップ"),
        (r"round_(\d+)$", lambda m: f"${m[1]}キリ番からの距離"),
        (r"round50_pos$", lambda m: "$50刻み内の位置"),
        (r"relvol_(\d+)$", lambda m: f"相対出来高 {_span(m[1])}"),
        (r"vol_vs_season$", lambda m: "季節調整出来高"),
        (r"vwap_dev$", lambda m: "当日VWAPからの乖離"),
        (r"imb_(\d+)$", lambda m: f"売買の偏り(符号付き出来高) {_span(m[1])}"),
    ]
    for pat, fn in rules:
        m = re.match(pat, name)
        if m:
            return fn(m)
    return name
