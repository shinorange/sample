"""XAUUSD 1分〜24時間先の確率的予測モデル（全特徴量アンサンブル版）。

構成（ホライズンごと）:
  1. ボラティリティ
     - 日中季節性 f(週内の分) × 水準 L。L はまず HAR 回帰（過去 15分〜21日の脱季節化実現分散）で予測し、
     - 約 150 個の全特徴量を使う勾配ブースティングで HAR の残差を補正する。
       交差適合（時系列ブロック + エンバーゴ）で検証し、改善した場合だけ使用・縮小推定。
     → 予測分散 σ_h² = L̂_h × Σ f(将来の各分)。週末・日次休場は自動的に分散ゼロ。
  2. 平均（方向）… 4 つの予測器をスタッキング
     - 線形（リッジ、全特徴量） / 勾配ブースティング（全特徴量）
     - 類似局面（kNN、主要 28 特徴量で過去の似た局面を探し、その後の値動きを平均）
     - 時間帯統計（週内の時間帯ごとの平均リターン）
     各予測器は交差適合の検証で t > ゲート閾値 のときだけ採用し、非負最小二乗で重み付け。
     どれも有意でなければドリフト 0（＝マーチンゲール）。
  3. 分布: 交差適合の標準化残差（ボラ局面別のプール）で分位点・上昇確率（FHS）。
  4. 経路: 1 分ショック + ヒゲのブロック・ブートストラップ（モンテカルロ）で高安・到達確率。
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from scipy.stats import rankdata

from .core import HORIZONS, WARMUP, FeatureSet, Grid, estimate_profile, horizon_label
from .features import ANALOG_FEATURES

QLEVELS = np.array([0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975, 0.99, 0.995])
TOUCH_PCTS = [0.1, 0.25, 0.5, 1.0, 2.0, 3.0]
COMPONENTS = ["ridge", "gbm", "analog", "season"]
COMP_LABEL = {"ridge": "線形(リッジ)", "gbm": "勾配ブースティング", "analog": "類似局面(kNN)", "season": "時間帯統計"}
REGIME_FEATURE = "vr_60_1440"


def _ridge(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    n, k = X.shape
    return np.linalg.solve(X.T @ X + lam * n * np.eye(k), X.T @ y)


def _gbm(seed: int = 0):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(max_iter=120, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=400,
                                         l2_regularization=1.0, random_state=seed)


def _sub(idx: np.ndarray, cap: int) -> np.ndarray:
    return idx if len(idx) <= cap else idx[np.linspace(0, len(idx) - 1, cap).astype(int)]


def _ic_t(p: np.ndarray, y: np.ndarray, n_eff: float) -> tuple[float, float]:
    if len(p) < 50 or np.std(p) == 0 or np.std(y) == 0:
        return 0.0, 0.0
    ic = float(np.corrcoef(p, y)[0, 1])
    return ic, float(ic * np.sqrt(max(n_eff, 1.0)))


@dataclass
class HorizonModel:
    h: int
    har_beta: np.ndarray
    vol_gbm: object | None
    vol_gbm_scale: float
    vol_gain_pct: float
    smear: float
    har_resid_sd: float
    comp_weights: dict
    comp_stats: dict
    ridge_beta: np.ndarray
    gbm_mean: object | None
    season_table: np.ndarray
    active: bool
    ic_val: float
    t_val: float
    z_pools: list
    regime_cuts: np.ndarray
    naive_q: np.ndarray
    naive_var: float
    n_train: int
    feature_ic: dict = field(default_factory=dict)


class Forecaster:
    def __init__(self, horizons=None, stride: int = 5, ridge: float = 1.0, gate_t: float = 3.0, n_folds: int = 3,
                 use_gbm: bool = True, knn_k: int = 150, gbm_rows: int = 30000):
        self.horizons = list(horizons or HORIZONS)
        self.stride = stride
        self.ridge = ridge
        self.gate_t = gate_t
        self.n_folds = n_folds
        self.use_gbm = use_gbm
        self.knn_k = knn_k
        self.gbm_rows = gbm_rows
        self.models: dict[int, HorizonModel] = {}
        self.profile = None
        self.z1 = None
        self.fit_end = None
        self.r2_scale = 0.0
        self.events = None

    # ------------------------------------------------------------------ features
    def make_features(self, grid: Grid) -> FeatureSet:
        return FeatureSet(grid, self.profile, events=self.events, vprofile=self.vprofile, r2_scale=self.r2_scale)

    def _std(self, X: np.ndarray) -> np.ndarray:
        return np.clip((X - self.x_mu) / self.x_sd, -6, 6)

    # ------------------------------------------------------------------ fit
    def fit(self, grid: Grid, end: int | None = None, verbose: bool = False, events=None) -> FeatureSet:
        from sklearn.neighbors import NearestNeighbors

        end = grid.n if end is None else end
        H = max(self.horizons)
        if end - WARMUP - H < 20 * 1440:
            raise ValueError("学習データが不足しています（最低 約 42 日分の 1 分足が必要）")
        self.events = events
        self.profile = estimate_profile(grid, end)
        fs = FeatureSet(grid, self.profile, end, events)
        self.r2_scale, self.vprofile = fs.r2_scale, fs.vprofile
        self.feature_names, self.feature_groups = fs.names, fs.groups
        self.fit_end = grid.idx[end - 1]
        cand = np.where(grid.is_open[:end])[0]
        cand = cand[cand >= WARMUP]
        self._fit_shocks(grid, fs, cand, end)

        P = cand[cand + H < end][:: self.stride]
        n = len(P)
        X = fs.matrix(P)
        self.x_mu, self.x_sd = X.mean(0), X.std(0) + 1e-9
        Xs = self._std(X)
        del X
        Xh = fs.har_matrix(P)
        self.aidx = [self.feature_names.index(k) for k in ANALOG_FEATURES if k in self.feature_names]
        A = Xs[:, self.aidx].astype(np.float32)
        how = grid.slot[P] // 60
        reg_col = Xs[:, self.feature_names.index(REGIME_FEATURE)]
        # 特徴量の分位（現在値が過去のどの位置かを示すため）
        self.feature_pct_grid = np.quantile(Xs[:: max(1, n // 20000)], np.linspace(0, 1, 101), axis=0).astype(np.float32)
        Rx = np.apply_along_axis(rankdata, 0, Xs[:: max(1, n // 30000)]) if n > 0 else None
        rx_rows = np.arange(n)[:: max(1, n // 30000)]

        # 時系列ブロックの交差適合（ラベル期間が重なる学習行は除外 = エンバーゴ）
        blocks = np.array_split(np.arange(n), self.n_folds)
        folds = []
        for b in blocks:
            lo, hi = P[b[0]] - H - 1, P[b[-1]] + H + 1
            folds.append((np.where((P < lo) | (P > hi))[0], b))
        nbr_oof = np.zeros((n, self.knn_k), dtype=np.int64)
        for tr, te in folds:
            trs = _sub(tr, 60000)
            nn = NearestNeighbors(n_neighbors=self.knn_k).fit(A[trs])
            nbr_oof[te] = trs[nn.kneighbors(A[te], return_distance=False)]
        fin = _sub(np.arange(n), 60000)
        self._nn = NearestNeighbors(n_neighbors=self.knn_k).fit(A[fin])
        self.analog = {"A_rows": fin, "time": grid.idx[P[fin]].as_unit("ns").asi8, "z": {}, "ret": {}}

        for h in self.horizons:
            hm = self._fit_horizon(grid, fs, h, P, Xs, Xh, folds, nbr_oof, how, reg_col, Rx, rx_rows, verbose)
            self.models[h] = hm
        return fs

    def _fit_shocks(self, grid, fs, cand, end):
        p1 = cand[cand < end - 1]
        p1 = p1[grid.is_open[p1 + 1]]
        q1 = p1 + 1
        sd1 = np.sqrt(self.profile[grid.slot[q1]] * np.maximum(fs.L[1440][p1], fs.eps))
        z1 = np.clip(grid.r[q1] / sd1, -40, 40)
        c = np.sqrt(np.mean(z1 ** 2))
        top = np.maximum(grid.logp[q1], grid.logp[p1])
        bot = np.minimum(grid.logp[q1], grid.logp[p1])
        self.z1 = (z1 / c)[-200_000:].astype(np.float32)
        self.wick_up = (np.clip((np.log(grid.high[q1]) - top) / sd1, 0, 40) / c)[-200_000:].astype(np.float32)
        self.wick_dn = (np.clip((bot - np.log(grid.low[q1])) / sd1, 0, 40) / c)[-200_000:].astype(np.float32)

    def _fit_horizon(self, grid, fs, h, P, Xs, Xh, folds, nbr_oof, how, reg_col, Rx, rx_rows, verbose) -> HorizonModel:
        n = len(P)
        Ff = fs.Cf[P + h + 1] - fs.Cf[P + 1]
        valid = Ff > 0.05 * h
        RV = grid.Cr2[P + h + 1] - grid.Cr2[P + 1]
        ret = grid.logp[P + h] - grid.logp[P]
        y = np.log(RV / np.maximum(Ff, 1e-9) + fs.eps)
        n_eff_scale = min(1.0, self.stride / max(h, 1))

        # ---------------- ボラ: HAR + GBM 残差補正（交差適合）
        har_oof = np.zeros(n)
        gv_oof = np.zeros(n)
        for k, (tr, te) in enumerate(folds):
            trv = tr[valid[tr]]
            b = _ridge(Xh[trv], y[trv], 1e-6)
            har_oof[te] = Xh[te] @ b
            if self.use_gbm:
                s = _sub(trv, self.gbm_rows)
                m = _gbm(k).fit(Xs[s], y[s] - Xh[s] @ b)
                gv_oof[te] = m.predict(Xs[te])
        v = valid
        e0 = y[v] - har_oof[v]
        scale, gain = 0.0, 0.0
        if self.use_gbm and np.var(gv_oof[v]) > 0:
            scale = float(np.clip(np.cov(e0, gv_oof[v])[0, 1] / np.var(gv_oof[v]), 0, 1))
            gain = float(1 - np.mean((e0 - scale * gv_oof[v]) ** 2) / np.mean(e0 ** 2))
        use_vg = gain > 0.005
        lhat_oof = har_oof + (scale * gv_oof if use_vg else 0.0)
        res = y[v] - lhat_oof[v]
        smear = float(np.mean(np.exp(res)))
        sigma_oof = np.sqrt(np.exp(lhat_oof) * smear * np.maximum(Ff, 1e-9))
        b_full = _ridge(Xh[v], y[v], 1e-6)
        vol_gbm = None
        if use_vg:
            s = _sub(np.where(v)[0], self.gbm_rows)
            vol_gbm = _gbm(99).fit(Xs[s], y[s] - Xh[s] @ b_full)

        # ---------------- 平均: 4 予測器の交差適合 → スタッキング
        z = ret / sigma_oof
        zt = np.clip(z, -10, 10)
        zt = zt - zt[v].mean()
        zt_nan = np.where(v, zt, np.nan)
        comps = {c: np.zeros(n) for c in COMPONENTS}
        for k, (tr, te) in enumerate(folds):
            trv = tr[v[tr]]
            beta = _ridge(Xs[trv], zt[trv], self.ridge)
            comps["ridge"][te] = Xs[te] @ beta
            if self.use_gbm:
                s = _sub(trv, self.gbm_rows)
                comps["gbm"][te] = _gbm(10 + k).fit(Xs[s], zt[s]).predict(Xs[te])
            comps["analog"][te] = np.nan_to_num(np.nanmean(zt_nan[nbr_oof[te]], axis=1))
            comps["season"][te] = self._season_table(how[trv], zt[trv])[how[te]]
        n_eff = v.sum() * n_eff_scale
        comp_stats = {c: dict(zip(("ic", "t"), _ic_t(comps[c][v], zt[v], n_eff))) for c in COMPONENTS}
        passing = [c for c in COMPONENTS if comp_stats[c]["t"] > self.gate_t and comp_stats[c]["ic"] > 0
                   and (c != "gbm" or self.use_gbm)]
        weights = {c: 0.0 for c in COMPONENTS}
        mu_oof = np.zeros(n)
        ic_s, t_s, active = 0.0, 0.0, False
        if passing:
            M = np.column_stack([comps[c][v] for c in passing])
            w, _ = nnls(M, zt[v])
            if w.sum() > 0:
                for c, wi in zip(passing, w):
                    weights[c] = float(wi)
                mu_oof = sum(weights[c] * comps[c] for c in passing)
                ic_s, t_s = _ic_t(mu_oof[v], zt[v], n_eff)
                active = t_s > self.gate_t
        if not active:
            weights = {c: 0.0 for c in COMPONENTS}
            mu_oof = np.zeros(n)
        vi = np.where(v)[0]
        ridge_beta = _ridge(Xs[vi], zt[vi], self.ridge)
        gbm_mean = None
        if active and weights["gbm"] > 0:
            s = _sub(vi, self.gbm_rows)
            gbm_mean = _gbm(77).fit(Xs[s], zt[s])
        season_table = self._season_table(how[vi], zt[vi])
        fin = self.analog["A_rows"]
        self.analog["z"][h] = zt_nan[fin].astype(np.float32)
        self.analog["ret"][h] = np.where(v[fin], ret[fin], np.nan).astype(np.float32)

        # ---------------- 分布: ボラ局面別の残差プール
        zr = (z - mu_oof)[v]
        zr = zr - zr.mean()
        rc = reg_col[v]
        cuts = np.quantile(rc, [1 / 3, 2 / 3])
        bucket = np.searchsorted(cuts, rc)
        pools = []
        for bi in range(3):
            pools.append(self._pool(zr[bucket == bi]) if (bucket == bi).sum() >= 3000 else None)
        pools.append(self._pool(zr))

        # ---------------- 各特徴量の単独の予測力（順位相関）
        fic = {}
        if Rx is not None:
            mask = v[rx_rows]
            ry = rankdata(zt[rx_rows][mask])
            R = Rx[mask]
            R = (R - R.mean(0)) / (R.std(0) + 1e-12)
            ry = (ry - ry.mean()) / (ry.std() + 1e-12)
            ics = R.T @ ry / len(ry)
            ne = mask.sum() * min(1.0, self.stride * max(1, len(P) // max(len(rx_rows), 1)) / max(h, 1))
            for name, ic in zip(self.feature_names, ics):
                fic[name] = (float(ic), float(ic * np.sqrt(max(ne, 1))))

        if verbose:
            cs = " ".join(f"{c}:{comp_stats[c]['t']:+.1f}" for c in COMPONENTS)
            print(f"  h={horizon_label(h):>5}: n={v.sum():6d}  ボラ: HAR残差sd={res.std():.3f} GBM補正 "
                  f"{gain * 100:+.1f}%{'(採用)' if use_vg else '(不採用)'}  方向 t値[{cs}] → "
                  f"{'採用 t=%+.1f' % t_s if active else '不採用(ドリフト0)'}", flush=True)
        return HorizonModel(
            h=h, har_beta=b_full, vol_gbm=vol_gbm, vol_gbm_scale=scale, vol_gain_pct=gain * 100, smear=smear,
            har_resid_sd=float(res.std()), comp_weights=weights, comp_stats=comp_stats, ridge_beta=ridge_beta,
            gbm_mean=gbm_mean, season_table=season_table, active=active, ic_val=ic_s, t_val=t_s, z_pools=pools,
            regime_cuts=cuts, naive_q=np.quantile(ret[v], QLEVELS), naive_var=float(np.mean(ret[v] ** 2)),
            n_train=int(v.sum()), feature_ic=fic)

    @staticmethod
    def _season_table(how: np.ndarray, zt: np.ndarray, K: float = 300.0) -> np.ndarray:
        s = np.bincount(how, weights=zt, minlength=168)
        c = np.bincount(how, minlength=168)
        return s / (c + K)  # 0 に向けて縮小した時間帯平均

    @staticmethod
    def _pool(z: np.ndarray, cap: int = 20000) -> np.ndarray:
        zs = np.sort(z)
        if len(zs) > cap:
            zs = zs[np.linspace(0, len(zs) - 1, cap).astype(int)]
        return zs.astype(np.float32)

    # ------------------------------------------------------------- predict
    def predict_batch(self, fs: FeatureSet, pos: np.ndarray) -> dict[int, dict[str, np.ndarray]]:
        pos = np.asarray(pos, dtype=np.int64)
        Xs = self._std(fs.matrix(pos, self.feature_names))
        Xh = fs.har_matrix(pos)
        # 近傍の番号は self.analog 内の位置（学習時に保存した類似局面候補）
        nbrs = self._nn.kneighbors(Xs[:, self.aidx].astype(np.float32), return_distance=False) \
            if any(m.active and m.comp_weights.get("analog", 0) > 0 for m in self.models.values()) else None
        how = fs.grid.slot[pos] // 60
        reg = Xs[:, self.feature_names.index(REGIME_FEATURE)]
        out = {}
        for h, m in self.models.items():
            Ff = fs.future_fsum(pos, h)
            base = Xh @ m.har_beta
            adj = m.vol_gbm_scale * m.vol_gbm.predict(Xs) if m.vol_gbm is not None else np.zeros(len(pos))
            L = np.exp(base + adj) * m.smear
            sigma = np.sqrt(L * Ff)
            comp = {c: np.zeros(len(pos)) for c in COMPONENTS}
            if m.active:
                if m.comp_weights["ridge"] > 0:
                    comp["ridge"] = Xs @ m.ridge_beta
                if m.comp_weights["gbm"] > 0 and m.gbm_mean is not None:
                    comp["gbm"] = m.gbm_mean.predict(Xs)
                if m.comp_weights["analog"] > 0 and nbrs is not None:
                    comp["analog"] = np.nan_to_num(np.nanmean(self.analog["z"][h][nbrs], axis=1))
                if m.comp_weights["season"] > 0:
                    comp["season"] = m.season_table[how]
            mu_z = sum(m.comp_weights[c] * comp[c] for c in COMPONENTS) if m.active else np.zeros(len(pos))
            bucket = np.searchsorted(m.regime_cuts, reg)
            q = np.empty((len(pos), len(QLEVELS)))
            p_up = np.empty(len(pos))
            p_dn = np.empty(len(pos))
            for bi in range(3):
                sel = bucket == bi
                if not sel.any():
                    continue
                zs = m.z_pools[bi] if m.z_pools[bi] is not None else m.z_pools[3]
                zq = np.quantile(zs, QLEVELS)
                q[sel] = sigma[sel, None] * (mu_z[sel, None] + zq[None, :])
                p_up[sel] = (len(zs) - np.searchsorted(zs, -mu_z[sel], side="right")) / len(zs)
                p_dn[sel] = np.searchsorted(zs, -mu_z[sel], side="left") / len(zs)
            out[h] = dict(sigma=sigma, mu=mu_z * sigma, mu_z=mu_z, q=q, p_up=p_up, p_down=p_dn, L=L, Ff=Ff,
                          sigma_har=np.sqrt(np.exp(base) * m.smear * Ff), vol_adj=np.exp(adj), comps=comp, bucket=bucket)
        return out

    def z_pool(self, h: int, bucket: int) -> np.ndarray:
        m = self.models[h]
        return m.z_pools[bucket] if m.z_pools[bucket] is not None else m.z_pools[3]

    # ------------------------------------------------------------- simulate
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

        mh = np.array([0] + hs, dtype=float)
        mv = np.array([0.0] + [float(pred[h]["mu"][0]) for h in hs])
        cum_mu = np.interp(np.arange(1, H + 1), mh, mv)
        dmu = np.diff(np.concatenate([[0.0], cum_mu]))

        nb = int(np.ceil(H / block))
        starts = rng.integers(0, len(self.z1) - block, size=(n_paths, nb))
        ix = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_paths, -1)[:, :H]
        s = float(np.sqrt(max(self.models[max(hs)].har_resid_sd ** 2 - 0.05, 0.0)))
        scale = np.sqrt(np.exp(s * rng.standard_normal(n_paths) - s * s / 2))[:, None] * sd_min[None, :]
        close = np.cumsum(self.z1[ix] * scale + dmu[None, :], axis=1)
        prev = np.concatenate([np.zeros((n_paths, 1)), close[:, :-1]], axis=1)
        high = np.maximum(prev, close) + self.wick_up[ix] * scale
        low = np.minimum(prev, close) - self.wick_dn[ix] * scale
        return close, high, low

    # ------------------------------------------------------------- forecast
    def forecast(self, grid: Grid, fs: FeatureSet, pos: int | None = None, n_paths: int = 3000,
                 seed: int | None = 0) -> dict:
        """1 時点の完全な予測（分位点・方向確率・高安・到達確率・根拠・類似局面）。"""
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

        open_cum = np.cumsum(fs.fpath(pos, H) > 0.02)
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
                "sigma_har_usd": float(p0 * d["sigma_har"][0]), "vol_adjust_factor": float(np.sqrt(d["vol_adj"][0])),
                "drift_pct": float(d["mu"][0] * 100), "drift_usd": float(p0 * np.expm1(d["mu"][0])),
                "trading_minutes": int(open_cum[h - 1]),
                "mean_model_active": m.active, "mean_model_t": m.t_val,
                "components_usd": {c: float(m.comp_weights[c] * d["comps"][c][0] * d["sigma"][0] * p0) for c in COMPONENTS},
                "component_weights": m.comp_weights,
                "median": float(qp[QLEVELS.tolist().index(0.5)]),
                "quantiles": {f"{q:g}": float(v) for q, v in zip(QLEVELS, qp)},
                "p_up": float(d["p_up"][0]), "p_down": float(d["p_down"][0]),
                "p_flat": float(max(0.0, 1 - d["p_up"][0] - d["p_down"][0])),
                "expected_high": float(np.median(hi)), "expected_low": float(np.median(lo)),
                "high_q90": float(np.quantile(hi, 0.9)), "low_q10": float(np.quantile(lo, 0.1)),
                "expected_range_usd": float(np.median(hi - lo)),
                "vol_level_vs_normal": float(d["L"][0] / self.r2_scale),
                "vol_regime_bucket": ["低", "中", "高"][int(d["bucket"][0])],
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
        lo_i = max(0, pos - 359)
        hist = {"minutes": (np.arange(lo_i, pos + 1) - pos).tolist(), "close": grid.close[lo_i:pos + 1].round(3).tolist()}

        return {
            "symbol": "XAUUSD", "origin_utc": str(t0), "origin_ny": str(t0.tz_convert("America/New_York")),
            "origin_tokyo": str(t0.tz_convert("Asia/Tokyo")), "price": p0,
            "model_trained_until": str(self.fit_end), "data_last_bar_utc": str(grid.idx[grid.n - 1]),
            "n_features": len(self.feature_names),
            "horizons": hz, "touch": touch, "fan": fan, "history": hist,
            "explain": self.explain(fs, pos, p0),
        }

    def explain(self, fs: FeatureSet, pos: int, p0: float, top: int = 10) -> dict:
        """予測の根拠: 現在の統計量の位置づけ、線形モデルの寄与、類似局面。"""
        Xs = self._std(fs.matrix(np.array([pos]), self.feature_names))[0]
        pct = np.array([np.searchsorted(self.feature_pct_grid[:, j], Xs[j]) for j in range(len(Xs))]) / 100.0
        hs = [h for h in (60, 1440) if h in self.models] or [max(self.models)]
        stats = []
        order = np.argsort(-np.abs(np.array([self.models[hs[-1]].feature_ic.get(k, (0, 0))[1] for k in self.feature_names])))
        for j in order[: top * 2]:
            k = self.feature_names[j]
            row = {"feature": k, "group": self.feature_groups.get(k, ""), "value_z": float(Xs[j]),
                   "percentile": float(min(pct[j], 1.0))}
            for h in hs:
                ic, t = self.models[h].feature_ic.get(k, (0.0, 0.0))
                row[f"ic_{h}"], row[f"t_{h}"] = ic, t
            stats.append(row)
        contrib = {}
        for h in hs:
            m = self.models[h]
            c = Xs * m.ridge_beta
            idx = np.argsort(-np.abs(c))[:top]
            contrib[h] = [{"feature": self.feature_names[j], "group": self.feature_groups.get(self.feature_names[j], ""),
                           "contribution_z": float(c[j]), "value_z": float(Xs[j])} for j in idx]
        # 類似局面
        dist, idx = self._nn.kneighbors(Xs[self.aidx][None, :].astype(np.float32))
        idx = idx[0]
        an = {"k": int(len(idx)), "by_horizon": [], "nearest": []}
        for h in sorted(self.models):
            rr = self.analog["ret"][h][idx]
            rr = rr[np.isfinite(rr)]
            if len(rr) > 10:
                an["by_horizon"].append({"h": h, "label": horizon_label(h), "n": int(len(rr)), "p_up": float(np.mean(rr > 0)),
                                         "median_usd": float(p0 * np.expm1(np.median(rr))),
                                         "q10_usd": float(p0 * np.expm1(np.quantile(rr, 0.1))),
                                         "q90_usd": float(p0 * np.expm1(np.quantile(rr, 0.9)))})
        chosen = []
        for i, d in zip(idx, dist[0]):
            t = pd.Timestamp(int(self.analog["time"][i]), unit="ns", tz="UTC")
            if any(abs((t - c).total_seconds()) < 6 * 3600 for c in chosen):
                continue  # 同じ局面（6 時間以内）の重複を除く
            chosen.append(t)
            if len(chosen) > 8:
                break
            row = {"time_utc": str(t)[:16], "distance": float(d)}
            for h in (60, 240, 1440):
                if h in self.analog["ret"]:
                    v = self.analog["ret"][h][i]
                    row[f"ret_{h}_pct"] = float(v * 100) if np.isfinite(v) else None
            an["nearest"].append(row)
        summary = [{"h": h, "label": horizon_label(h), "vol_gbm_gain_pct": m.vol_gain_pct, "vol_gbm_used": m.vol_gbm is not None,
                    "active": m.active, "t": m.t_val, "weights": m.comp_weights,
                    "component_t": {c: m.comp_stats[c]["t"] for c in COMPONENTS}} for h, m in sorted(self.models.items())]
        return {"feature_stats": stats, "linear_contrib": {str(k): v for k, v in contrib.items()}, "analogs": an,
                "model_summary": summary}

    def feature_ic_table(self) -> pd.DataFrame:
        rows = []
        for k in self.feature_names:
            row = {"feature": k, "group": self.feature_groups.get(k, "")}
            for h, m in sorted(self.models.items()):
                ic, t = m.feature_ic.get(k, (np.nan, np.nan))
                row[f"ic_{h}"], row[f"t_{h}"] = ic, t
            rows.append(row)
        return pd.DataFrame(rows)

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
