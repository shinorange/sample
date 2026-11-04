"""XAUUSD 1分〜24時間先の確率的予測モデル。

構成:
  1. ボラティリティ: 日中季節性 f(週内の分) × 水準 L。L はホライズン別の HAR 回帰
     （過去 15分/1時間/4時間/1日/5日/21日 の脱季節化実現分散 + 非対称項）で予測。
     → 予測分散 σ_h² = L̂_h × Σ f(将来の各分)。週末・日次休場は自動的に分散ゼロ。
  2. 平均（方向）: 17 個の特徴量のリッジ回帰。時系列ホールドアウトで有意な
     予測力（t > ゲート閾値）が確認されたホライズンだけ採用し、傾きを較正。
     有意でなければドリフト 0（＝マーチンゲール）とする。
  3. 分布: 標準化残差の経験分布（Filtered Historical Simulation）で分位点・上昇確率。
  4. 経路: 1 分ショックのブロック・ブートストラップによるモンテカルロで、
     高値/安値・価格到達確率・先にどちらへ到達するか等の経路依存量を算出。
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .core import FEATURES, HORIZONS, WARMUP, FeatureSet, Grid, estimate_profile, horizon_label

QLEVELS = np.array([0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975, 0.99, 0.995])
TOUCH_PCTS = [0.1, 0.25, 0.5, 1.0, 2.0, 3.0]


@dataclass
class HorizonModel:
    h: int
    har_beta: np.ndarray
    smear: float
    har_resid_sd: float
    mean_beta: np.ndarray
    x_mu: np.ndarray
    x_sd: np.ndarray
    calib: float
    ic_val: float
    t_val: float
    active: bool
    z_sorted: np.ndarray
    naive_q: np.ndarray            # 無条件の h リターン分位点（ベンチマーク）
    naive_var: float
    n_train: int
    feature_importance: dict = field(default_factory=dict)


def _ridge(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    n, k = X.shape
    return np.linalg.solve(X.T @ X + lam * n * np.eye(k), X.T @ y)


class Forecaster:
    def __init__(self, horizons=None, stride: int = 5, ridge: float = 0.5, gate_t: float = 3.0):
        self.horizons = list(horizons or HORIZONS)
        self.stride = stride
        self.ridge = ridge
        self.gate_t = gate_t
        self.models: dict[int, HorizonModel] = {}
        self.profile: np.ndarray | None = None
        self.z1: np.ndarray | None = None
        self.fit_end: pd.Timestamp | None = None
        self.r2_scale: float = 0.0

    # ------------------------------------------------------------------ fit
    def fit(self, grid: Grid, end: int | None = None, verbose: bool = False) -> FeatureSet:
        end = grid.n if end is None else end
        if end - WARMUP < 20 * 1440:
            raise ValueError("学習データが不足しています（最低 約 41 日分の 1 分足が必要）")
        self.profile = estimate_profile(grid, end)
        fs = FeatureSet(grid, self.profile, end)
        self.r2_scale = fs.r2_scale
        self.fit_end = grid.idx[end - 1]
        cand = np.where(grid.is_open[:end])[0]
        cand = cand[cand >= WARMUP]

        # ブートストラップ用 1 分標準化ショック（時系列順）
        p1 = cand[cand < end - 1]
        p1 = p1[grid.is_open[p1 + 1]]
        q1 = p1 + 1
        sd1 = np.sqrt(self.profile[grid.slot[q1]] * np.maximum(fs.L[1440][p1], fs.eps))
        z1 = np.clip(grid.r[q1] / sd1, -40, 40)
        c = np.sqrt(np.mean(z1 ** 2))
        # バー内のヒゲ（高値・安値の終値からのはみ出し）も同じ時点で標準化して保存
        top = np.maximum(grid.logp[q1], grid.logp[p1])
        bot = np.minimum(grid.logp[q1], grid.logp[p1])
        wu = np.clip((np.log(grid.high[q1]) - top) / sd1, 0, 40) / c
        wd = np.clip((bot - np.log(grid.low[q1])) / sd1, 0, 40) / c
        self.z1 = (z1 / c)[-200_000:].astype(np.float32)
        self.wick_up = wu[-200_000:].astype(np.float32)
        self.wick_dn = wd[-200_000:].astype(np.float32)

        for h in self.horizons:
            pos = cand[cand + h < end][:: self.stride]
            Ff = fs.Cf[pos + h + 1] - fs.Cf[pos + 1]
            pos = pos[Ff > 0.05 * h]
            Ff = fs.Cf[pos + h + 1] - fs.Cf[pos + 1]
            RV = grid.Cr2[pos + h + 1] - grid.Cr2[pos + 1]
            ret = grid.logp[pos + h] - grid.logp[pos]

            # --- ボラティリティ（HAR, 対数）
            Xh = fs.har_matrix(pos)
            y = np.log(RV / Ff + fs.eps)
            bh = _ridge(Xh, y, 1e-6)
            res = y - Xh @ bh
            smear = float(np.mean(np.exp(res)))
            sigma = np.sqrt(np.exp(Xh @ bh) * smear * Ff)
            z = ret / sigma

            # --- 平均（リッジ + 時系列ホールドアウトによるゲート）
            Xm = fs.matrix(pos)
            mu, sd = Xm.mean(0), Xm.std(0) + 1e-12
            Xs = np.clip((Xm - mu) / sd, -6, 6)
            zt = np.clip(z, -10, 10)
            n = len(pos)
            cut = int(n * 0.75)
            emb = max(1, h // self.stride)
            b_tr = _ridge(Xs[:cut], zt[:cut] - zt[:cut].mean(), self.ridge)
            pv = Xs[cut + emb:] @ b_tr
            yv = zt[cut + emb:] - zt[:cut].mean()
            if len(pv) > 50 and pv.std() > 0:
                ic = float(np.corrcoef(pv, yv)[0, 1])
                n_eff = min(len(pv), len(pv) * self.stride / max(h, 1))
                tval = ic * np.sqrt(max(n_eff, 1))
                calib = float(np.clip(np.cov(pv, yv)[0, 1] / pv.var(), 0, 1))
            else:
                ic, tval, calib = 0.0, 0.0, 0.0
            active = bool(tval > self.gate_t and ic > 0)
            b_full = _ridge(Xs, zt - zt.mean(), self.ridge)
            mu_z = (Xs @ b_full) * calib if active else np.zeros(n)
            zr = z - mu_z
            zr = zr - zr.mean()  # 標本期間のトレンドを暗黙のドリフトとして持ち込まない
            zs = np.sort(zr)
            if len(zs) > 20000:
                zs = zs[np.linspace(0, len(zs) - 1, 20000).astype(int)]
            imp = {k: float(v) for k, v in zip(FEATURES, b_full * (calib if active else 0.0))}

            self.models[h] = HorizonModel(
                h=h, har_beta=bh, smear=smear, har_resid_sd=float(res.std()), mean_beta=b_full,
                x_mu=mu, x_sd=sd, calib=calib, ic_val=ic, t_val=float(tval), active=active,
                z_sorted=zs.astype(np.float32), naive_q=np.quantile(ret, QLEVELS),
                naive_var=float(np.mean(ret ** 2)), n_train=n, feature_importance=imp)
            if verbose:
                print(f"  h={horizon_label(h):>5}: n={n:6d}  HAR残差sd={res.std():.3f}  "
                      f"方向IC(検証)={ic:+.4f} t={tval:+.2f} {'採用' if active else '不採用(ドリフト0)'}", flush=True)
        return fs

    # ------------------------------------------------------------- predict
    def predict_batch(self, fs: FeatureSet, pos: np.ndarray) -> dict[int, dict[str, np.ndarray]]:
        pos = np.asarray(pos, dtype=np.int64)
        Xh = fs.har_matrix(pos)
        Xm = fs.matrix(pos)
        out = {}
        for h, m in self.models.items():
            Ff = fs.future_fsum(pos, h)
            L = np.exp(Xh @ m.har_beta) * m.smear
            sigma = np.sqrt(L * Ff)
            if m.active:
                mu_z = (np.clip((Xm - m.x_mu) / m.x_sd, -6, 6) @ m.mean_beta) * m.calib
            else:
                mu_z = np.zeros(len(pos))
            zq = np.quantile(m.z_sorted, QLEVELS)
            q = sigma[:, None] * (mu_z[:, None] + zq[None, :])
            zs = m.z_sorted
            n = len(zs)
            p_up = (n - np.searchsorted(zs, -mu_z, side="right")) / n
            p_dn = np.searchsorted(zs, -mu_z, side="left") / n
            out[h] = dict(sigma=sigma, mu=mu_z * sigma, mu_z=mu_z, q=q, p_up=p_up, p_down=p_dn, L=L, Ff=Ff)
        return out

    def simulate(self, fs: FeatureSet, pos: int, pred: dict, n_paths: int = 2000, H: int = 1440,
                 block: int = 30, seed: int | None = None):
        """将来 H 分のパスを生成。戻り値 (close, high, low) はいずれも p0 からの累積対数リターン
        で shape=(n_paths, H)。high/low はバー内のヒゲを含む。"""
        rng = np.random.default_rng(seed)
        f = fs.fpath(pos, H)
        Fc = np.concatenate([[0.0], np.cumsum(f)])
        hs = [h for h in sorted(self.models) if h <= H]
        lvl = np.empty(H)
        prev_h, prev_v = 0, 0.0
        for h in hs:
            v = float(pred[h]["sigma"][0] ** 2)
            dF = Fc[h] - Fc[prev_h]
            seg = (v - prev_v) / dF if dF > 1e-9 else float(pred[h]["L"][0])
            lvl[prev_h:h] = seg
            prev_h, prev_v = h, v
        lvl[prev_h:] = float(pred[hs[-1]]["L"][0])
        ref = float(pred[hs[-1]]["L"][0])
        lvl = np.clip(lvl, 0.2 * ref, 5.0 * ref)
        sd_min = np.sqrt(lvl * f)

        # ドリフト（ホライズン別の平均を線形補間）
        mh = np.array([0] + hs, dtype=float)
        mv = np.array([0.0] + [float(pred[h]["mu"][0]) for h in hs])
        cum_mu = np.interp(np.arange(1, H + 1), mh, mv)
        dmu = np.diff(np.concatenate([[0.0], cum_mu]))

        nb = int(np.ceil(H / block))
        starts = rng.integers(0, len(self.z1) - block, size=(n_paths, nb))
        ix = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_paths, -1)[:, :H]
        # ボラティリティ水準の不確実性（パスごとの倍率、期待分散は保存）
        s = float(np.sqrt(max(self.models[max(hs)].har_resid_sd ** 2 - 0.05, 0.0)))
        scale = np.sqrt(np.exp(s * rng.standard_normal(n_paths) - s * s / 2))[:, None] * sd_min[None, :]
        close = np.cumsum(self.z1[ix] * scale + dmu[None, :], axis=1)
        prev = np.concatenate([np.zeros((n_paths, 1)), close[:, :-1]], axis=1)
        high = np.maximum(prev, close) + self.wick_up[ix] * scale
        low = np.minimum(prev, close) - self.wick_dn[ix] * scale
        return close, high, low

    def forecast(self, grid: Grid, fs: FeatureSet, pos: int | None = None, n_paths: int = 3000,
                 seed: int | None = 0) -> dict:
        """1 時点の完全な予測（分位点・方向確率・高安・到達確率・ファンチャート用データ）。"""
        pos = grid.n - 1 if pos is None else pos
        p0 = float(grid.close[pos])
        t0 = grid.idx[pos]
        pred = self.predict_batch(fs, np.array([pos]))
        H = max(self.models)
        paths, phigh, plow = self.simulate(fs, pos, pred, n_paths=n_paths, H=H, seed=seed)
        price_paths = p0 * np.exp(paths)
        run_max = p0 * np.exp(np.maximum.accumulate(phigh, axis=1))
        run_min = p0 * np.exp(np.minimum.accumulate(plow, axis=1))
        del phigh, plow

        open_cum = np.cumsum(fs.fpath(pos, H) > 0.02)  # 将来の各分が取引時間帯か（季節性から推定）
        hz = []
        for h in sorted(self.models):
            m = self.models[h]
            d = pred[h]
            qp = p0 * np.exp(d["q"][0])
            hi = run_max[:, h - 1]
            lo = run_min[:, h - 1]
            hz.append({
                "h": h, "label": horizon_label(h), "target_time_utc": str(t0 + pd.Timedelta(minutes=h)),
                "sigma_pct": float(d["sigma"][0] * 100), "sigma_usd": float(p0 * d["sigma"][0]),
                "drift_pct": float(d["mu"][0] * 100), "drift_usd": float(p0 * np.expm1(d["mu"][0])),
                "trading_minutes": int(open_cum[h - 1]),
                "mean_model_active": m.active, "mean_model_t": m.t_val,
                "median": float(qp[QLEVELS.tolist().index(0.5)]),
                "quantiles": {f"{q:g}": float(v) for q, v in zip(QLEVELS, qp)},
                "p_up": float(d["p_up"][0]), "p_down": float(d["p_down"][0]),
                "p_flat": float(max(0.0, 1 - d["p_up"][0] - d["p_down"][0])),
                "expected_high": float(np.median(hi)), "expected_low": float(np.median(lo)),
                "high_q90": float(np.quantile(hi, 0.9)), "low_q10": float(np.quantile(lo, 0.1)),
                "expected_range_usd": float(np.median(hi - lo)),
                "vol_level_vs_normal": float(d["L"][0] / self.r2_scale),
            })

        touch = []
        for pct in TOUCH_PCTS:
            up_lv, dn_lv = p0 * (1 + pct / 100), p0 * (1 - pct / 100)
            hit_up = run_max >= up_lv
            hit_dn = run_min <= dn_lv
            row = {"pct": pct, "usd": p0 * pct / 100, "up_level": up_lv, "down_level": dn_lv}
            for h in (60, 240, 1440):
                if h <= H:
                    row[f"p_up_{h}"] = float(hit_up[:, h - 1].mean())
                    row[f"p_down_{h}"] = float(hit_dn[:, h - 1].mean())
            tu = np.where(hit_up.any(1), hit_up.argmax(1), H + 1)
            td = np.where(hit_dn.any(1), hit_dn.argmax(1), H + 1)
            both = (tu <= H) | (td <= H)
            row["p_up_first"] = float(np.mean(tu[both] < td[both])) if both.any() else float("nan")
            row["median_minutes_to_up"] = float(np.median(tu[tu <= H]) + 1) if (tu <= H).any() else None
            row["median_minutes_to_down"] = float(np.median(td[td <= H]) + 1) if (td <= H).any() else None
            touch.append(row)

        step = 5
        mins = np.arange(step, H + 1, step)
        fan = {"minutes": mins.tolist()}
        for q in (0.05, 0.25, 0.5, 0.75, 0.95):
            fan[f"{q:g}"] = np.quantile(price_paths[:, mins - 1], q, axis=0).round(3).tolist()

        hist_n = 360
        lo_i = max(0, pos - hist_n + 1)
        hist = {"minutes": (np.arange(lo_i, pos + 1) - pos).tolist(), "close": grid.close[lo_i:pos + 1].round(3).tolist()}

        return {
            "symbol": "XAUUSD", "origin_utc": str(t0), "origin_ny": str(t0.tz_convert("America/New_York")),
            "origin_tokyo": str(t0.tz_convert("Asia/Tokyo")), "price": p0,
            "model_trained_until": str(self.fit_end), "data_last_bar_utc": str(grid.idx[grid.n - 1]),
            "horizons": hz, "touch": touch, "fan": fan, "history": hist,
        }

    # ------------------------------------------------------------- persistence
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh)

    @staticmethod
    def load(path: str | Path) -> "Forecaster":
        with open(path, "rb") as fh:
            return pickle.load(fh)
