"""統計・予測・検証結果の Markdown / テキスト / HTML 出力。"""
from __future__ import annotations

import html
import json
from typing import Any

import numpy as np


def _n(x, d=2, pct=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "-"
    if pct:
        return f"{x * 100:.{d}f}%"
    return f"{x:,.{d}f}"


def _get(d, key: str):
    """ネストしたキー取得。"a.b" は d["a"]["b"]。キー自体に "." を含む場合（"0.05" 等）も扱う。"""
    if not isinstance(d, dict):
        return None
    if key in d:
        return d[key]
    parts = key.split(".")
    for i in range(1, len(parts)):
        head = ".".join(parts[:i])
        if head in d:
            v = _get(d[head], ".".join(parts[i:]))
            if v is not None:
                return v
    return None


def _table(rows: list[dict], cols: list[tuple[str, str, Any]]) -> str:
    """cols: (見出し, キー, 書式関数)"""
    if not rows:
        return "_データなし_\n"
    head = "| " + " | ".join(c[0] for c in cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    body = ""
    for r in rows:
        vals = []
        for _, k, fmt in cols:
            v = _get(r, k)
            vals.append(fmt(v) if fmt else str(v))
        body += "| " + " | ".join(vals) + " |\n"
    return head + body


f2 = lambda v: _n(v, 2)
f1 = lambda v: _n(v, 1)
f3 = lambda v: _n(v, 3)
f4 = lambda v: _n(v, 4)
pc = lambda v: _n(v, 1, pct=True)
s_ = lambda v: "-" if v is None else str(v)
DOW = ["月", "火", "水", "木", "金", "土", "日"]


# ---------------------------------------------------------------------------
def stats_markdown(st: dict) -> str:
    b = st.get("basic", {})
    L = [f"# XAUUSD 統計レポート\n",
         f"- 期間: {b.get('start_utc')} 〜 {b.get('end_utc')} (UTC)",
         f"- 1分足本数: {b.get('bars'):,} / 取引日数: {b.get('trading_days')} / 想定取引時間に対するカバー率: {pc(b.get('coverage_vs_expected_open_minutes'))}",
         f"- 価格: 始 {f2(b.get('first_price'))} → 終 {f2(b.get('last_price'))}（安値 {f2(b.get('min_price'))} / 高値 {f2(b.get('max_price'))}）",
         f"- 期間リターン {f2(b.get('total_return_pct'))}% / 年率リターン {f2(b.get('annualized_return_pct'))}% / 年率ボラ {f2(b.get('annualized_vol_pct'))}%",
         f"- 1分足で終値が変化しない割合: {pc(b.get('zero_return_share_1m'))}\n"]

    c = st.get("current", {})
    if c and "error" not in c:
        L += ["## 現在の状況\n",
              f"- 最終足: {c.get('last_time_utc')} UTC / 東京 {c.get('last_time_tokyo')} / 価格 {f2(c.get('last_price'))}",
              f"- 脱季節化ボラ（過去1h/4h/1d/5d）の歴史的分位: {pc(c.get('deseasonalized_vol_1h_percentile'))} / {pc(c.get('deseasonalized_vol_4h_percentile'))} / "
              f"{pc(c.get('deseasonalized_vol_1d_percentile'))} / {pc(c.get('deseasonalized_vol_5d_percentile'))}",
              f"- RSI14: 15分足 {f1(c.get('rsi14_15min'))} / 1時間足 {f1(c.get('rsi14_1h'))}\n"]

    L += ["## 1. ホライズン別リターン分布（1分〜24時間）\n",
          "USD 換算は最新価格基準。尖度は正規分布=0。裾指数（Hill）が小さいほど裾が厚い（正規分布は∞、2〜4 が金融資産で典型）。\n",
          _table(st.get("horizons", []), [
              ("ホライズン", "label", s_), ("σ(bp)", "std_bp", f1), ("σ($)", "std_usd_at_last", f2),
              ("平均絶対変動($)", "mean_abs_usd_at_last", f2), ("平均(bp)", "mean_bp", f2), ("平均t値", "mean_t", f2),
              ("上昇率", "p_up", pc), ("下落率", "p_down", pc), ("歪度", "skew", f2), ("超過尖度", "excess_kurtosis", f1),
              ("裾指数", "hill_tail_index", f2), (">2σ", "p_abs_gt_2sd", pc), (">3σ", "p_abs_gt_3sd", pc)]),
          "\n### 分位点（USD、最新価格基準）\n",
          _table(st.get("horizons", []), [("ホライズン", "label", s_)] + [
              (f"{q}", f"quantiles_usd_at_last.{q}", f2) for q in ("0.01", "0.05", "0.25", "0.5", "0.75", "0.95", "0.99")])]

    sc = st.get("scaling", {})
    L += ["\n## 2. スケーリングとランダムウォーク検定\n",
          f"- σ(h) ∝ h^H の推定 H（全ホライズン）: **{f3(sc.get('hurst_scaling_all'))}**、30分以上: **{f3(sc.get('hurst_scaling_30m_plus'))}**",
          f"- {sc.get('interpretation', '')}\n",
          _table(sc.get("variance_ratio", []), [("q(本)", "q_bars", s_), ("分散比", "variance_ratio", f3),
                                                ("頑健z", "z_robust", f2), ("p値", "p_value", f4)])]

    ac = st.get("autocorr", {})
    L += ["\n## 3. 自己相関（リターン / 絶対リターン）\n"]
    rows = []
    for k in ("1m", "5m", "1h", "1d"):
        a = ac.get(k)
        if a:
            rows.append({"bar": k, "r1": a["acf_return"][0], "r2": a["acf_return"][1] if len(a["acf_return"]) > 1 else None,
                         "a1": a["acf_abs_return"][0], "a5": a["acf_abs_return"][4] if len(a["acf_abs_return"]) > 4 else None,
                         "lb": a["ljung_box_p"], "lba": a["ljung_box_abs_p"], "se": a["se_approx"]})
    L.append(_table(rows, [("足", "bar", s_), ("ρ1", "r1", f3), ("ρ2", "r2", f3), ("絶対値ρ1", "a1", f3), ("絶対値ρ5", "a5", f3),
                           ("LB p値(リターン)", "lb", f4), ("LB p値(絶対値)", "lba", f4), ("±1SE", "se", f3)]))
    lm = ac.get("abs_1m_long_memory")
    if lm:
        L.append("\n1分足 |r| の長期自己相関（ボラの持続性）: " + ", ".join(f"lag{l}={v:.3f}" for l, v in zip(lm["lags"], lm["acf"])) + "\n")

    se = st.get("seasonality", {})
    L += ["\n## 4. 季節性・時間帯効果\n", se.get("note", ""), "\n### NY 時間別（1分足ベース）\n",
          _table(se.get("by_ny_hour", []), [("NY時", "hour", s_), ("σ/分(bp)", "std_bp", f2), ("分散寄与", "share_of_variance_pct", f1),
                                            ("平均レンジ(bp)", "avg_range_bp", f2), ("1h平均(bp)", "hourly_return_mean_bp", f2),
                                            ("t値", "hourly_return_t", f2), ("1h上昇率", "hourly_p_up", pc), ("出来高", "avg_volume", f1)]),
          "\n### 曜日別（日次リターン）\n",
          _table([dict(r, dow=DOW[int(r["dow"])]) for r in se.get("by_weekday", [])],
                 [("曜日", "dow", s_), ("n", "n", s_), ("平均(bp)", "mean_bp", f1), ("σ(bp)", "std_bp", f1), ("t値", "t", f2), ("上昇率", "p_up", pc)]),
          "\n### 月別（日次リターン平均）\n",
          _table(se.get("by_month", []), [("月", "month", s_), ("n", "n", s_), ("平均(bp/日)", "mean_bp", f2), ("t値", "t", f2)])]
    tom = se.get("turn_of_month", {})
    if tom:
        L.append(f"\n月末月初（最終2日+最初3日）平均 {f2(tom.get('turn_of_month_mean_bp'))}bp (t={f2(tom.get('turn_of_month_t'))}) / その他 {f2(tom.get('rest_mean_bp'))}bp (t={f2(tom.get('rest_t'))})\n")
    mins = se.get("by_minute_of_hour", [])
    if mins:
        top = sorted(mins, key=lambda r: -(r.get("vol_ratio_vs_avg") or 0))[:8]
        L.append("\n毎時の「何分」でボラが高いか（上位）: " + ", ".join(f":{int(r['minute']):02d}={r['vol_ratio_vs_avg']:.2f}倍" for r in top) + "\n")
    ss = se.get("sessions_intraday", {})
    if ss:
        L += ["\n### セッション別\n", _table([dict(v, name=k) for k, v in ss.items()],
                                       [("セッション", "name", s_), ("分散寄与", "share_of_variance_pct", f1),
                                        ("σ/分(bp)", "std_bp_per_min", f2), ("平均出来高", "avg_volume", f1)])]
    L += ["\n### 週内で最もボラが高い時刻（NY 時間、平均比の σ 倍率）\n",
          ", ".join(f"{r['ny_time']} ({r['vol_multiple']:.1f}倍)" for r in st.get("top_slots", [])) + "\n"]

    L += ["\n## 5. 時刻イベント・経済指標\n",
          _table(st.get("time_events", []), [("イベント", "event", s_), ("時刻", "local_time", s_), ("日数", "n_days", s_),
                                             ("直後5分ボラ倍率", "vol_ratio_first5m_vs_prior30m", f2), ("30分ボラ倍率", "vol_ratio_next30m_vs_prior30m", f2),
                                             ("5分平均絶対変動(bp)", "mean_abs_move_5m_bp", f1), ("初動5分→55分相関", "corr_first5m_vs_next55m", f3)])]
    ev = [e for e in ([st.get("nfp")] + list(st.get("events") or [])) if e and "error" not in e]
    if ev:
        L += ["\n### 指標発表前後\n", _table(ev, [
            ("イベント", "event", s_), ("n", "n", s_), ("1分ボラ倍率", "vol_ratio_1m", f1), ("5分", "vol_ratio_5m", f1),
            ("60分", "vol_ratio_60m", f2), ("1分絶対変動 中央($)", "abs_move_1m_usd_median_at_last", f2),
            ("1時間 中央($)", "abs_move_60m_usd_median_at_last", f2), ("24時間 中央($)", "abs_move_1440m_usd_median_at_last", f2),
            ("初動→4h継続率", "p_continuation_4h", pc)])]
        if st.get("nfp", {}) and st["nfp"].get("note"):
            L.append(f"\n※ {st['nfp']['note']}\n")

    v = st.get("volatility", {})
    if v and "error" not in v:
        e = v.get("annualized_vol_estimators_pct", {})
        g = v.get("gjr_garch_5m_deseasonalized", {})
        rv = v.get("daily_realized_vol_ann_pct", {})
        h = v.get("har_rv_daily", {})
        lv = v.get("leverage_effect") or {}
        L += ["\n## 6. ボラティリティ\n",
              f"- 年率ボラ推定: 終値 {f1(e.get('close_to_close'))}% / Parkinson {f1(e.get('parkinson'))}% / Garman-Klass {f1(e.get('garman_klass'))}% / "
              f"Rogers-Satchell {f1(e.get('rogers_satchell'))}% / Yang-Zhang {f1(e.get('yang_zhang'))}%",
              f"- 日次実現ボラ(年率): 平均 {f1(rv.get('mean'))}% / 中央 {f1(rv.get('median'))}% / 10-90% {f1(rv.get('p10'))}〜{f1(rv.get('p90'))}% / 直近 {f1(rv.get('last'))}%（分位 {pc(rv.get('last_percentile'))}）",
              f"- ボラのボラ（log RV 日次変化の σ）: {f3(v.get('vol_of_vol_logRV_std'))} / log RV 自己相関(1,2,5,10,22日): {', '.join(f3(x) for x in (v.get('logRV_acf') or []))}",
              f"- 日次 HAR-RV: 日 {f3(h.get('b_daily'))} / 週 {f3(h.get('b_weekly'))} / 月 {f3(h.get('b_monthly'))} / R² {f3(h.get('r2'))}",
              f"- GJR-GARCH(5分, 脱季節化): α={f3(g.get('alpha'))} γ={f3(g.get('gamma_leverage'))} β={f3(g.get('beta'))} 持続性={f4(g.get('persistence'))} "
              f"半減期 ≈ {f1(g.get('half_life_hours_of_trading'))} 取引時間",
              f"  - {g.get('leverage_note', '')}",
              f"- レバレッジ効果: 当日リターン↔翌日logRV 相関 {f3(lv.get('corr_return_vs_next_day_logRV'))}（下落部分 {f3(lv.get('corr_neg_return_vs_next_logRV'))} / 上昇部分 {f3(lv.get('corr_pos_return_vs_next_logRV'))}）",
              f"- ATR14(日足): ${f2(v.get('atr14_usd_last'))} / 日中レンジ 平均 ${f2((v.get('daily_range_usd') or {}).get('mean'))}・中央 ${f2((v.get('daily_range_usd') or {}).get('median'))}・90% ${f2((v.get('daily_range_usd') or {}).get('p90'))}\n"]

    L += ["\n## 7. 値幅（高値-安値）と最大上昇/下落幅\n",
          _table(st.get("ranges", []), [("ホライズン", "label", s_), ("レンジ中央($)", "range_usd_at_last.p50", f2),
                                        ("レンジ10%($)", "range_usd_at_last.p10", f2), ("レンジ90%($)", "range_usd_at_last.p90", f2),
                                        ("最大上昇 中央(bp)", "max_up_bp.p50", f1), ("最大上昇 90%(bp)", "max_up_bp.p90", f1),
                                        ("最大下落 中央(bp)", "max_down_bp.p50", f1), ("最大下落 90%(bp)", "max_down_bp.p90", f1)]),
          "\n### 価格到達確率（経験値）\n",
          _table(st.get("touch", []), [("±%", "pct", f2), ("$", "usd_at_last", f2),
                                       ("15分↑", "p_touch_up_15m", pc), ("15分↓", "p_touch_down_15m", pc),
                                       ("1h↑", "p_touch_up_60m", pc), ("1h↓", "p_touch_down_60m", pc),
                                       ("4h↑", "p_touch_up_240m", pc), ("4h↓", "p_touch_down_240m", pc),
                                       ("24h↑", "p_touch_up_1440m", pc), ("24h↓", "p_touch_down_1440m", pc),
                                       ("上が先", "p_up_first_within_24h", pc)])]

    co = st.get("conditional", {})
    if co and "error" not in co:
        L += ["\n## 8. 条件付き統計（モメンタム / 平均回帰 / テクニカル）\n",
              "t 値の絶対値が 2〜3 未満の差は偶然の範囲と考えてください（多重比較に注意）。\n",
              "\n### 過去 h のリターン五分位 → 次の h のリターン（非重複サンプル）\n"]
        rows = []
        for m in co.get("momentum_reversal", []):
            r = {"label": m["label"], "n": m["n"], "rho": m["spearman"], "p": m["p_value"]}
            for t in m["table"]:
                r[f"q{t['quintile']}"] = t["next_mean_bp"]
            rows.append(r)
        L.append(_table(rows, [("h", "label", s_), ("n", "n", s_), ("順位相関", "rho", f3), ("p値", "p", f4)] +
                        [(f"Q{i}次(bp)", f"q{i}", f2) for i in range(1, 6)]))
        L += ["\n### RSI(14) 別の次足リターン\n",
              _table(co.get("rsi", []), [("足", "bars", s_), ("先(本)", "ahead_bars", s_), ("RSI", "rsi_bin", s_), ("n", "n", s_),
                                         ("平均(bp)", "next_mean_bp", f2), ("t値", "t", f2), ("上昇率", "p_up", pc)]),
              "\n### 1時間足 EMA 乖離五分位 → 先のリターン\n",
              _table(co.get("ema_deviation_1h", []), [("EMA", "ema", s_), ("先(h)", "ahead_h", s_), ("五分位", "quintile", s_),
                                                       ("乖離z", "dev_mean", f2), ("平均(bp)", "next_mean_bp", f2), ("t値", "t", f2), ("上昇率", "p_up", pc)]),
              "\n### ボラ局面別（前日の実現ボラ三分位）→ 翌日\n",
              _table(co.get("vol_regime_daily", []), [("局面", "regime", s_), ("n", "n", s_), ("翌日ボラ(年率%)", "next_day_vol_ann_pct", f1),
                                                       ("翌日平均(bp)", "next_day_mean_bp", f1), ("t値", "next_day_t", f2), ("翌日上昇率", "next_day_p_up", pc)]),
              "\n### 連続陽線・陰線の後\n",
              _table([r for r in co.get("streaks", []) if "after" in r],
                     [("足", "bars", s_), ("条件", "after", s_), ("n", "n", s_), ("次も同方向", "p_same_direction_next", pc)]),
              "\n" + "\n".join(f"- ラン検定({r['bars']}): z={f2(r['runs_test_z'])}（{r['note']}）" for r in co.get("streaks", []) if "runs_test_z" in r) + "\n"]

    ses = st.get("sessions", {})
    if ses and "error" not in ses:
        L += ["\n## 9. セッション間の関係\n",
              _table([{"s": k, "m": ses["session_return_mean_bp"][k], "t": ses["session_return_t"][k], "sd": ses["session_return_std_bp"][k]}
                      for k in ses.get("session_return_mean_bp", {})],
                     [("セッション", "s", s_), ("平均(bp)", "m", f2), ("t値", "t", f2), ("σ(bp)", "sd", f1)]),
              "\n", _table(ses.get("consecutive_session_links", []), [("前", "from", s_), ("次", "to", s_), ("相関", "corr", f3),
                                                                   ("同符号率", "p_same_sign", pc), ("n", "n", s_)])]

    gp = st.get("gaps", {})
    if gp and "error" not in gp:
        L += ["\n## 10. ギャップ（窓）\n", _table([dict(v, k=("週明け" if k == "weekend" else "日次再開")) for k, v in gp.items()],
                                             [("種類", "k", s_), ("n", "n", s_), ("平均窓幅(bp)", "mean_abs_bp", f1), ("平均窓幅($)", "mean_abs_usd_at_last", f2),
                                              ("90%(bp)", "p90_abs_bp", f1), ("最大(bp)", "max_abs_bp", f1), ("上窓率", "p_up", pc),
                                              ("24h内窓埋め率", "p_fill_within_24h", pc)])]
    L += ["\n## 11. キリ番（ラウンドナンバー）\n",
          _table(st.get("round_numbers", []), [("刻み($)", "level_step_usd", s_), ("接近回数", "n_touches", s_),
                                               ("60分後に反発側", "p_reject_after_60m", pc), ("基準(中間価格)", "baseline_p_reject_mid_levels", pc)])]
    vo = st.get("volume", {})
    if vo and "error" not in vo:
        nx = vo.get("next15m_abs_move_bp_by_rel_volume", {})
        L += ["\n## 12. 出来高（ティックボリューム）\n",
              f"- 1分足 出来高と|リターン|の相関: {f3(vo.get('corr_volume_abs_return_1m'))}（順位相関 {f3(vo.get('spearman_volume_abs_return_1m'))}）",
              f"- 相対出来高別の次15分 平均|変動|: 中央値未満 {f2(nx.get('rel<median'))}bp / 上位10% {f2(nx.get('rel>p90'))}bp / 上位1% {f2(nx.get('rel>p99'))}bp\n"]
    tr = st.get("trend", {})
    if tr and "error" not in tr:
        L += ["\n## 13. トレンド\n", "\n".join(f"- {k}: {f2(v)}" for k, v in tr.items()) + "\n"]
    ex = st.get("extremes", {})
    if ex and "error" not in ex:
        L += ["\n## 14. 過去最大の変動\n"]
        for k, lab in (("1m", "1分"), ("1h", "1時間"), ("1d", "1日")):
            L.append(f"- {lab}: " + ", ".join(f"{r['time'][:16]} ({r['return_pct']:+.2f}%)" for r in ex.get(k, [])[:5]))
        L.append("")
    ad = st.get("advanced", {})
    if ad and "error" not in ad:
        L += ["\n## 15. 高度な統計\n"]
        j = ad.get("jumps", {})
        L.append(f"- **ジャンプ**（BNS 検定、5分足）: 有意なジャンプを含む日 {pc(j.get('share_days_jump_p001'))}、分散に占めるジャンプの平均比率 {pc(j.get('mean_jump_share_of_variance'))}")
        sv = ad.get("semivariance", {})
        if sv:
            L.append(f"- **セミ分散**: 下方の分散比率 {pc(sv.get('mean_downside_share'))}。翌日 log RV との相関 下方 {f3(sv.get('corr_downside_vs_next_logRV'))} / 上方 {f3(sv.get('corr_upside_vs_next_logRV'))}")
        im = ad.get("intraday_momentum", {})
        if im:
            L.append(f"- **日中モメンタム**（前日終値→8:50 NY が 16:30-17:00 を予測するか）: 相関 {f3(im.get('corr'))}、t={f2(im.get('t'))}、n={im.get('n')}")
        pe = ad.get("permutation_entropy", {})
        L.append(f"- **順列エントロピー**（1 = 完全ランダム）: 1分 {f4(pe.get('1m'))} / 15分 {f4(pe.get('15m'))} / 1時間 {f4(pe.get('1h'))}")
        dh = ad.get("dfa_hurst", {})
        L.append(f"- **DFA Hurst**: リターン {f3(dh.get('returns_1m'))} / 絶対リターン {f3(dh.get('abs_returns_1m'))}（{dh.get('note', '')}）")
        sp = ad.get("spectral_peaks_abs_return", [])
        if sp:
            L.append("- **ボラの周期**（|1分リターン| のスペクトルのピーク）: " + "、".join(f"{p_['period_min'] / 60:.1f}時間" for p_ in sp[:8]))
        mk = ad.get("markov_1h_terciles")
        if mk:
            L += ["\n### 1時間足の遷移確率（三分位: 下落 / 横ばい / 上昇）\n",
                  _table([{"from": lab, **{f"to{j_}": mk["transition"][i][j_] for j_ in range(3)}} for i, lab in enumerate(mk["labels"])],
                         [("前の足", "from", s_)] + [(f"次:{lab}", f"to{j_}", pc) for j_, lab in enumerate(mk["labels"])]),
                  f"\n独立性の χ² 検定 p値 = {f4(mk.get('p_value'))}（小さいほど前の足が次の足に影響。主にボラの持続性による）\n"]
        vr = ad.get("vol_regimes")
        if vr:
            L.append(f"- **ボラ局面**（日次 log RV の 2 状態混合分布）: 低ボラ {f1(vr.get('low_vol_ann_pct'))}% / 高ボラ {f1(vr.get('high_vol_ann_pct'))}%、"
                     f"高ボラの日の比率 {pc(vr.get('share_high'))}、継続確率 低 {pc(vr.get('p_stay_low'))} / 高 {pc(vr.get('p_stay_high'))}、"
                     f"平均継続 低 {f1(vr.get('expected_days_low'))} 日 / 高 {f1(vr.get('expected_days_high'))} 日、現在: **{vr.get('current')}**")
        ec = ad.get("extreme_clustering_1h")
        if ec:
            L.append(f"- **極端な変動の連鎖**（1時間足、±2σ 超）: 通常 {pc(ec.get('p_big'))} → 直前が大変動なら {pc(ec.get('p_big_after_big'))}。大変動の次の足が同じ方向 {pc(ec.get('p_same_direction_after_big'))}")
        tf = ad.get("student_t_df", {})
        L.append("- **裾の厚さ**（Student-t の自由度。小さいほど裾が厚い、正規分布は∞）: " + " / ".join(f"{k} {f1(v)}" for k, v in tf.items()))
        pb = ad.get("prior_day_break", {})
        L.append(f"- **前日高値・安値のブレイク**: 高値更新 {pc(pb.get('p_break_high'))} / 安値更新 {pc(pb.get('p_break_low'))} / 両方 {pc(pb.get('p_both'))} / はらみ足 {pc(pb.get('p_inside_day'))}")
        hl = ad.get("high_low_timing_ny_hour", {})
        if hl:
            hours = sorted({int(k) for k in list(hl.get("high", {})) + list(hl.get("low", {}))})
            L += ["\n### 日中の高値・安値がつく時間帯（NY 時間）\n",
                  _table([{"h": h, "hi": hl["high"].get(str(h), hl["high"].get(h)), "lo": hl["low"].get(str(h), hl["low"].get(h))} for h in hours],
                         [("NY時", "h", s_), ("高値がつく割合", "hi", pc), ("安値がつく割合", "lo", pc)])]
    errs = [k for k, v in st.items() if isinstance(v, dict) and "error" in v]
    if errs:
        L.append("\n> 計算できなかった項目: " + ", ".join(f"{k} ({st[k]['error']})" for k in errs))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
def forecast_text(fc: dict) -> str:
    L = [f"XAUUSD 予測  基準: {fc['origin_utc']} UTC（東京 {fc['origin_tokyo'][:16]}）  現在値 {fc['price']:.2f}",
         f"モデル学習データ末尾: {fc['model_trained_until']}", "",
         f"{'先':>6} {'中央値':>9} {'σ($)':>7} {'90%区間':>21} {'50%区間':>21} {'上昇':>6} {'下落':>6} {'予想高値':>9} {'予想安値':>9} {'取引分':>5} 方向モデル"]
    for h in fc["horizons"]:
        q = h["quantiles"]
        L.append(f"{h['label']:>6} {h['median']:9.2f} {h['sigma_usd']:7.2f} {q['0.05']:9.2f}〜{q['0.95']:9.2f}  "
                 f"{q['0.25']:9.2f}〜{q['0.75']:9.2f} {h['p_up'] * 100:5.1f}% {h['p_down'] * 100:5.1f}% "
                 f"{h['expected_high']:9.2f} {h['expected_low']:9.2f} {h.get('trading_minutes', h['h']):5d} {'有効' if h['mean_model_active'] else '-'}")
    if any(h.get("trading_minutes", h["h"]) < 0.5 * h["h"] for h in fc["horizons"]):
        L.append("※ 「取引分」が期間より短いホライズンは、週末・日次休止などの休場を含みます（休場中は価格が動かない前提）。")
    L += ["", "価格到達確率（モンテカルロ、ヒゲ含む）:",
          f"{'±%':>5} {'±$':>7} {'1h↑':>6} {'1h↓':>6} {'4h↑':>6} {'4h↓':>6} {'24h↑':>6} {'24h↓':>6} {'上が先':>6}"]
    for t in fc["touch"]:
        L.append(f"{t['pct']:5.2f} {t['usd']:7.2f} " + " ".join(
            f"{t.get(k, float('nan')) * 100:5.1f}%" for k in ("p_up_60", "p_down_60", "p_up_240", "p_down_240", "p_up_1440", "p_down_1440"))
                 + f" {t['p_up_first'] * 100 if t['p_up_first'] == t['p_up_first'] else float('nan'):5.1f}%")
    L += explain_text(fc)
    L += ["", "注: 金価格の方向は統計的にほぼ予測不能です。ここに示すのは確率分布であり、確定的な予想ではありません。"]
    return "\n".join(L)


COMP_JA = {"ridge": "線形", "gbm": "GBM", "analog": "類似局面", "season": "時間帯統計"}


def explain_text(fc: dict) -> list[str]:
    from .features import feature_label

    ex = fc.get("explain")
    if not ex:
        return []
    L = ["", f"予測の根拠（使用した特徴量 {fc.get('n_features', '?')} 個）:",
         f"{'先':>6} {'HARのσ($)':>10} {'補正後σ($)':>10} {'補正倍率':>8} {'ボラ局面':>6}  方向: 予測器の寄与($)"]
    for h in fc["horizons"]:
        comp = h.get("components_usd", {})
        cs = " ".join(f"{COMP_JA[c]}{v:+.3f}" for c, v in comp.items() if v) or "なし（ドリフト0）"
        L.append(f"{h['label']:>6} {h.get('sigma_har_usd', 0):10.2f} {h['sigma_usd']:10.2f} {h.get('vol_adjust_factor', 1):8.2f} "
                 f"{h.get('vol_regime_bucket', ''):>6}  {cs}")
    fsr = ex.get("feature_stats", [])
    if fsr:
        hs = sorted({int(k[3:]) for k in fsr[0] if k.startswith("ic_")})
        L += ["", "現在の統計量（予測力の高い順、IC=将来リターンとの順位相関・学習期間）:",
              f"{'特徴量':<30} {'現在の分位':>8} " + " ".join(f"{'IC'+str(h)+'分':>9} {'t':>6}" for h in hs)]
        for r in fsr[:12]:
            L.append(f"{feature_label(r['feature'])[:28]:<30} {r['percentile'] * 100:7.0f}% " +
                     " ".join(f"{r.get(f'ic_{h}', 0):+9.4f} {r.get(f't_{h}', 0):+6.1f}" for h in hs))
    an = ex.get("analogs", {})
    if an.get("by_horizon"):
        L += ["", f"類似局面（過去で最も似た {an['k']} 局面のその後）:",
              f"{'先':>6} {'上昇率':>7} {'中央値($)':>10} {'10%($)':>9} {'90%($)':>9}"]
        for r in an["by_horizon"]:
            L.append(f"{r['label']:>6} {r['p_up'] * 100:6.1f}% {r['median_usd']:+10.2f} {r['q10_usd']:+9.2f} {r['q90_usd']:+9.2f}")
        L.append("最も似た局面: " + ", ".join(f"{r['time_utc']}(24h後 {r.get('ret_1440_pct') or 0:+.2f}%)" for r in an.get("nearest", [])[:5]))
    return L


def forecast_html(fc: dict, backtest: dict | None = None) -> str:
    W, Hh, padl, padr, padt, padb = 920, 420, 64, 16, 16, 36
    hist, fan = fc["history"], fc["fan"]
    xs_h = hist["minutes"]
    xs_f = fan["minutes"]
    xmin, xmax = min(xs_h), max(xs_f)
    vals = hist["close"] + fan["0.05"] + fan["0.95"]
    ymin, ymax = min(vals), max(vals)
    pad = (ymax - ymin) * 0.06 or 1
    ymin, ymax = ymin - pad, ymax + pad
    X = lambda m: padl + (m - xmin) / (xmax - xmin) * (W - padl - padr)
    Y = lambda p: padt + (ymax - p) / (ymax - ymin) * (Hh - padt - padb)
    pts = lambda xs, ys: " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(xs, ys))
    p0 = fc["price"]
    band = lambda lo, hi: pts([0] + xs_f, [p0] + fan[lo]) + " " + pts(([0] + xs_f)[::-1], ([p0] + fan[hi])[::-1])
    yt = np.linspace(ymin + pad, ymax - pad, 5)
    grid_lines = "".join(f'<line x1="{padl}" x2="{W - padr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="gl"/>'
                         f'<text x="{padl - 6}" y="{Y(v) + 4:.1f}" class="ax" text-anchor="end">{v:,.1f}</text>' for v in yt)
    xt = [m for m in (-360, -180, 0, 60, 240, 480, 720, 1080, 1440) if xmin <= m <= xmax]
    x_lab = "".join(f'<text x="{X(m):.1f}" y="{Hh - 12}" class="ax" text-anchor="middle">{("+" if m > 0 else "") + (str(m // 60) + "h" if m else "現在")}</text>' for m in xt)
    svg = f'''<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="価格予測ファンチャート">
{grid_lines}{x_lab}
<line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{padt}" y2="{Hh - padb}" class="now"/>
<polygon points="{band('0.05', '0.95')}" class="b90"/><polygon points="{band('0.25', '0.75')}" class="b50"/>
<polyline points="{pts([0] + xs_f, [p0] + fan['0.5'])}" class="med"/>
<polyline points="{pts(xs_h, hist['close'])}" class="hist"/>
</svg>'''
    rows = "".join(
        f"<tr><td>{h['label']}</td><td>{h['target_time_utc'][5:16]}</td><td class=n>{h['median']:,.2f}</td><td class=n>±{h['sigma_usd']:,.2f}</td>"
        f"<td class=n>{h['quantiles']['0.05']:,.2f} – {h['quantiles']['0.95']:,.2f}</td><td class=n>{h['quantiles']['0.25']:,.2f} – {h['quantiles']['0.75']:,.2f}</td>"
        f"<td class=n>{h['p_up'] * 100:.1f}%</td><td class=n>{h['expected_high']:,.2f}</td><td class=n>{h['expected_low']:,.2f}</td><td class=n>{h.get('trading_minutes', h['h'])}</td>"
        f"<td>{'有効' if h['mean_model_active'] else '—'}</td></tr>" for h in fc["horizons"])
    trows = "".join(
        f"<tr><td class=n>±{t['pct']:g}%</td><td class=n>${t['usd']:,.2f}</td>" + "".join(
            f"<td class=n>{t.get(k, float('nan')) * 100:.1f}%</td>" for k in ("p_up_60", "p_down_60", "p_up_240", "p_down_240", "p_up_1440", "p_down_1440"))
        + f"<td class=n>{(t['p_up_first'] or 0) * 100:.1f}%</td></tr>" for t in fc["touch"])
    bt = ""
    if backtest:
        bt_rows = "".join(f"<tr><td>{r['label']}</td><td class=n>{r['cover_50'] * 100:.1f}%</td><td class=n>{r['cover_90'] * 100:.1f}%</td>"
                          f"<td class=n>{r['cover_98'] * 100:.1f}%</td><td class=n>{r['qlike_skill_pct']:.1f}%</td><td class=n>{r['pinball_skill_pct']:.1f}%</td>"
                          f"<td class=n>{r['brier_skill_pct']:.2f}%</td></tr>" for r in backtest.get("horizons", []))
        bt = f'''<h2>過去検証（ウォークフォワード）</h2><p class=sub>名目 50% / 90% / 98% 区間に実際に収まった割合。ボラ改善率・分位点損失改善率は無条件分布との比較、方向は 50% 予測との比較。</p>
<div class=tw><table><thead><tr><th>先</th><th>50%区間</th><th>90%区間</th><th>98%区間</th><th>ボラ予測 改善</th><th>分位点損失 改善</th><th>方向 Brier 改善</th></tr></thead><tbody>{bt_rows}</tbody></table></div>'''
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XAUUSD 予測</title><style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6a66;--line:#e4e2dc;--acc:#b8860b;--b90:rgba(184,134,11,.14);--b50:rgba(184,134,11,.32);--hist:#3a3a38}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#161614;--fg:#ecebe7;--mut:#a3a29d;--line:#33322f;--acc:#e0b04a;--b90:rgba(224,176,74,.14);--b50:rgba(224,176,74,.32);--hist:#d6d5d0}}}}
:root[data-theme="dark"]{{--bg:#161614;--fg:#ecebe7;--mut:#a3a29d;--line:#33322f;--acc:#e0b04a;--b90:rgba(224,176,74,.14);--b50:rgba(224,176,74,.32);--hist:#d6d5d0}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:17px;margin:32px 0 6px}}
.sub{{color:var(--mut);font-size:13px;margin:0 0 12px}}.kpi{{display:flex;gap:28px;flex-wrap:wrap;margin:14px 0 8px}}.kpi b{{display:block;font-size:24px;font-variant-numeric:tabular-nums}}.kpi span{{color:var(--mut);font-size:12px}}
svg{{width:100%;height:auto;display:block}}.gl{{stroke:var(--line)}}.ax{{fill:var(--mut);font-size:11px}}.now{{stroke:var(--mut);stroke-dasharray:3 3}}
.b90{{fill:var(--b90)}}.b50{{fill:var(--b50)}}.med{{fill:none;stroke:var(--acc);stroke-width:2}}.hist{{fill:none;stroke:var(--hist);stroke-width:1.4}}
.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}th{{color:var(--mut);font-weight:500}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}.note{{color:var(--mut);font-size:12.5px;margin-top:28px;border-top:1px solid var(--line);padding-top:12px}}
</style></head><body><main>
<h1>XAUUSD 確率予測</h1><p class=sub>基準時刻 {html.escape(fc['origin_utc'][:16])} UTC（東京 {html.escape(fc['origin_tokyo'][:16])}）・学習データ末尾 {html.escape(str(fc['model_trained_until'])[:16])}</p>
<div class=kpi><div><span>現在値</span><b>{p0:,.2f}</b></div><div><span>1時間後 90%区間</span><b>{_hz(fc, 60, '0.05'):,.1f} – {_hz(fc, 60, '0.95'):,.1f}</b></div>
<div><span>24時間後 90%区間</span><b>{_hz(fc, 1440, '0.05'):,.1f} – {_hz(fc, 1440, '0.95'):,.1f}</b></div><div><span>24時間後 上昇確率</span><b>{_hzp(fc, 1440):.1f}%</b></div></div>
{svg}<p class=sub>線: 直近6時間の実績 / 濃い帯: 50%区間 / 薄い帯: 90%区間 / 金色線: 中央値（モンテカルロ {len(fan['minutes'])*5//60}時間分）</p>
<h2>ホライズン別予測</h2><div class=tw><table><thead><tr><th>先</th><th>対象時刻(UTC)</th><th>中央値</th><th>σ</th><th>90%区間</th><th>50%区間</th><th>上昇確率</th><th>予想高値</th><th>予想安値</th><th>取引分</th><th>方向モデル</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>価格到達確率</h2><p class=sub>現在値から ±x% の価格に、期間内に一度でも到達する確率（高値・安値ベース）。「上が先」は上下どちらかに到達した場合に上が先である確率。</p>
<div class=tw><table><thead><tr><th>幅</th><th>$</th><th>1h ↑</th><th>1h ↓</th><th>4h ↑</th><th>4h ↓</th><th>24h ↑</th><th>24h ↓</th><th>上が先</th></tr></thead><tbody>{trows}</tbody></table></div>
{explain_html(fc)}
{bt}
<p class=note>価格の方向は統計的にほぼランダムで、確実な予測はできません。このページは「どのくらい動きうるか」の確率分布を示すもので、投資判断の保証ではありません。方向モデルは過去検証で有意な予測力が確認されたホライズンでのみ有効化され、それ以外はドリフト 0 として扱います。</p>
</main></body></html>'''


def explain_html(fc: dict) -> str:
    from .features import feature_label

    ex = fc.get("explain")
    if not ex:
        return ""
    e = html.escape
    rows = "".join(
        f"<tr><td>{h['label']}</td><td class=n>±{h.get('sigma_har_usd', 0):,.2f}</td><td class=n>±{h['sigma_usd']:,.2f}</td>"
        f"<td class=n>{h.get('vol_adjust_factor', 1):.2f}倍</td><td>{e(h.get('vol_regime_bucket', ''))}</td>"
        + "".join(f"<td class=n>{h.get('components_usd', {}).get(c, 0):+.3f}</td>" for c in COMP_JA) + "</tr>"
        for h in fc["horizons"])
    fsr = ex.get("feature_stats", [])
    hs = sorted({int(k[3:]) for k in fsr[0] if k.startswith("ic_")}) if fsr else []
    frows = "".join(
        f"<tr><td>{e(feature_label(r['feature']))}</td><td>{e(r['group'])}</td><td class=n>{r['percentile'] * 100:.0f}%</td>"
        + "".join(f"<td class=n>{r.get(f'ic_{h}', 0):+.4f}</td><td class=n>{r.get(f't_{h}', 0):+.1f}</td>" for h in hs) + "</tr>"
        for r in fsr[:15])
    fhead = "".join(f"<th>IC {h}分</th><th>t</th>" for h in hs)
    an = ex.get("analogs", {})
    arows = "".join(f"<tr><td>{r['label']}</td><td class=n>{r['p_up'] * 100:.1f}%</td><td class=n>{r['median_usd']:+,.2f}</td>"
                    f"<td class=n>{r['q10_usd']:+,.2f} – {r['q90_usd']:+,.2f}</td></tr>" for r in an.get("by_horizon", []))
    near = "、".join(f"{e(r['time_utc'])}（24h後 {r.get('ret_1440_pct') or 0:+.2f}%）" for r in an.get("nearest", [])[:6])
    return f'''<h2>予測の根拠</h2><p class=sub>特徴量 {fc.get('n_features', '?')} 個を使用。ボラは HAR 回帰の予測を全特徴量の勾配ブースティングで補正（検証で改善したホライズンのみ）。方向は 4 つの予測器のうち、検証で有意だったものだけを重み付けして合成（寄与は $ 換算）。</p>
<div class=tw><table><thead><tr><th>先</th><th>HAR の σ</th><th>補正後 σ</th><th>補正倍率</th><th>ボラ局面</th><th>線形</th><th>GBM</th><th>類似局面</th><th>時間帯統計</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>現在の統計量</h2><p class=sub>将来リターンとの順位相関（IC）が大きい特徴量の順。「現在の分位」は学習期間の分布の中での現在値の位置。</p>
<div class=tw><table><thead><tr><th>統計量</th><th>分類</th><th>現在の分位</th>{fhead}</tr></thead><tbody>{frows}</tbody></table></div>
<h2>類似局面</h2><p class=sub>主要な統計量が現在と最も似ている過去 {an.get('k', 0)} 局面の、その後の値動き（現在価格に換算）。最も似た局面: {near}</p>
<div class=tw><table><thead><tr><th>先</th><th>上昇した割合</th><th>中央値 $</th><th>10–90% $</th></tr></thead><tbody>{arows}</tbody></table></div>'''


def features_markdown(m) -> str:
    """全特徴量の予測力と、モデル各部の採否のレポート。"""
    from .features import feature_label
    from .model import COMPONENTS

    t = m.feature_ic_table()
    L = [f"# 特徴量（統計量）の予測力とモデル構成\n", f"- 学習データ末尾: {m.fit_end}",
         f"- 特徴量: {len(m.feature_names)} 個（" + "、".join(f"{g} {n}" for g, n in t['group'].value_counts().items()) + "）\n",
         "## ホライズン別のモデル構成\n",
         "ボラ補正 = 勾配ブースティングによる HAR 残差の補正で、前進型の検証での log 実現分散の二乗誤差が何 % 減ったか。"
         "方向の t 値は各予測器の前進型の検証での予測力（ゲート閾値を超えたものだけ採用）。\n"]
    rows = []
    for h, hm in sorted(m.models.items()):
        r = {"label": f"{h}分" if h < 60 else f"{h // 60}時間", "vg": hm.vol_gain_pct, "vu": "採用" if hm.vol_gbm is not None else "-",
             "act": "採用" if hm.active else "ドリフト0", "t": hm.t_val}
        for c in COMPONENTS:
            r[f"t_{c}"] = hm.comp_stats[c]["t"]
            r[f"w_{c}"] = hm.comp_weights[c]
        rows.append(r)
    L.append(_table(rows, [("先", "label", s_), ("ボラ補正(%)", "vg", f1), ("ボラ補正", "vu", s_)] +
                    [(f"t {COMP_JA[c]}", f"t_{c}", f1) for c in COMPONENTS] +
                    [(f"重み {COMP_JA[c]}", f"w_{c}", f3) for c in COMPONENTS] + [("方向", "act", s_), ("合成 t", "t", f1)]))
    L.append("\n## 分類別の平均 |t|（将来リターンとの順位相関）\n")
    hs = [h for h in sorted(m.models)]
    g = t.groupby("group")[[f"t_{h}" for h in hs]].apply(lambda x: x.abs().mean()).reset_index()
    L.append(_table(g.to_dict("records"), [("分類", "group", s_)] + [(f"{h}分" if h < 60 else f"{h // 60}時間", f"t_{h}", f1) for h in hs]))
    for h in [x for x in (1, 15, 60, 240, 1440) if x in m.models]:
        top = t.reindex(t[f"t_{h}"].abs().sort_values(ascending=False).index).head(15)
        L.append(f"\n## {h}分先 の予測力が高い統計量 上位15\n" if h < 60 else f"\n## {h // 60}時間先 の予測力が高い統計量 上位15\n")
        L.append(_table([dict(r, label=feature_label(r["feature"])) for r in top.to_dict("records")],
                        [("統計量", "label", s_), ("名前", "feature", s_), ("分類", "group", s_), ("IC", f"ic_{h}", f4), ("t", f"t_{h}", f1)]))
    L.append("\n|t| が 3 未満は偶然の範囲と考えてください（特徴量が多いため多重比較に注意）。全表は feature_ic.csv にあります。\n")
    return "\n".join(L) + "\n"


def _hz(fc, h, q):
    for x in fc["horizons"]:
        if x["h"] == h:
            return x["quantiles"][q]
    return float("nan")


def _hzp(fc, h):
    for x in fc["horizons"]:
        if x["h"] == h:
            return x["p_up"] * 100
    return float("nan")


def backtest_markdown(bt: dict) -> str:
    L = ["# ウォークフォワード検証結果\n", f"- 検証期間: {bt['period_test'][0]} 〜 {bt['period_test'][1]}（{bt['n_folds']} 分割、各分割の直前までで再学習）\n",
         "## 予測区間の較正（名目値に近いほど良い）\n",
         _table(bt["horizons"], [("先", "label", s_), ("n", "n", s_), ("50%", "cover_50", pc), ("80%", "cover_80", pc), ("90%", "cover_90", pc),
                                 ("95%", "cover_95", pc), ("98%", "cover_98", pc), ("PIT KS", "pit_ks", f3)]),
         "\n## 予測力（ベンチマーク比の改善率。正なら改善）\n",
         "- ボラ: QLIKE 損失（無条件ボラ比）/ 分位点: pinball 損失（無条件分布比）/ 方向: Brier（常に 50% 予測比）\n",
         _table(bt["horizons"], [("先", "label", s_), ("ボラ改善", "qlike_skill_pct", f1), ("log分散相関", "vol_corr", f3),
                                 ("分位点改善", "pinball_skill_pct", f2), ("方向Brier改善", "brier_skill_pct", f3),
                                 ("方向IC", "ic", f4), ("方向モデル有効率", "mean_model_active_share", pc), ("有効時の的中率", "hit_rate_when_active", pc)])]
    if bt["horizons"] and "qlike_skill_har_only_pct" in bt["horizons"][0]:
        L += ["\n## 構成要素の寄与（検証期間）\n",
              "ボラ: HAR 単独と、全特徴量 GBM 補正後の QLIKE 改善率。方向: 各予測器の生の予測値と実際のリターンの相関（採用されていない予測器も計算）。\n",
              _table(bt["horizons"], [("先", "label", s_), ("ボラ HAR単独", "qlike_skill_har_only_pct", f1), ("ボラ 補正後", "qlike_skill_pct", f1)] +
                     [(f"IC {v}", f"ic_{k}", f4) for k, v in COMP_JA.items()])]
    if bt.get("touch_calibration"):
        L += ["\n## 価格到達確率の較正（予測平均 vs 実際の頻度）\n",
              _table(bt["touch_calibration"], [("期間(分)", "h", s_), ("±%", "pct", f2), ("予測", "pred", pc), ("実際", "actual", pc), ("n", "n", s_)]),
              f"\nBrier スコア: {f4(bt.get('touch_brier'))}\n"]
    return "\n".join(L) + "\n"


def dump_json(obj: dict, path) -> None:
    def conv(o):
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return str(o)

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, default=conv)
