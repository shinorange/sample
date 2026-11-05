"""ウォークフォワード検証（拡張窓で再学習 → 未来区間で評価）。

評価項目（ホライズン別）:
  - 予測区間のカバー率（50/80/90/95/98%）… 名目値に近いほど較正が良い
  - PIT の一様性（KS 距離）
  - 分位点損失（pinball）の改善率 vs 無条件分布（気候値）ベンチマーク
  - ボラ予測: QLIKE 改善率、log(実現分散) と log(予測分散) の相関
  - 方向: 的中率・Brier スコア改善率（ドリフト 0 の 50% 予測が基準）
  - 到達確率（モンテカルロ）の較正: 予測確率の平均 vs 実際の到達頻度
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .core import WARMUP, Grid, horizon_label
from .model import COMPONENTS, QLEVELS, TOUCH_PCTS, Forecaster

INTERVALS = {50: (0.25, 0.75), 80: (0.1, 0.9), 90: (0.05, 0.95), 95: (0.025, 0.975), 98: (0.01, 0.99)}


def _pinball(y: np.ndarray, q: np.ndarray) -> float:
    d = y[:, None] - q
    return float(np.mean(np.maximum(QLEVELS[None, :] * d, (QLEVELS[None, :] - 1) * d)))


def backtest(df: pd.DataFrame, n_folds: int = 4, test_frac: float = 0.4, eval_stride: int = 15,
             touch_origins: int = 150, touch_paths: int = 400, verbose: bool = True, **model_kw) -> dict:
    grid = Grid(df)
    start = max(WARMUP + 45 * 1440, int(grid.n * (1 - test_frac)))
    bounds = np.linspace(start, grid.n, n_folds + 1).astype(int)
    rec: dict[int, dict[str, list]] = {}
    touch_rec = []
    rng = np.random.default_rng(0)
    for k in range(n_folds):
        a, b = bounds[k], bounds[k + 1]
        model = Forecaster(**model_kw)
        if verbose:
            print(f"[fold {k + 1}/{n_folds}] 学習 〜{grid.idx[a - 1]:%Y-%m-%d %H:%M} / 検証 〜{grid.idx[b - 1]:%Y-%m-%d %H:%M}", flush=True)
        fs = model.fit(grid, end=a)
        test = np.where(grid.is_open[a:b])[0] + a
        test = test[::eval_stride]
        allpred = model.predict_batch(fs, test)
        keys = ("y", "q", "nq", "sigma", "sigma_har", "rv", "mu", "pup", "pdn", "pit", "nvar", "active") + \
            tuple(f"c_{c}" for c in COMPONENTS)
        for h, m in model.models.items():
            sel = (test + h < grid.n)
            pr = {kk: (vv[sel] if isinstance(vv, np.ndarray) else vv) for kk, vv in allpred[h].items()}
            pr["comps"] = {c: v[sel] for c, v in allpred[h]["comps"].items()}
            ok = pr["Ff"] > 0.05 * h
            p = test[sel][ok]
            if len(p) == 0:
                continue
            y = grid.logp[p + h] - grid.logp[p]
            rv = grid.Cr2[p + h + 1] - grid.Cr2[p + 1]
            d = rec.setdefault(h, {k2: [] for k2 in keys})
            d["y"].append(y)
            d["q"].append(pr["q"][ok])
            d["nq"].append(np.repeat(m.naive_q[None, :], len(p), 0))
            d["sigma"].append(pr["sigma"][ok])
            d["sigma_har"].append(pr["sigma_har"][ok])
            d["rv"].append(rv)
            d["mu"].append(pr["mu"][ok])
            d["pup"].append(pr["p_up"][ok])
            d["pdn"].append(pr["p_down"][ok])
            zobs = (y / np.maximum(pr["sigma"][ok], 1e-12)) - pr["mu_z"][ok]
            bk = pr["bucket"][ok]
            pit = np.empty(len(p))
            for bi in range(3):
                zs = model.z_pool(h, bi)
                pit[bk == bi] = np.searchsorted(zs, zobs[bk == bi]) / len(zs)
            d["pit"].append(pit)
            d["nvar"].append(np.full(len(p), m.naive_var))
            d["active"].append(np.full(len(p), m.active))
            # 各予測器の生の予測値（採用されていなくても計算して検証期間の予測力を測る）
            for c in COMPONENTS:
                d[f"c_{c}"].append(pr["comps"][c][ok])

        # 到達確率の較正（MC はコストが高いのでサブサンプル）
        if touch_origins > 0:
            H = max(model.models)
            cand = np.where(grid.is_open[a:b])[0] + a
            cand = cand[cand + H < grid.n]
            if len(cand):
                sel = rng.choice(cand, size=min(touch_origins // n_folds + 1, len(cand)), replace=False)
                preds = model.predict_batch(fs, sel)
                for i, p in enumerate(sel):
                    one = {h: {kk: vv[i:i + 1] for kk, vv in preds[h].items() if isinstance(vv, np.ndarray)} for h in preds}
                    _, ph, pl = model.simulate(fs, int(p), one, n_paths=touch_paths, H=H, seed=int(p))
                    p0 = grid.close[p]
                    pmax = p0 * np.exp(np.maximum.accumulate(ph, axis=1))
                    pmin = p0 * np.exp(np.minimum.accumulate(pl, axis=1))
                    for h in (60, 240, 1440):
                        if h > H:
                            continue
                        rh = grid.high[p + 1:p + h + 1].max()
                        rl = grid.low[p + 1:p + h + 1].min()
                        for pct in TOUCH_PCTS:
                            up, dn = p0 * (1 + pct / 100), p0 * (1 - pct / 100)
                            touch_rec.append((h, pct, "up", float((pmax[:, h - 1] >= up).mean()), float(rh >= up)))
                            touch_rec.append((h, pct, "down", float((pmin[:, h - 1] <= dn).mean()), float(rl <= dn)))

    res = {"period_test": [str(grid.idx[bounds[0]]), str(grid.idx[-1])], "n_folds": n_folds, "horizons": []}
    for h in sorted(rec):
        d = {k: np.concatenate(v) for k, v in rec[h].items()}
        y, q, nq = d["y"], d["q"], d["nq"]
        row = {"h": h, "label": horizon_label(h), "n": int(len(y))}
        for lev, (lo, hi) in INTERVALS.items():
            il, ih = list(QLEVELS).index(lo), list(QLEVELS).index(hi)
            row[f"cover_{lev}"] = float(np.mean((y >= q[:, il]) & (y <= q[:, ih])))
            row[f"naive_cover_{lev}"] = float(np.mean((y >= nq[:, il]) & (y <= nq[:, ih])))
        pl, npl = _pinball(y, q), _pinball(y, nq)
        row["pinball_skill_pct"] = float((1 - pl / npl) * 100)
        pit = np.sort(d["pit"])
        row["pit_ks"] = float(np.max(np.abs(pit - (np.arange(1, len(pit) + 1) / len(pit)))))
        s2 = d["sigma"] ** 2
        good = (d["rv"] > 0) & (s2 > 0)
        ql = lambda rv, v: np.mean(rv / v - np.log(rv / v) - 1)
        row["qlike_skill_pct"] = float((1 - ql(d["rv"][good], s2[good]) / ql(d["rv"][good], d["nvar"][good])) * 100)
        row["vol_corr"] = float(np.corrcoef(np.log(d["rv"][good]), np.log(s2[good]))[0, 1])
        sh2 = d["sigma_har"][good] ** 2
        row["qlike_skill_har_only_pct"] = float((1 - ql(d["rv"][good], sh2) / ql(d["rv"][good], d["nvar"][good])) * 100)
        nz = y != 0
        pu = d["pup"][nz] / np.maximum(d["pup"][nz] + d["pdn"][nz], 1e-9)
        out = (y[nz] > 0).astype(float)
        row["brier_skill_pct"] = float((1 - np.mean((pu - out) ** 2) / np.mean((0.5 - out) ** 2)) * 100)
        act = d["active"][nz] & (d["mu"][nz] != 0)
        row["mean_model_active_share"] = float(np.mean(d["active"]))
        row["hit_rate_when_active"] = float(np.mean(np.sign(d["mu"][nz][act]) == np.sign(y[nz][act]))) if act.any() else None
        row["ic"] = float(np.corrcoef(d["mu"][nz], y[nz])[0, 1]) if np.std(d["mu"][nz]) > 0 else None
        for c in COMPONENTS:
            cc = d[f"c_{c}"][nz]
            row[f"ic_{c}"] = float(np.corrcoef(cc, y[nz])[0, 1]) if np.std(cc) > 0 else None
        res["horizons"].append(row)

    if touch_rec:
        t = pd.DataFrame(touch_rec, columns=["h", "pct", "side", "p", "hit"])
        g = t.groupby(["h", "pct"]).agg(pred=("p", "mean"), actual=("hit", "mean"), n=("hit", "size")).reset_index()
        t["b"] = (t["p"] - t["hit"]) ** 2
        res["touch_calibration"] = g.to_dict("records")
        res["touch_brier"] = float(t["b"].mean())
    return res
