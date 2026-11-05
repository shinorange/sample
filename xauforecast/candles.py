"""値幅が取れる（大きく動く）ローソク足の直前に、どんな統計量の条件が成り立っているかを洗い出す。

定義:
  - 時間足（既定 15分・1時間・4時間）のローソク足を、時計の区切り（例: 毎時 0 分）で作る。
  - 動きの大きさは「その時間帯として普通の値動き」で割って標準化する:
        z = 足のリターン / sqrt(過去 1 日の脱季節化ボラ × その足の時間帯の季節的ボラの和)
    → 時間帯による動きやすさの違いを除いたうえで「いつもより大きい足」を選ぶ。
  - 探索期間（前半 60%）で |z| の上位 10% を「大きな足」とし、z > 0 を大陽線、z < 0 を大陰線とする。

分析:
  1. 単独条件: 足の始まりの時点の各特徴量（約 140 個）を探索期間の五分位で分け、各区分の
     大陽線率・大陰線率・大きく動く率を基準と比べる（リフト = 区分の率 / 全体の率）。
     二項検定の p 値に Benjamini-Hochberg の FDR 補正をかけ、検証期間（後半 40%）で同じ向きに
     再現したかを確認する。
  2. 組み合わせ条件: 浅い決定木（深さ 3、葉の最小サイズを大きく）で 2〜3 個の条件の組み合わせを探し、
     各葉（条件の組み合わせ）の大陽線率・大陰線率を、検証期間でも測る。
  3. 時間帯: NY 時間 × 曜日ごとの大陽線率・大陰線率・平均値幅。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from .core import NY, FeatureSet, Grid, WARMUP, estimate_profile
from .features import feature_label

TARGETS = {"bigup": "大陽線", "bigdown": "大陰線", "big": "大きく動く(上下問わず)"}


def _bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg の q 値。"""
    p = np.asarray(p, dtype=float)
    n = len(p)
    o = np.argsort(p)
    q = p[o] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[o] = np.clip(q, 0, 1)
    return out


def candle_frame(grid: Grid, fs: FeatureSet, tf: int) -> pd.DataFrame:
    """時間足 tf 分のローソク足（始まりの時点の特徴量つき）。"""
    minute_of_day = (grid.idx.hour * 60 + grid.idx.minute).to_numpy()
    pos = np.where((minute_of_day % tf == 0) & grid.is_open)[0]
    pos = pos[(pos >= WARMUP) & (pos + tf < grid.n)]
    Ff = fs.Cf[pos + tf + 1] - fs.Cf[pos + 1]
    pos = pos[Ff > 0.5 * tf * np.median(Ff / tf)]  # 休場が大半を占める足は除く
    Ff = fs.Cf[pos + tf + 1] - fs.Cf[pos + 1]
    p0 = grid.logp[pos]
    ret = grid.logp[pos + tf] - p0
    hi = pd.Series(grid.high).rolling(tf).max().to_numpy()[pos + tf]
    lo = pd.Series(grid.low).rolling(tf).min().to_numpy()[pos + tf]
    sd = np.sqrt(np.maximum(fs.L[1440][pos], fs.eps) * Ff)
    ny = grid.idx[pos].tz_convert(NY)
    df = pd.DataFrame({"pos": pos, "time": grid.idx[pos], "ret": ret, "z": ret / sd,
                       "range_usd": hi - lo, "move_usd": grid.close[pos + tf] - grid.close[pos],
                       "ny_hour": ny.hour, "weekday": ny.dayofweek})
    return df


