"""時間グリッド、日中季節性プロファイル、特徴量の計算。

すべての計算は「1 分刻みの時計時間グリッド」上で行う。休場中は直前の終値を保持
（リターン 0）、再開最初の分にギャップが乗る。予測ホライズンは時計時間で定義される
ため、「24 時間後」が週末を跨ぐ場合も正しく扱える。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
HORIZONS = [1, 5, 15, 30, 60, 120, 240, 480, 720, 1440]
HAR_WINDOWS = [15, 60, 240, 1440, 7200, 30240]
WARMUP = 30240 + 10
WEEK = 10080


def horizon_label(h: int) -> str:
    return f"{h}分" if h < 60 else f"{h // 60}時間"


def slots_of(index_utc: pd.DatetimeIndex) -> np.ndarray:
    """NY 時間の「週内の分」(0=月曜 0:00 … 10079=日曜 23:59)。夏時間を自動処理。"""
    ny = index_utc.tz_convert(NY)
    return (ny.dayofweek.to_numpy() * 1440 + ny.hour.to_numpy() * 60 + ny.minute.to_numpy()).astype(np.int64)


class Grid:
    """1 分グリッド上の価格系列。"""

    def __init__(self, df: pd.DataFrame):
        if len(df) < 10:
            raise ValueError("データが少なすぎます")
        idx = pd.date_range(df.index[0], df.index[-1], freq="min")
        g = df.reindex(idx)
        self.df = df
        self.idx = idx
        self.n = len(idx)
        self.is_open = g["close"].notna().to_numpy()
        close = g["close"].ffill().to_numpy()
        self.close = close
        self.high = g["high"].fillna(g["close"].ffill()).to_numpy()
        self.low = g["low"].fillna(g["close"].ffill()).to_numpy()
        self.open = g["open"].fillna(g["close"].ffill()).to_numpy()
        self.volume = g["volume"].fillna(0.0).to_numpy()
        self.logp = np.log(close)
        r = np.diff(self.logp, prepend=self.logp[0])
        self.r = r
        self.slot = slots_of(idx)
        ny = idx.tz_convert(NY)
        self.mod = (ny.hour.to_numpy() * 60 + ny.minute.to_numpy()).astype(np.int64)
        self.dow = ny.dayofweek.to_numpy()
        td = (ny + pd.Timedelta(hours=7)).normalize()
        self.tday = pd.factorize(td)[0]
        self.tday_dates = pd.DatetimeIndex(pd.unique(td)).tz_localize(None).date
        self.Cr2 = np.concatenate([[0.0], np.cumsum(r ** 2)])  # Cr2[i+1] = sum r2[0..i]

    def pos_of(self, ts) -> int:
        ts = pd.Timestamp(ts)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        p = int(self.idx.searchsorted(ts.floor("min"), side="right") - 1)
        if p < 0:
            raise ValueError("指定時刻がデータ範囲外です")
        # 直近の取引足まで戻す
        while p > 0 and not self.is_open[p]:
            p -= 1
        return p

    def window_sum(self, C: np.ndarray, pos: np.ndarray, w: int) -> np.ndarray:
        """(pos-w, pos] の和。C は長さ n+1 の累積和。"""
        a = np.clip(pos + 1 - w, 0, None)
        return C[pos + 1] - C[a]


# ---------------------------------------------------------------------------
# 日中季節性プロファイル（週内の分ごとの分散比）
# ---------------------------------------------------------------------------
def estimate_profile(grid: Grid, end: int | None = None, K: float = 30.0, cap: float = 400.0) -> np.ndarray:
    """f[slot] = E[r^2 / 局所ボラ水準 | slot]。週内 10080 スロット、5 分ブロック平均へ縮小推定。

    end: この位置より前のデータだけを使う（バックテストでの先読み防止）。
    """
    end = grid.n if end is None else end
    r2 = grid.r[:end] ** 2
    op = grid.is_open[:end]
    slot = grid.slot[:end]
    lvl_open = pd.Series(r2[op]).rolling(1380, min_periods=200).mean().bfill().to_numpy()
    lvl_open = np.maximum(lvl_open, np.nanmedian(lvl_open) * 1e-3 + 1e-18)
    u = np.zeros(end)
    u[op] = np.minimum(r2[op] / lvl_open, cap)
    sums = np.bincount(slot, weights=u, minlength=WEEK)
    cnt = np.bincount(slot, minlength=WEEK).astype(float)
    f_slot = sums / np.maximum(cnt, 1)
    blk = np.arange(WEEK) // 5
    bs = np.bincount(blk, weights=sums, minlength=WEEK // 5)
    bc = np.bincount(blk, weights=cnt, minlength=WEEK // 5)
    f_blk = (bs / np.maximum(bc, 1))[blk]
    f = (cnt * f_slot + K * f_blk) / (cnt + K)
    f = f / max(np.mean(f[slot]), 1e-12)
    return np.maximum(f, 1e-6)


# ---------------------------------------------------------------------------
# 特徴量
# ---------------------------------------------------------------------------
class FeatureSet:
    """グリッド全体の特徴量（過去データのみ使用）を計算して保持する。

    end / vprofile / r2_scale は学習時の値を渡す（予測時も学習時と同じ尺度で計算するため）。
    """

    def __init__(self, grid: Grid, f: np.ndarray, end: int | None = None, events=None,
                 vprofile: np.ndarray | None = None, r2_scale: float | None = None):
        from .features import compute_features, volume_profile

        self.grid = grid
        self.f = f
        fs = f[grid.slot]
        self.Cf = np.concatenate([[0.0], np.cumsum(fs)])
        end = grid.n if end is None else end
        self.r2_scale = r2_scale or (float(np.mean(grid.r[:end][grid.is_open[:end]] ** 2)) + 1e-18)
        self.eps = 1e-3 * self.r2_scale
        self.vprofile = volume_profile(grid, end) if vprofile is None else vprofile
        pos = np.arange(grid.n)
        self.L = {}
        for w in HAR_WINDOWS:
            num = grid.window_sum(grid.Cr2, pos, w)
            den = grid.window_sum(self.Cf, pos, w)
            self.L[w] = num / (den + 0.02 * w)
        self.X, self.groups = compute_features(grid, f, self.Cf, self.L, self.eps, self.vprofile, events)
        self.names = list(self.X)

    def matrix(self, pos: np.ndarray, names: list[str] | None = None) -> np.ndarray:
        names = self.names if names is None else names
        return np.column_stack([self.X[k][pos] for k in names]).astype(np.float64)

    def har_matrix(self, pos: np.ndarray) -> np.ndarray:
        cols = [np.ones(len(pos))]
        for w in HAR_WINDOWS:
            cols.append(np.log(self.L[w][pos] + self.eps))
        n1440 = self.X["nr_1440"][pos].astype(np.float64)
        cols.append(np.clip(n1440, 0, None))
        cols.append(np.clip(n1440, None, 0))
        cols.append(np.abs(self.X["nr_60"][pos].astype(np.float64)))
        return np.column_stack(cols)

    # 将来区間 (pos, pos+h] の季節性の和。グリッド外（将来）は時刻から計算。
    def future_fsum(self, pos: np.ndarray, h: int) -> np.ndarray:
        g = self.grid
        pos = np.asarray(pos)
        out = np.empty(len(pos))
        inside = pos + h < g.n
        out[inside] = self.Cf[pos[inside] + h + 1] - self.Cf[pos[inside] + 1]
        for i in np.where(~inside)[0]:
            out[i] = self.fpath(int(pos[i]), h).sum()
        return out

    def fpath(self, pos: int, h: int) -> np.ndarray:
        t0 = self.grid.idx[pos]
        fut = pd.date_range(t0 + pd.Timedelta(minutes=1), periods=h, freq="min")
        return self.f[slots_of(fut)]
