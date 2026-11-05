"""外部データソースからの XAUUSD 1 分足取得。

- dukascopy : Dukascopy の無料ヒストリカル・フィード（APIキー不要、2003年〜）。
              完了した日は 1 分足ファイル、当日分はティック（1 時間単位）から集計。
              ※ 通常 数十分〜1時間程度の遅延があります。
- mt5       : MetaTrader5 ターミナル（Windows、pip install MetaTrader5）。リアルタイム。
- csv       : 手元の CSV（MT4/MT5 エクスポート、HistData 等）を追記読み込み。
"""
from __future__ import annotations

import lzma
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data import COLS, clean_ohlcv, load_csv, localize_to_utc

DUKA_URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/"
UA = {"User-Agent": "Mozilla/5.0 (xauforecast research tool)"}


def _get(url: str, retries: int = 4) -> bytes | None:
    import requests

    for i in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r.content
        except requests.RequestException:
            pass
        time.sleep(2 ** i)
    raise RuntimeError(f"取得失敗: {url}")


def _decode_candles(blob: bytes, day: datetime, point: float) -> pd.DataFrame:
    if not blob:
        return pd.DataFrame(columns=COLS)
    data = lzma.decompress(blob)
    n = len(data) // 24
    arr = np.frombuffer(data[: n * 24], dtype=">i4").reshape(n, 6).astype(np.int64)
    vol = np.frombuffer(data[: n * 24], dtype=">f4").reshape(n, 6)[:, 5].astype(float)
    t = arr[:, 0]
    p = arr[:, 1:5] / point
    # フィールド順は time, open, close, low, high, volume。念のため整合性で検証して自動補正。
    best, best_score = (0, 1, 2, 3), -1
    for perm in [(0, 1, 2, 3), (0, 3, 2, 1), (0, 2, 1, 3), (0, 1, 3, 2)]:
        o, c, lo, hi = (p[:, i] for i in perm)
        score = np.mean((hi >= np.maximum(o, c) - 1e-9) & (lo <= np.minimum(o, c) + 1e-9))
        if score > best_score:
            best, best_score = perm, score
    o, c, lo, hi = (p[:, i] for i in best)
    idx = pd.DatetimeIndex(pd.to_datetime(day.timestamp() + t, unit="s", utc=True))
    df = pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": vol}, index=idx)
    return df[df["volume"] > 0]  # 休場中のフラット足を除外


def _decode_ticks(blob: bytes, hour: datetime, point: float) -> pd.DataFrame:
    if not blob:
        return pd.DataFrame(columns=COLS)
    data = lzma.decompress(blob)
    n = len(data) // 20
    if n == 0:
        return pd.DataFrame(columns=COLS)
    rec = np.frombuffer(data[: n * 20], dtype=np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"),
                                                         ("av", ">f4"), ("bv", ">f4")]))
    ts = pd.to_datetime(hour.timestamp() * 1000 + rec["ms"].astype(np.int64), unit="ms", utc=True)
    mid = (rec["ask"].astype(float) + rec["bid"].astype(float)) / 2 / point
    s = pd.Series(mid, index=ts)
    g = s.resample("1min")
    df = pd.DataFrame({"open": g.first(), "high": g.max(), "low": g.min(), "close": g.last(), "volume": g.count().astype(float)})
    return df.dropna()


def fetch_dukascopy(start: str | datetime, end: str | datetime | None = None, symbol: str = "XAUUSD",
                    point: float = 1000.0, side: str = "BID", cache_dir: str | Path = ".cache/dukascopy",
                    workers: int = 4, verbose: bool = True) -> pd.DataFrame:
    """Dukascopy から [start, end] の 1 分足を取得（日単位でキャッシュ）。"""
    start = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end = pd.Timestamp.now(tz="UTC") if end is None else (
        pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC"))
    cache = Path(cache_dir) / symbol
    cache.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now(tz="UTC").normalize()
    days = pd.date_range(start.normalize(), end.normalize(), freq="D")

    def one_day(d: pd.Timestamp) -> pd.DataFrame:
        if d.dayofweek == 5:  # 土曜は休場
            return pd.DataFrame(columns=COLS)
        base = DUKA_URL.format(sym=symbol, y=d.year, m=d.month - 1, d=d.day)
        if d < today:
            f = cache / f"{d:%Y%m%d}_{side}.pkl"
            if f.exists():
                return pd.read_pickle(f)
            blob = _get(base + f"{side}_candles_min_1.bi5")
            df = _decode_candles(blob or b"", d.to_pydatetime(), point)
            df.to_pickle(f)
            return df
        # 当日: 1 時間ごとのティックファイルから集計（キャッシュしない）
        parts = []
        for hh in range(0, pd.Timestamp.now(tz="UTC").hour + 1):
            blob = _get(base + f"{hh:02d}h_ticks.bi5")
            parts.append(_decode_ticks(blob or b"", (d + pd.Timedelta(hours=hh)).to_pydatetime(), point))
        parts = [p for p in parts if len(p)]
        return pd.concat(parts) if parts else pd.DataFrame(columns=COLS)

    out = []
    with ThreadPoolExecutor(workers) as ex:
        for i, df in enumerate(ex.map(one_day, days)):
            if len(df):
                out.append(df)
            if verbose and (i % 30 == 0 or i == len(days) - 1):
                print(f"  dukascopy {days[i]:%Y-%m-%d} ({i + 1}/{len(days)})", flush=True)
    if not out:
        raise RuntimeError("Dukascopy からデータが取得できませんでした")
    df = pd.concat(out)
    df = df[(df.index >= start) & (df.index <= end)]
    return clean_ohlcv(df)


def fetch_mt5(symbol: str = "XAUUSD", start: str | None = None, bars: int = 400_000,
              server_tz: str = "NY+7") -> pd.DataFrame:
    """MetaTrader5 ターミナルから 1 分足を取得（Windows）。

    MT5 の時刻はブローカーのサーバー時間。多くのブローカーは NY+7（夏時間連動の UTC+2/+3）。
    """
    import MetaTrader5 as mt5  # type: ignore

    if not mt5.initialize():
        raise RuntimeError(f"MT5 初期化失敗: {mt5.last_error()}")
    try:
        mt5.symbol_select(symbol, True)
        if start:
            s = pd.Timestamp(start).to_pydatetime().replace(tzinfo=timezone.utc)
            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, s, datetime.now(timezone.utc) + timedelta(days=1))
        else:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars)
    finally:
        mt5.shutdown()
    if rates is None or len(rates) == 0:
        raise RuntimeError("MT5 からデータが取得できませんでした")
    df = pd.DataFrame(rates)
    idx = pd.DatetimeIndex(pd.to_datetime(df["time"], unit="s"))  # サーバー時間（naive として扱う）
    df.index = localize_to_utc(idx, server_tz)
    df = df.rename(columns={"tick_volume": "volume"})
    return clean_ohlcv(df[COLS])


def fetch(source: str, **kw) -> pd.DataFrame:
    if source == "dukascopy":
        return fetch_dukascopy(**kw)
    if source == "mt5":
        return fetch_mt5(**kw)
    if source == "csv":
        return load_csv(kw["path"], tz=kw.get("tz"))
    raise ValueError(f"unknown source: {source}")