def analyze(df_m1: pd.DataFrame, tfs=(15, 60, 240), q: float = 0.9, is_frac: float = 0.6,
            max_depth: int = 3, verbose: bool = True) -> dict:
    from sklearn.tree import DecisionTreeClassifier

    grid = Grid(df_m1)
    end_is = int(grid.n * is_frac)
    f = estimate_profile(grid, end_is)
    fs = FeatureSet(grid, f, end_is)
    names = fs.names
    out = {"period": [str(grid.idx[0]), str(grid.idx[-1])], "is_end": str(grid.idx[end_is - 1]), "tfs": {}}
    for tf in tfs:
        c = candle_frame(grid, fs, tf)
        is_m = (c["pos"] < end_is).to_numpy()
        if is_m.sum() < 500 or (~is_m).sum() < 200:
            continue
        thr = float(np.quantile(np.abs(c.loc[is_m, "z"]), q))
        c["bigup"] = c["z"] >= thr
        c["bigdown"] = c["z"] <= -thr
        c["big"] = c["bigup"] | c["bigdown"]
        X = fs.matrix(c["pos"].to_numpy())
        base = {t: float(c.loc[is_m, t].mean()) for t in TARGETS}
        base_oos = {t: float(c.loc[~is_m, t].mean()) for t in TARGETS}

        # ---- 1. 単独条件（五分位）
        rows = []
        for j, name in enumerate(names):
            x = X[:, j]
            edges = np.unique(np.quantile(x[is_m], [0.2, 0.4, 0.6, 0.8]))
            if len(edges) < 2:
                continue
            b = np.searchsorted(edges, x, side="right")
            for k in range(len(edges) + 1):
                sel_is = is_m & (b == k)
                sel_oos = ~is_m & (b == k)
                n_is, n_oos = int(sel_is.sum()), int(sel_oos.sum())
                if n_is < 100:
                    continue
                lo_v = -np.inf if k == 0 else edges[k - 1]
                hi_v = np.inf if k == len(edges) else edges[k]
                for t in TARGETS:
                    p_is = float(c.loc[sel_is, t].mean())
                    p_oos = float(c.loc[sel_oos, t].mean()) if n_oos else np.nan
                    pv = sps.binomtest(int(c.loc[sel_is, t].sum()), n_is, base[t]).pvalue
                    rows.append({"feature": name, "label": feature_label(name), "group": fs.groups.get(name, ""),
                                 "quintile": k + 1, "lo": lo_v, "hi": hi_v, "target": t, "n_is": n_is, "n_oos": n_oos,
                                 "p_is": p_is, "p_oos": p_oos, "lift_is": p_is / base[t] if base[t] else np.nan,
                                 "lift_oos": p_oos / base_oos[t] if base_oos[t] else np.nan, "pval": pv})
        single = pd.DataFrame(rows)
        single["qval"] = _bh(single["pval"].to_numpy())
        single["replicated"] = (single["qval"] < 0.05) & (np.sign(single["lift_is"] - 1) == np.sign(single["lift_oos"] - 1)) \
            & ((single["lift_oos"] - 1).abs() >= 0.5 * (single["lift_is"] - 1).abs())

        # ---- 1b. 方向: 大きな足に限って、陽線になる割合が条件でどう偏るか
        big_m = c["big"].to_numpy()
        up = c["bigup"].to_numpy()
        share_is = float(up[is_m & big_m].mean())
        share_oos = float(up[~is_m & big_m].mean()) if (~is_m & big_m).any() else np.nan
        drows = []
        for j, name in enumerate(names):
            x = X[:, j]
            edges = np.unique(np.quantile(x[is_m & big_m], [0.2, 0.4, 0.6, 0.8]))
            if len(edges) < 2:
                continue
            b = np.searchsorted(edges, x, side="right")
            for k in range(len(edges) + 1):
                a = is_m & big_m & (b == k)
                o = ~is_m & big_m & (b == k)
                if a.sum() < 40:
                    continue
                p_is = float(up[a].mean())
                p_oos = float(up[o].mean()) if o.sum() >= 10 else np.nan
                drows.append({"feature": name, "label": feature_label(name), "group": fs.groups.get(name, ""),
                              "quintile": k + 1, "lo": -np.inf if k == 0 else edges[k - 1],
                              "hi": np.inf if k == len(edges) else edges[k], "n_is": int(a.sum()), "n_oos": int(o.sum()),
                              "up_is": p_is, "up_oos": p_oos, "pval": sps.binomtest(int(up[a].sum()), int(a.sum()), share_is).pvalue})
        direction = pd.DataFrame(drows)
        if len(direction):
            direction["qval"] = _bh(direction["pval"].to_numpy())
            d_is = direction["up_is"] - share_is
            d_oos = direction["up_oos"] - share_oos
            direction["replicated"] = (direction["qval"] < 0.05) & (np.sign(d_is) == np.sign(d_oos)) & (d_oos.abs() >= 0.5 * d_is.abs())

        # 方向の組み合わせ条件（大きな足だけで決定木: 陽線 vs 陰線）
        dleaf_min = max(60, int(0.05 * (is_m & big_m).sum()))
        dtree = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=dleaf_min, random_state=0)
        dtree.fit(X[is_m & big_m], up[is_m & big_m].astype(int))
        dl = dtree.apply(X)
        dpaths = _leaf_paths(dtree, names)
        dlrows = []
        for leaf in np.unique(dl[is_m & big_m]):
            a = is_m & big_m & (dl == leaf)
            o = ~is_m & big_m & (dl == leaf)
            dlrows.append({"conditions": dpaths.get(leaf, ""), "n_is": int(a.sum()), "n_oos": int(o.sum()),
                           "up_is": float(up[a].mean()), "up_oos": float(up[o].mean()) if o.any() else np.nan,
                           "move_usd_oos": float(c.loc[o, "move_usd"].mean()) if o.any() else np.nan})
        dir_leaves = pd.DataFrame(dlrows)

        # ---- 1c. 時間帯別の方向: 足の開始時刻（NY 時）ごとに、特徴量が中央値より上か下かで
        #          次の足の符号付きの動き（z）がどう違うか（Welch の t 検定）
        hrows = []
        zz = c["z"].to_numpy()
        hrs = c["ny_hour"].to_numpy()
        for h in np.unique(hrs):
            hm = hrs == h
            if (is_m & hm).sum() < 60 or (~is_m & hm).sum() < 30:
                continue
            for j, name in enumerate(names):
                x = X[:, j]
                med = np.median(x[is_m & hm])
                hi_ = x > med
                a1, a0 = is_m & hm & hi_, is_m & hm & ~hi_
                o1, o0 = ~is_m & hm & hi_, ~is_m & hm & ~hi_
                if min(a1.sum(), a0.sum()) < 25 or min(o1.sum(), o0.sum()) < 10:
                    continue
                t_is, p_is = sps.ttest_ind(zz[a1], zz[a0], equal_var=False)
                hrows.append({"ny_hour": int(h), "feature": name, "label": feature_label(name), "group": fs.groups.get(name, ""),
                              "median": float(med), "n_is": int(a1.sum() + a0.sum()), "n_oos": int(o1.sum() + o0.sum()),
                              "diff_is": float(zz[a1].mean() - zz[a0].mean()), "diff_oos": float(zz[o1].mean() - zz[o0].mean()),
                              "up_hi_is": float((zz[a1] > 0).mean()), "up_lo_is": float((zz[a0] > 0).mean()),
                              "up_hi_oos": float((zz[o1] > 0).mean()), "up_lo_oos": float((zz[o0] > 0).mean()),
                              "move_hi_oos_usd": float(c["move_usd"].to_numpy()[o1].mean()),
                              "move_lo_oos_usd": float(c["move_usd"].to_numpy()[o0].mean()), "t_is": float(t_is), "pval": float(p_is)})
        hour_dir = pd.DataFrame(hrows)
        if len(hour_dir):
            hour_dir["qval"] = _bh(hour_dir["pval"].to_numpy())
            hour_dir["replicated"] = (hour_dir["qval"] < 0.05) & (np.sign(hour_dir["diff_is"]) == np.sign(hour_dir["diff_oos"])) \
                & (hour_dir["diff_oos"].abs() >= 0.5 * hour_dir["diff_is"].abs())

        # ---- 2. 組み合わせ条件（浅い決定木）
        y = np.where(c["bigup"], 1, np.where(c["bigdown"], 2, 0))
        leaf_min = max(150, int(0.03 * is_m.sum()))
        tree = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=leaf_min, random_state=0)
        tree.fit(X[is_m], y[is_m])
        leaves = tree.apply(X)
        paths = _leaf_paths(tree, names)
        lrows = []
        for leaf in np.unique(leaves[is_m]):
            a, o = is_m & (leaves == leaf), ~is_m & (leaves == leaf)
            r = {"conditions": paths.get(leaf, ""), "n_is": int(a.sum()), "n_oos": int(o.sum())}
            for t in ("bigup", "bigdown", "big"):
                r[f"{t}_is"] = float(c.loc[a, t].mean())
                r[f"{t}_oos"] = float(c.loc[o, t].mean()) if o.any() else np.nan
                r[f"{t}_lift_is"] = r[f"{t}_is"] / base[t] if base[t] else np.nan
                r[f"{t}_lift_oos"] = r[f"{t}_oos"] / base_oos[t] if base_oos[t] else np.nan
            r["mean_range_usd_is"] = float(c.loc[a, "range_usd"].mean())
            r["mean_move_usd_oos"] = float(c.loc[o, "move_usd"].mean()) if o.any() else np.nan
            lrows.append(r)
        leaves_df = pd.DataFrame(lrows)

        # ---- 3. 時間帯
        hour = c[is_m | ~is_m].groupby("ny_hour").agg(n=("z", "size"), bigup=("bigup", "mean"), bigdown=("bigdown", "mean"),
                                                       big=("big", "mean"), mean_range_usd=("range_usd", "mean")).reset_index()
        wd = c.groupby("weekday").agg(n=("z", "size"), bigup=("bigup", "mean"), bigdown=("bigdown", "mean"),
                                      mean_range_usd=("range_usd", "mean")).reset_index()
        big_usd = c.loc[c["big"], "range_usd"]
        out["tfs"][tf] = {"n_is": int(is_m.sum()), "n_oos": int((~is_m).sum()), "threshold_z": thr, "base": base,
                          "base_oos": base_oos, "big_range_usd_median": float(big_usd.median()) if len(big_usd) else None,
                          "normal_range_usd_median": float(c.loc[~c["big"], "range_usd"].median()),
                          "single": single, "leaves": leaves_df, "hour": hour, "weekday": wd,
                          "direction": direction, "dir_leaves": dir_leaves, "up_share_is": share_is, "up_share_oos": share_oos,
                          "hour_direction": hour_dir}
        if verbose:
            nd = int(direction["replicated"].sum()) if len(direction) else 0
            nh = int(hour_dir["replicated"].sum()) if len(hour_dir) else 0
            print(f"  {tf}分足 方向: 大きな足のうち陽線 {share_is * 100:.1f}%、方向の条件で再現 {nd} 個、時間帯別の方向条件で再現 {nh} 個", flush=True)
            rep = single[single["replicated"]]
            print(f"  {tf}分足: 足 {len(c):,} 本、条件 {len(single):,} 個を検定、FDR 有意かつ検証期間で再現 "
                  f"{len(rep)} 個（大陽線 {int((rep.target == 'bigup').sum())} / 大陰線 {int((rep.target == 'bigdown').sum())} / "
                  f"上下問わず {int((rep.target == 'big').sum())}）", flush=True)
    return out


