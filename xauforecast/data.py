"""XAUUSD 1分足データの読み込み・整形・保存・合成データ生成。

内部形式: UTC の tz-aware DatetimeIndex（1分単位、取引があった分のみ）と
列 open/high/low/close/volume を持つ DataFrame。
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

NY = "America/New_York"
COLS = ["open", "high", "low", "close", "volume"]


# ---------------------------------------------------------------------------
# タイムゾーン処理
# ---------------------------------------------------------------------------
def localize_to_utc(index: pd.DatetimeIndex, tz: str | None) -> pd.DatetimeIndex:
    """naive な時刻を指定タイムゾーンとして解釈し UTC に変換する。

    tz の書式:
      - None / "UTC"           : UTC
      - IANA 名 (例 "Asia/Tokyo")
      - "UTC+2", "UTC-5"       : 固定オフセット
      - "NY+7"                 : 多くの MT4/MT5 ブローカーのサーバー時間
                                 （NY 17:00 = 0:00 となる、米国夏時間に連動した UTC+2/+3）
    """
    if index.tz is not None:
        return index.tz_convert("UTC")
    if tz is None or tz.upper() == "UTC":
        return index.tz_localize("UTC")
    m = re.fullmatch(r"(?i)NY([+-]\d+(?:\.\d+)?)", tz)
    if m:
        shift = pd.Timedelta(hours=float(m.group(1)))
        ny = (index - shift).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward")
        return ny.tz_convert("UTC")
    m = re.fullmatch(r"(?i)UTC([+-]\d+(?:\.\d+)?)", tz)
    if m:
        return (index - pd.Timedelta(hours=float(m.group(1)))).tz_localize("UTC")
    return index.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


# ---------------------------------------------------------------------------
# CSV 読み込み（形式自動判定）
# ---------------------------------------------------------------------------
def _find(cols, *cands):
    low = {c.lower().strip("<> ").replace(" ", "_"): c for c in cols}
    for c in cands:
        if c in low:
            return low[c]
    return None


def load_csv(path: str | os.PathLike, tz: str | None = None) -> pd.DataFrame:
    """1分足 CSV を読み込む。対応形式:

    - 本ツールの保存形式 / 一般的な OHLCV CSV（time, open, high, low, close, volume）
    - MT4/MT5 のエクスポート（<DATE> <TIME> <OPEN> ... タブ区切り）※ tz="NY+7" 等を指定
    - HistData.com ASCII M1（20240102 000000;open;high;low;close;vol）※ EST 固定(UTC-5)
    - Dukascopy CSV（"Gmt time" 列）
    """
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix == ".gz":
        import gzip

        raw = gzip.decompress(raw)
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text else ""

    # HistData: ヘッダなし、セミコロン区切り、"YYYYMMDD HHMMSS"
    if re.match(r"^\d{8} \d{6};", first):
        df = pd.read_csv(io.StringIO(text), sep=";", header=None,
                         names=["dt", "open", "high", "low", "close", "volume"])
        idx = pd.DatetimeIndex(pd.to_datetime(df["dt"], format="%Y%m%d %H%M%S"))
        df.index = localize_to_utc(idx, tz or "UTC-5")
        return clean_ohlcv(df[COLS])

    sep = "\t" if first.count("\t") >= 3 else (";" if first.count(";") >= 3 else ",")
    df = pd.read_csv(io.StringIO(text), sep=sep)
    cols = list(df.columns)
    c_date = _find(cols, "date")
    c_time = _find(cols, "time")
    c_dt = _find(cols, "datetime", "timestamp", "gmt_time", "time_utc", "date_time", "local_time")
    if c_dt is None and c_time is not None and c_date is None:
        c_dt = c_time
    if c_dt is not None:
        ts = df[c_dt].astype(str)
    elif c_date is not None and c_time is not None:
        ts = df[c_date].astype(str) + " " + df[c_time].astype(str)
    elif c_date is not None:
        ts = df[c_date].astype(str)
    else:
        raise ValueError(f"時刻列が見つかりません: {cols}")

    if ts.str.fullmatch(r"\d{9,13}").all():  # epoch
        unit = "ms" if ts.str.len().max() > 11 else "s"
        idx = pd.DatetimeIndex(pd.to_datetime(ts.astype("int64"), unit=unit, utc=True))
    else:
        ts = ts.str.replace(".", "-", n=2, regex=False) if ts.str.match(r"^\d{4}\.\d{2}\.\d{2}").all() else ts
        dayfirst = bool(ts.str.match(r"^\d{2}[./-]\d{2}[./-]\d{4}").all())
        idx = pd.DatetimeIndex(pd.to_datetime(ts, dayfirst=dayfirst, format="mixed"))
    if c_dt is not None and "gmt" in c_dt.lower() and idx.tz is None and tz is None:
        tz = "UTC"
    idx = localize_to_utc(idx, tz)

    out = pd.DataFrame(index=idx)
    for name, cands in {
        "open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"),
        "close": ("close", "c", "last", "price"),
        "volume": ("volume", "tick_volume", "tickvol", "vol", "real_volume", "v"),
    }.items():
        c = _find(cols, *cands)
        if c is None:
            if name == "volume":
                out[name] = 0.0
                continue
            if name in ("open", "high", "low") and _find(cols, "close", "price", "last"):
                continue
            raise ValueError(f"列 {name} が見つかりません: {cols}")
        out[name] = pd.to_numeric(df[c], errors="coerce").to_numpy()
    for name in ("open", "high", "low"):
        if name not in out:
            out[name] = out["close"]
    return clean_ohlcv(out[COLS])


def save_csv(df: pd.DataFrame, path: str | os.PathLike) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df[COLS].copy()
    out.index = out.index.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S")
    out.index.name = "time_utc"
    out.to_csv(path, float_format="%.5f", compression="gzip" if path.suffix == ".gz" else None)


# ---------------------------------------------------------------------------
# クリーニング
# ---------------------------------------------------------------------------
def clean_ohlcv(df: pd.DataFrame, spike_sigma: float = 25.0) -> pd.DataFrame:
    """重複・欠損・非正値・OHLC 不整合・単発スパイク（即座に戻る異常値）を除去する。"""
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("UTC").floor("min")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["close"])
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    df["volume"] = df["volume"].fillna(0.0)
    o, c = df["open"], df["close"]
    df["high"] = np.maximum.reduce([df["high"].to_numpy(), o.to_numpy(), c.to_numpy()])
    df["low"] = np.minimum.reduce([df["low"].to_numpy(), o.to_numpy(), c.to_numpy()])

    # 単発スパイク: 前後の足から大きく乖離し、すぐ戻る終値を中央値で置換
    if len(df) > 100:
        lc = np.log(df["close"].to_numpy())
        r = np.diff(lc)
        mad = np.median(np.abs(r - np.median(r))) * 1.4826 + 1e-12
        rin = np.r_[0.0, r]
        rout = np.r_[r, 0.0]
        spike = (np.abs(rin) > spike_sigma * mad) & (np.abs(rout) > spike_sigma * mad) & (np.sign(rin) == -np.sign(rout)) \
            & (np.abs(rin + rout) < 0.25 * np.abs(rin))
        if spike.any():
            prev = df["close"].shift(1)
            nxt = df["close"].shift(-1)
            fix = ((prev + nxt) / 2)[spike]
            df.loc[spike, "close"] = fix
            df.loc[spike, "open"] = prev[spike]
            df.loc[spike, "high"] = np.maximum(prev[spike], fix)
            df.loc[spike, "low"] = np.minimum(prev[spike], fix)
    return df[COLS].astype(float)


def merge(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return clean_ohlcv(new)
    return clean_ohlcv(pd.concat([old, new]))


# ---------------------------------------------------------------------------
# 合成データ（パイプライン検証用。金の 1 分足の統計的特徴を模したもの）
# ---------------------------------------------------------------------------
def market_open_mask(idx_utc: pd.DatetimeIndex) -> np.ndarray:
    """金スポットの標準的な取引時間（NY 日 18:00 〜 金 17:00、毎日 17:00-18:00 休止）。"""
    ny = idx_utc.tz_convert(NY)
    dow = ny.dayofweek.to_numpy()
    mod = (ny.hour * 60 + ny.minute).to_numpy()
    closed = (dow == 5) | ((dow == 4) & (mod >= 17 * 60)) | ((dow == 6) & (mod < 18 * 60)) \
        | ((mod >= 17 * 60) & (mod < 18 * 60))
    return ~closed


def synthetic(days: int = 420, seed: int = 7, start: str = "2025-01-05 22:00",
              p0: float = 2650.0, annual_vol: float = 0.17, drift_ann: float = 0.0) -> pd.DataFrame:
    """GARCH 的なボラティリティ・クラスタリング、日中季節性、指標発表スパイク、
    週末ギャップ、ファットテール、マイクロストラクチャ・ノイズを持つ合成 1 分足。"""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(pd.Timestamp(start, tz="UTC"), periods=days * 1440, freq="min")
    is_open = market_open_mask(idx)
    ny = idx.tz_convert(NY)
    dow = ny.dayofweek.to_numpy()
    mod = (ny.hour * 60 + ny.minute).to_numpy()
    dom = ny.day.to_numpy()
    n = len(idx)

    # 日中季節性（NY 時間）
    h = mod / 60.0
    prof = 0.55 + 0.35 * np.exp(-0.5 * ((h - 3.5) / 1.2) ** 2) + 1.1 * np.exp(-0.5 * ((h - 9.5) / 1.6) ** 2) \
        + 0.25 * np.exp(-0.5 * ((h - 20.5) / 1.5) ** 2)
    prof = prof.copy()
    prof[(mod == 8 * 60 + 30)] *= 6.0        # 08:30 指標発表
    prof[(mod > 8 * 60 + 30) & (mod < 8 * 60 + 40)] *= 2.0
    prof[(mod == 10 * 60)] *= 3.0             # 10:00 指標
    prof[(mod == 14 * 60)] *= 1.8
    nfp = (dow == 4) & (dom <= 7) & (mod == 8 * 60 + 30)
    prof[nfp] *= 4.0                          # 雇用統計
    prof[(dow == 6) & (mod >= 18 * 60) & (mod < 19 * 60)] *= 1.3

    # 日次ボラティリティ状態（対数 AR(1)）＋ 時間スケールの状態
    tday = ((ny + pd.Timedelta(hours=7)).normalize().as_unit("ns").asi8 // (86400 * 10**9)).astype(np.int64)
    tday -= tday.min()
    nd = tday.max() + 1
    lv = np.zeros(nd)
    for i in range(1, nd):
        lv[i] = 0.97 * lv[i - 1] + 0.16 * rng.standard_normal()
    hour_id = np.arange(n) // 60
    lh = np.zeros(hour_id.max() + 1)
    eps_h = rng.standard_normal(len(lh))
    for i in range(1, len(lh)):
        lh[i] = 0.9 * lh[i - 1] + 0.18 * eps_h[i]
    vol_state = np.exp(lv[tday] + lh[hour_id])

    minutes_per_year = 1380 * 5 * 52
    base = annual_vol / np.sqrt(minutes_per_year)
    sig = base * np.sqrt(prof) * vol_state / np.sqrt(np.mean(prof[is_open]))
    df_t = 4.0
    eps = rng.standard_t(df_t, size=n) / np.sqrt(df_t / (df_t - 2))
    r = np.where(is_open, sig * eps, 0.0) + np.where(is_open, drift_ann / minutes_per_year, 0.0)
    # 週明け最初の足のギャップ
    reopen = is_open & ~np.r_[False, is_open[:-1]]
    weekend_reopen = reopen & (dow == 6)
    r[weekend_reopen] += rng.standard_normal(weekend_reopen.sum()) * 0.004
    r[reopen & ~weekend_reopen] += rng.standard_normal((reopen & ~weekend_reopen).sum()) * base * 3

    eff = np.log(p0) + np.cumsum(r)
    # バー内の高値・安値（ブラウン橋の近似）
    rng_hl = np.abs(sig) * (0.6 + 0.6 * np.abs(rng.standard_normal(n)))
    noise = 0.3 * base * rng.standard_normal(n)  # ビッド・アスクの揺らぎ
    close = np.exp(eff + noise)
    open_ = np.r_[close[0], close[:-1]] * np.exp(0.2 * base * rng.standard_normal(n))
    open_[reopen] = np.exp(eff[reopen] - r[reopen] * 0.1)  # 再開足の始値にギャップを反映
    hi = np.maximum(open_, close) * np.exp(rng_hl * rng.uniform(0.1, 1.0, n))
    lo = np.minimum(open_, close) * np.exp(-rng_hl * rng.uniform(0.1, 1.0, n))
    vol = rng.poisson(40 * np.sqrt(prof) * vol_state) + 1
    df = pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close, "volume": vol.astype(float)}, index=idx)
    return df[is_open]