def _leaf_paths(tree, names) -> dict:
    t = tree.tree_
    out = {}

    def walk(node, conds):
        if t.children_left[node] == -1:
            out[node] = " かつ ".join(conds) if conds else "(全体)"
            return
        f = names[t.feature[node]]
        th = t.threshold[node]
        lab = feature_label(f)
        walk(t.children_left[node], conds + [f"{lab} ≤ {th:.3g}"])
        walk(t.children_right[node], conds + [f"{lab} > {th:.3g}"])

    walk(0, [])
    return out


def candles_markdown(res: dict, top: int = 15) -> str:
    def f(v, d=2):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-"
        return f"{v:,.{d}f}"

    def pc(v):
        return "-" if v is None or not np.isfinite(v) else f"{v * 100:.1f}%"

    def rng(r):
        lo, hi = r["lo"], r["hi"]
        if not np.isfinite(lo):
            return f"≤ {hi:.3g}"
        if not np.isfinite(hi):
            return f"> {lo:.3g}"
        return f"{lo:.3g} 〜 {hi:.3g}"

    wd = ["月", "火", "水", "木", "金", "土", "日"]
    L = ["# 値幅が取れるローソク足（大陽線・大陰線）の直前の統計量の条件\n",
         f"- 期間: {res['period'][0][:16]} 〜 {res['period'][1][:16]}（探索: 〜{res['is_end'][:16]}、それ以降は検証）",
         "- 「大きな足」= その時間帯として普通の値動きで割った動き（z）が、探索期間の上位 10% の足。",
         "- リフト = 条件を満たす足での発生率 ÷ 全体の発生率（1.5 なら 1.5 倍起きやすい）。",
         "- 「再現」= 探索期間で FDR 補正後に有意（q < 0.05）、かつ検証期間でも同じ向きに、探索期間の半分以上の強さで現れた条件。\n",
         "> 「大きく動くかどうか」（ボラ）は統計量からかなり予測できますが、「上か下か」は予測できないことが多いです。"
         "大陽線と大陰線の両方が同じ条件で増える場合、それは方向ではなく値幅の条件です。\n"]
    for tf, r in res["tfs"].items():
        lab = f"{tf}分足" if tf < 60 else f"{tf // 60}時間足"
        b = r["base"]
        L += [f"\n## {lab}\n",
              f"- 足の数: 探索 {r['n_is']:,} / 検証 {r['n_oos']:,}。大きな足の閾値 |z| ≥ {r['threshold_z']:.2f}",
              f"- 基準の発生率: 大陽線 {pc(b['bigup'])} / 大陰線 {pc(b['bigdown'])}。値幅の中央値: 大きな足 ${f(r['big_range_usd_median'])}、"
              f"それ以外 ${f(r['normal_range_usd_median'])}\n"]
        s = r["single"]
        for t, name in (("bigup", "大陽線"), ("bigdown", "大陰線"), ("big", "上下問わず大きく動く")):
            d = s[(s.target == t) & (s.lift_is > 1)].copy()
            d["score"] = np.where(d["replicated"], 1, 0) * 10 + (d["lift_is"] - 1)
            d = d.sort_values(["replicated", "lift_is"], ascending=[False, False]).head(top)
            L += [f"\n### {name}が起きやすい条件（単独、上位 {top}）\n",
                  "| 統計量 | 分類 | 範囲（五分位） | 探索 発生率 | リフト | q値 | 検証 発生率 | 検証リフト | 再現 |", "|---|---|---|---|---|---|---|---|---|"]
            for _, x in d.iterrows():
                L.append(f"| {x['label']} | {x['group']} | 第{x['quintile']} ({rng(x)}) | {pc(x['p_is'])} | {f(x['lift_is'])} | {f(x['qval'], 3)} | "
                         f"{pc(x['p_oos'])} | {f(x['lift_oos'])} | {'○' if x['replicated'] else '-'} |")
        dd_ = r.get("direction")
        if dd_ is not None and len(dd_):
            L += [f"\n### 大きな足が陽線 / 陰線のどちらになりやすいか（方向の条件）\n",
                  f"大きな足のうち陽線の割合は、探索 {pc(r['up_share_is'])} / 検証 {pc(r['up_share_oos'])}。"
                  "その割合が条件によってどれだけ偏るかです。値幅の条件と違い、ここで再現する条件が「方向を取れる」条件です。\n"]
            for side, asc, name in ((1, False, "陽線になりやすい"), (-1, True, "陰線になりやすい")):
                d = dd_[(dd_["up_is"] - r["up_share_is"]) * side > 0].sort_values(["replicated", "up_is"], ascending=[False, asc]).head(10)
                L += [f"\n#### {name}条件（上位 10）\n",
                      "| 統計量 | 分類 | 範囲（五分位） | 探索 足数 | 探索 陽線率 | q値 | 検証 足数 | 検証 陽線率 | 再現 |", "|---|---|---|---|---|---|---|---|---|"]
                for _, x in d.iterrows():
                    L.append(f"| {x['label']} | {x['group']} | 第{x['quintile']} ({rng(x)}) | {x['n_is']} | {pc(x['up_is'])} | {f(x['qval'], 3)} | "
                             f"{x['n_oos']} | {pc(x['up_oos'])} | {'○' if x['replicated'] else '-'} |")
            dl_ = r.get("dir_leaves")
            if dl_ is not None and len(dl_):
                L += ["\n#### 方向の組み合わせ条件（大きな足だけで作った決定木）\n",
                      "| 条件 | 探索 足数 | 探索 陽線率 | 検証 足数 | 検証 陽線率 | 検証 平均値動き$ |", "|---|---|---|---|---|---|"]
                for _, x in dl_.sort_values("up_is", ascending=False).iterrows():
                    L.append(f"| {x['conditions']} | {x['n_is']} | {pc(x['up_is'])} | {x['n_oos']} | {pc(x['up_oos'])} | {f(x['move_usd_oos'])} |")
        hd = r.get("hour_direction")
        if hd is not None and len(hd):
            top_h = hd.sort_values(["replicated", "pval"], ascending=[False, True]).head(15)
            L += ["\n### 時間帯別の方向の条件（足の開始時刻ごと、統計量が中央値より上 / 下）\n",
                  "特定の時間帯にだけ効く方向の偏りを探します（例: アジア時間に上がった日のロンドン序盤）。"
                  "差は「中央値より上の足」と「下の足」の平均の動き（σ 単位）の差。\n",
                  "| NY時 | 統計量 | 中央値 | 探索: 上→陽線率 / 下→陽線率 | 差(σ) | q値 | 検証: 上→陽線率 / 下→陽線率 | 検証 差(σ) | 検証 平均値動き$ 上/下 | 再現 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
            for _, x in top_h.iterrows():
                L.append(f"| {x['ny_hour']} | {x['label']} | {x['median']:.3g} | {pc(x['up_hi_is'])} / {pc(x['up_lo_is'])} | {f(x['diff_is'])} | {f(x['qval'], 3)} | "
                         f"{pc(x['up_hi_oos'])} / {pc(x['up_lo_oos'])} | {f(x['diff_oos'])} | {f(x['move_hi_oos_usd'])} / {f(x['move_lo_oos_usd'])} | "
                         f"{'○' if x['replicated'] else '-'} |")
        lv = r["leaves"].copy()
        if len(lv):
            L += ["\n### 組み合わせ条件（決定木の葉）\n",
                  "探索期間で決定木が作った条件の組み合わせごとの発生率です。検証期間の列で再現しているかを確認してください。\n",
                  "| 条件 | 探索 足数 | 大陽線 探索→検証 | 大陰線 探索→検証 | 大きな足 探索→検証 | 平均値幅$ | 検証 平均値動き$ |",
                  "|---|---|---|---|---|---|---|"]
            lv["mx"] = lv[["bigup_lift_is", "bigdown_lift_is"]].max(axis=1)
            for _, x in lv.sort_values("mx", ascending=False).iterrows():
                L.append(f"| {x['conditions']} | {x['n_is']} | {pc(x['bigup_is'])}→{pc(x['bigup_oos'])} | {pc(x['bigdown_is'])}→{pc(x['bigdown_oos'])} | "
                         f"{pc(x['big_is'])}→{pc(x['big_oos'])} | {f(x['mean_range_usd_is'])} | {f(x['mean_move_usd_oos'])} |")
        h = r["hour"]
        L += ["\n### NY 時間別（足の開始時刻）\n", "| NY時 | 足数 | 大陽線 | 大陰線 | 大きな足 | 平均値幅$ |", "|---|---|---|---|---|---|"]
        for _, x in h.iterrows():
            L.append(f"| {int(x['ny_hour'])} | {int(x['n'])} | {pc(x['bigup'])} | {pc(x['bigdown'])} | {pc(x['big'])} | {f(x['mean_range_usd'])} |")
        w = r["weekday"]
        L += ["\n### 曜日別\n", "| 曜日 | 足数 | 大陽線 | 大陰線 | 平均値幅$ |", "|---|---|---|---|---|"]
        for _, x in w.iterrows():
            L.append(f"| {wd[int(x['weekday'])]} | {int(x['n'])} | {pc(x['bigup'])} | {pc(x['bigdown'])} | {f(x['mean_range_usd'])} |")
    L.append("\n全条件の結果は candles_<時間足>.csv にあります。")
    return "\n".join(L) + "\n"
