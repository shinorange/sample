"""トレードルールの探索（値幅を取るルールを大量に試し、過剰最適化を厳しく除外する）。

ルール群（合計 約 2,300 個のパラメータ組み合わせ）:
  A. レンジブレイク     アジア・ロンドン序盤・COMEX/NY 開場・指標前などのレンジを抜けた方向に入る
  B. 時刻イベント       8:30/10:00/14:00 等の発表後 w 分の初動に順張り / 逆張り（雇用統計日のみも）
  C. 時間帯保有         NY 時間の a 時に買い（売り）、b 時に決済（全組み合わせ）
  D. 平均回帰           当日始値 / 当日 VWAP から k×ATR 乖離したら逆張り
  E. 前日高安ブレイク   前日高値・安値を抜けた方向に入る
  F. ギャップ埋め       週明け（または日次再開）の窓を埋める方向に入る
  G. 時系列モメンタム   過去 L 時間のリターンの方向に H 時間保有
  H. ドンチャン         N 時間の高値・安値ブレイク（N/2 の逆ブレイクで決済）
  I. RSI               1 時間足 RSI の過熱で逆張り / 順張り
  J. セッション順/逆張り アジア・ロンドン等の方向に、次の時間帯で順張り / 逆張り（日中モメンタム）

コスト: スプレッド（往復、既定 $0.30/oz）と、ストップ約定時のスリッページ（既定 $0.10/oz）。
同じ足でストップと利確の両方に届いた場合は、ストップが先と仮定（保守的）。

過剰最適化の対策:
  1. 期間分割: 前半 60% で探索（IS）、後半 40% は検証専用（OOS）
  2. 多重検定の補正: 全ルールの最大 t 値の分布を定常ブートストラップで求め（White の Reality Check /
     Romano-Wolf の single-step max-t）、「何千個も試した中の最良」であることを織り込んだ p 値を出す
  3. デフレート・シャープレシオ（試行回数とリターン分布の歪み・尖りを補正）
  4. 前進型の選択: 毎月、直近 6 か月で最良のルールを選び翌月に使う、という「探索の手順そのもの」の成績
採用条件: 補正後 p < 0.05、かつ OOS で平均がプラスかつ t > 1.65、かつ IS/OOS とも取引数が十分。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

NY = "America/New_York"
T = 1440  # 取引日の分数（NY 18:00 始まり）


def M(h: int, m: int = 0) -> int:
    """NY 時刻 h:m → 取引日の分インデックス（0 = 18:00 NY）。"""
    return ((h * 60 + m) - 1080) % 1440


# ---------------------------------------------------------------------------
# データ整形
# ---------------------------------------------------------------------------
@dataclass
class DayData:
    dates: pd.DatetimeIndex
    O: np.ndarray
    H: np.ndarray
    L: np.ndarray
    C: np.ndarray
    V: np.ndarray
    valid: np.ndarray
    atr: np.ndarray       # 過去 20 日の平均日中レンジ（$）
    prev_h: np.ndarray
    prev_l: np.ndarray
    prev_c: np.ndarray
    weekday: np.ndarray   # 取引日ラベルの曜日（0=月）
    nfp: np.ndarray       # 雇用統計日（第 1 金曜と推定）


def day_matrix(df: pd.DataFrame, min_bars: int = 600) -> DayData:
    ny = df.index.tz_convert(NY).tz_localize(None)
    sh = ny + pd.Timedelta(hours=6)  # 18:00 NY → 0:00
    day = sh.normalize()
    m = (sh.hour * 60 + sh.minute).to_numpy()
    codes, uniq = pd.factorize(day, sort=True)
    D = len(uniq)
    mats = {}
    for k in ("open", "high", "low", "close", "volume"):
        a = np.full((D, T), np.nan)
        a[codes, m] = df[k].to_numpy()
        mats[k] = a
    valid = ~np.isnan(mats["close"])
    n = valid.sum(1)
    keep = n >= min_bars
    C = pd.DataFrame(mats["close"]).ffill(axis=1).bfill(axis=1).to_numpy()
    O = np.where(valid, mats["open"], C)
    H = np.where(valid, mats["high"], C)
    L = np.where(valid, mats["low"], C)
    V = np.nan_to_num(mats["volume"])
    O, H, L, C, V, valid = O[keep], H[keep], L[keep], C[keep], V[keep], valid[keep]
    dates = pd.DatetimeIndex(uniq[keep])
    rng = H.max(1) - L.min(1)
    atr = pd.Series(rng).rolling(20, min_periods=5).mean().shift(1).bfill().to_numpy()
    prev_h = np.r_[np.nan, H.max(1)[:-1]]
    prev_l = np.r_[np.nan, L.min(1)[:-1]]
    prev_c = np.r_[np.nan, C[:-1, -1]]
    wd = dates.dayofweek.to_numpy()
    nfp = (wd == 4) & (dates.day.to_numpy() <= 7)
    return DayData(dates, O, H, L, C, V, valid, atr, prev_h, prev_l, prev_c, wd, nfp)


# ---------------------------------------------------------------------------
# 1 日 1 トレードのシミュレーション（全日をベクトル化）
# ---------------------------------------------------------------------------
def simulate(dd: DayData, e: np.ndarray, s: np.ndarray, px: np.ndarray, sl: np.ndarray, tp: np.ndarray,
             x: np.ndarray, spread: float, slip: float) -> dict:
    """e: エントリー足（-1 = 取引なし）、s: ±1、px: 約定価格、sl/tp: 価格（NaN = なし）、x: 決済時刻の足。"""
    D = len(e)
    trade = (e >= 0) & (s != 0) & (x > e)
    cols = np.arange(T)[None, :]
    e2, x2 = e[:, None], x[:, None]
    win = (cols > e2) & (cols <= x2) & trade[:, None]
    lng = (s > 0)[:, None]
    with np.errstate(invalid="ignore"):
        hit_sl = np.where(lng, dd.L <= sl[:, None], dd.H >= sl[:, None]) & win & ~np.isnan(sl)[:, None]
        hit_tp = np.where(lng, dd.H >= tp[:, None], dd.L <= tp[:, None]) & win & ~np.isnan(tp)[:, None]
    big = T + 5
    i_sl = np.where(hit_sl.any(1), hit_sl.argmax(1), big)
    i_tp = np.where(hit_tp.any(1), hit_tp.argmax(1), big)
    stop_first = (i_sl <= i_tp) & (i_sl < big)
    tp_first = (i_tp < i_sl) & (i_tp < big)
    xi = np.clip(x, 0, T - 1)
    exit_px = dd.C[np.arange(D), xi]
    # ストップ足で始値がストップを越えていれば始値で約定（窓開け）
    o_sl = dd.O[np.arange(D), np.clip(i_sl, 0, T - 1)]
    sl_fill = np.where(s > 0, np.minimum(sl, o_sl), np.maximum(sl, o_sl))
    exit_px = np.where(stop_first, sl_fill, np.where(tp_first, tp, exit_px))
    exit_i = np.where(stop_first, i_sl, np.where(tp_first, i_tp, xi))
    with np.errstate(invalid="ignore"):
        pnl = s * (exit_px - px) - spread - np.where(stop_first, slip, 0.0)
    pnl = np.where(trade, pnl, 0.0)
    # 最大含み益（MFE）
    upto = (cols > e2) & (cols <= exit_i[:, None]) & trade[:, None]
    fav = np.where(lng, dd.H - px[:, None], px[:, None] - dd.L)
    mfe = np.where(trade, np.nanmax(np.where(upto, fav, -np.inf), axis=1), 0.0)
    mfe = np.where(np.isfinite(mfe), np.maximum(mfe, 0), 0.0)
    ref = np.where(trade, px, 1.0)
    return {"pnl_usd": pnl, "pnl_bp": pnl / ref * 1e4, "trade": trade, "mfe_usd": mfe}


def _first_cross(dd: DayData, t0: int, t1: int, hi: np.ndarray, lo: np.ndarray, side: str):
    """[t0, t1) で最初に hi を上抜け / lo を下抜けした足と方向。両方同じ足ならその日は見送り。"""
    cols = np.arange(T)[None, :]
    w = (cols >= t0) & (cols < t1)
    up = (dd.H > hi[:, None]) & w if side in ("both", "long") else np.zeros_like(w & True)
    dn = (dd.L < lo[:, None]) & w if side in ("both", "short") else np.zeros_like(w & True)
    big = T + 5
    iu = np.where(up.any(1), up.argmax(1), big)
    idn = np.where(dn.any(1), dn.argmax(1), big)
    s = np.where(iu < idn, 1, np.where(idn < iu, -1, 0))
    e = np.where(s > 0, iu, np.where(s < 0, idn, -1))
    s = np.where((iu == idn) & (iu < big), 0, s)
    e = np.where(s == 0, -1, e)
    return e.astype(int), s.astype(int)


# ---------------------------------------------------------------------------
# ルール群
# ---------------------------------------------------------------------------
def family_range_breakout(dd: DayData, spread: float, slip: float):
    wins = [("アジア→ロンドン", M(18), M(3), M(12)), ("アジア後半→ロンドン", M(0), M(3), M(12)),
            ("ロンドン序盤30分", M(3), M(3, 30), M(12)), ("ロンドン→NY", M(3), M(8, 20), M(16)),
            ("COMEX開場15分", M(8, 20), M(8, 35), M(16)), ("COMEX開場30分", M(8, 20), M(8, 50), M(16)),
            ("NY株開場30分", M(9, 30), M(10), M(16)), ("指標前30分", M(8), M(8, 30), M(12))]
    D = len(dd.dates)
    idx = np.arange(D)
    for name, r0, r1, t1 in wins:
        hi = dd.H[:, r0:r1].max(1)
        lo = dd.L[:, r0:r1].min(1)
        width = hi - lo
        med = pd.Series(width).rolling(20, min_periods=5).median().shift(1).bfill().to_numpy()
        for side in ("both", "long", "short"):
            e, s = _first_cross(dd, r1, t1, hi, lo, side)
            o_e = dd.O[idx, np.clip(e, 0, T - 1)]
            px = np.where(s > 0, np.maximum(hi, o_e), np.minimum(lo, o_e))
            for stop_k in (1.0, 0.5):
                sl = np.where(s > 0, px - stop_k * width, px + stop_k * width)
                for tgt_k in (0.5, 1.0, 2.0, None):
                    tp = np.full(D, np.nan) if tgt_k is None else np.where(s > 0, px + tgt_k * width, px - tgt_k * width)
                    for hold in (120, None):
                        x = np.minimum(e + hold, t1) if hold else np.full(D, t1)
                        for filt in ("all", "narrow", "wide"):
                            ok = np.ones(D, bool) if filt == "all" else (width < med if filt == "narrow" else width >= med)
                            ee = np.where(ok & (width > 0), e, -1)
                            yield (f"A レンジブレイク {name} {side} 損切{stop_k}R 利確{tgt_k or '-'}R "
                                   f"{'保有2h' if hold else '時間切れ'} {filt}", "A",
                                   simulate(dd, ee, s, px, sl, tp, x, spread, slip))


def family_event(dd: DayData, spread: float, slip: float):
    D = len(dd.dates)
    idx = np.arange(D)
    times = [("8:30", 8, 30), ("10:00", 10, 0), ("14:00", 14, 0), ("8:20", 8, 20), ("9:30", 9, 30),
             ("3:00", 3, 0), ("20:00", 20, 0), ("18:00", 18, 0)]
    for name, hh, mm in times:
        t = M(hh, mm)
        for days in ("all", "nfp") if name == "8:30" else ("all",):
            ok = np.ones(D, bool) if days == "all" else dd.nfp
            for w in (1, 5, 15):
                e = np.full(D, t + w - 1)
                if t + w - 1 >= T - 1:
                    continue
                move = dd.C[:, t + w - 1] - dd.C[:, max(t - 1, 0)]
                for mode in ("順張り", "逆張り"):
                    s = np.sign(move).astype(int) * (1 if mode == "順張り" else -1)
                    px = dd.C[idx, e] + 0.0
                    for hold in (15, 60, 240):
                        x = np.minimum(e + hold, T - 1)
                        for stop in (None, 0.25):
                            sl = np.full(D, np.nan) if stop is None else px - s * stop * dd.atr
                            ee = np.where(ok & (s != 0), e, -1)
                            yield (f"B 時刻イベント {name}{'(雇用統計日)' if days == 'nfp' else ''} 初動{w}分{mode} "
                                   f"保有{hold}分 損切{stop or '-'}ATR", "B",
                                   simulate(dd, ee, s, px, sl, np.full(D, np.nan), x, spread, slip))


def family_time_of_day(dd: DayData, spread: float, slip: float):
    D = len(dd.dates)
    anchors = [M(h) for h in list(range(18, 24)) + list(range(0, 17))] + [T - 1]
    labels = [f"{h}時" for h in list(range(18, 24)) + list(range(0, 17))] + ["17時"]
    nan = np.full(D, np.nan)
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            a, b = anchors[i], anchors[j]
            ea = max(a - 1, 0)  # a 時の価格 = 直前の足の終値で約定
            for s0, lab in ((1, "買い"), (-1, "売り")):
                yield (f"C 時間帯保有 NY{labels[i]}→{labels[j]} {lab}", "C",
                       simulate(dd, np.full(D, ea), np.full(D, s0), dd.C[:, ea], nan, nan, np.full(D, b), spread, slip))


def family_mean_reversion(dd: DayData, spread: float, slip: float):
    D = len(dd.dates)
    idx = np.arange(D)
    t0, t1, tx = M(3), M(15), M(16)
    cpv = np.cumsum(dd.C * np.maximum(dd.V, 1e-9), axis=1)
    cv = np.cumsum(np.maximum(dd.V, 1e-9), axis=1)
    vwap = cpv / cv
    anchors = {"当日始値": np.repeat(dd.O[:, :1], T, axis=1), "VWAP": vwap}
    cols = np.arange(T)[None, :]
    w = (cols >= t0) & (cols < t1)
    for an, ref in anchors.items():
        for k in (0.3, 0.5, 0.8):
            dev = (dd.C - ref) / dd.atr[:, None]
            up = (dev > k) & w
            dn = (dev < -k) & w
            big = T + 5
            iu = np.where(up.any(1), up.argmax(1), big)
            idn = np.where(dn.any(1), dn.argmax(1), big)
            s = np.where(iu < idn, -1, np.where(idn < iu, 1, 0))
            e = np.where(s < 0, iu, np.where(s > 0, idn, -1))
            px = dd.C[idx, np.clip(e, 0, T - 1)]
            tgt = ref[idx, np.clip(e, 0, T - 1)]
            for stop in (0.25, 0.5):
                sl = px - s * stop * dd.atr
                yield (f"D 平均回帰 {an}から{k}ATR乖離で逆張り 損切{stop}ATR", "D",
                       simulate(dd, e, s, px, sl, tgt, np.full(D, tx), spread, slip))


def family_prior_day(dd: DayData, spread: float, slip: float):
    D = len(dd.dates)
    idx = np.arange(D)
    ok = ~np.isnan(dd.prev_h)
    hi = np.nan_to_num(dd.prev_h, nan=np.inf)
    lo = np.nan_to_num(dd.prev_l, nan=-np.inf)
    for side in ("both", "long", "short"):
        e, s = _first_cross(dd, 0, M(15), hi, lo, side)
        e = np.where(ok, e, -1)
        o_e = dd.O[idx, np.clip(e, 0, T - 1)]
        px = np.where(s > 0, np.maximum(hi, o_e), np.minimum(lo, o_e))
        for stop in ("前日終値", 0.5):
            sl = np.where(np.isnan(dd.prev_c), np.nan, dd.prev_c) if stop == "前日終値" else px - s * 0.5 * dd.atr
            sl = np.where((s > 0) & (sl >= px), px - 0.5 * dd.atr, np.where((s < 0) & (sl <= px), px + 0.5 * dd.atr, sl))
            for tgt in (0.5, 1.0, None):
                tp = np.full(D, np.nan) if tgt is None else px + s * tgt * dd.atr
                for xt in (M(16), T - 1):
                    yield (f"E 前日高安ブレイク {side} 損切{stop}{'' if stop == '前日終値' else 'ATR'} 利確{tgt or '-'}ATR "
                           f"決済{'16時' if xt == M(16) else '17時'}", "E",
                           simulate(dd, e, s, px, sl, tp, np.full(D, xt), spread, slip))


def family_gap(dd: DayData, spread: float, slip: float):
    D = len(dd.dates)
    gap = dd.O[:, 0] - dd.prev_c
    for which in ("週明け", "全日"):
        ok = (dd.weekday == 0) if which == "週明け" else np.ones(D, bool)
        ok = ok & ~np.isnan(gap)
        for k in (0.0, 0.1, 0.2):
            sel = ok & (np.abs(np.nan_to_num(gap)) > k * dd.atr)
            s = -np.sign(np.nan_to_num(gap)).astype(int)
            px = dd.O[:, 0]
            tp = dd.prev_c
            for sm in (1.0, 2.0):
                sl = px - s * sm * np.abs(np.nan_to_num(gap))
                for hold in (120, 480, T - 1):
                    yield (f"F ギャップ埋め {which} 窓>{k}ATR 損切{sm}×窓 保有{hold if hold < T - 1 else '終日'}", "F",
                           simulate(dd, np.where(sel & (s != 0), 0, -1), s, px, sl, tp, np.full(D, min(hold, T - 1)), spread, slip))


def family_session_momentum(dd: DayData, spread: float, slip: float):
    """あるセッションの方向に、次のセッションで順張り / 逆張りする（日中モメンタム）。"""
    D = len(dd.dates)
    nan = np.full(D, np.nan)
    sets = [("アジア(18-3時)", M(18), M(3), (M(5), M(8), M(12))),
            ("アジア後半(0-3時)", M(0), M(3), (M(5), M(8), M(12))),
            ("ロンドン(3-8:20)", M(3), M(8, 20), (M(10), M(12), M(16))),
            ("18時-8:20", M(18), M(8, 20), (M(10), M(12), M(16))),
            ("COMEX序盤(8:20-9:00)", M(8, 20), M(9), (M(11), M(16))),
            ("前日終値-8:50", -1, M(8, 50), (M(16, 59),)),
            ("18時-16:30", M(18), M(16, 30), (M(16, 59),))]
    for name, a, b, exits in sets:
        start_px = np.where(np.isnan(dd.prev_c), dd.O[:, 0], dd.prev_c) if a < 0 else (dd.O[:, 0] if a == 0 else dd.C[:, a - 1])
        ent = dd.C[:, b - 1]
        mv = ent - start_px
        entry_from = M(16, 30) if name == "前日終値-8:50" else b - 1
        if name == "前日終値-8:50":
            ent = dd.C[:, entry_from]
        for mode in ("順張り", "逆張り"):
            sgn = np.sign(mv).astype(int) * (1 if mode == "順張り" else -1)
            for xt in exits:
                if xt <= entry_from:
                    continue
                for stop in (None, 0.25):
                    sl = nan if stop is None else ent - sgn * stop * dd.atr
                    e = np.where(sgn != 0, entry_from, -1)
                    xl = f"{(xt + 1080) // 60 % 24}:{(xt + 1080) % 60:02d}"
                    yield (f"J セッション{mode} {name}の方向→{xl}まで 損切{stop or '-'}ATR", "J",
                           simulate(dd, e, sgn, ent, sl, nan, np.full(D, xt), spread, slip))


# ---------------------------------------------------------------------------
# 時間足ベースのルール（複数日にまたがる）
# ---------------------------------------------------------------------------
def hourly_frame(df: pd.DataFrame, dd: DayData) -> pd.DataFrame:
    h = df["close"].resample("1h", label="right", closed="right").last().dropna()
    ny = (h.index - pd.Timedelta(hours=1)).tz_convert(NY).tz_localize(None)
    day = (ny + pd.Timedelta(hours=6)).normalize()
    return pd.DataFrame({"close": h.to_numpy(), "day": day}, index=h.index)


def _pos_pnl(hf: pd.DataFrame, pos: np.ndarray, dd: DayData, spread: float) -> dict:
    c = hf["close"].to_numpy()
    r = np.r_[0.0, np.diff(c)]
    p_prev = np.r_[0.0, pos[:-1]]
    pnl = p_prev * r - np.abs(pos - p_prev) * spread / 2
    df = pd.DataFrame({"pnl": pnl, "bp": pnl / c * 1e4, "trade": np.abs(pos - p_prev) > 0, "day": hf["day"].to_numpy()})
    g = df.groupby("day").agg(pnl=("pnl", "sum"), bp=("bp", "sum"), trade=("trade", "any")).reindex(dd.dates).fillna(0)
    return {"pnl_usd": g["pnl"].to_numpy(), "pnl_bp": g["bp"].to_numpy(), "trade": g["trade"].to_numpy().astype(bool),
            "mfe_usd": np.full(len(dd.dates), np.nan)}


def family_hourly(hf: pd.DataFrame, dd: DayData, spread: float, slip: float):
    c = hf["close"].to_numpy()
    n = len(c)
    for L in (4, 8, 24, 72, 120):
        sig = np.sign(c - np.r_[np.full(L, np.nan), c[:-L]])
        for Hh in (1, 4, 8, 24):
            reb = (np.arange(n) % Hh) == 0
            pos = pd.Series(np.where(reb, np.nan_to_num(sig), np.nan)).ffill().fillna(0).to_numpy()
            for side, f in (("both", lambda p: p), ("long", lambda p: np.maximum(p, 0)), ("short", lambda p: np.minimum(p, 0))):
                yield f"G 時系列モメンタム 過去{L}h→保有{Hh}h {side}", "G", _pos_pnl(hf, f(pos), dd, spread)
    cs = pd.Series(c)
    for N in (20, 55, 100, 200):
        hi = cs.rolling(N).max().shift(1).to_numpy()
        lo = cs.rolling(N).min().shift(1).to_numpy()
        hx = cs.rolling(N // 2).max().shift(1).to_numpy()
        lx = cs.rolling(N // 2).min().shift(1).to_numpy()
        pos = np.zeros(n)
        p = 0.0
        for i in range(n):
            if p <= 0 and c[i] > hi[i]:
                p = 1.0
            elif p >= 0 and c[i] < lo[i]:
                p = -1.0
            elif p > 0 and c[i] < lx[i]:
                p = 0.0
            elif p < 0 and c[i] > hx[i]:
                p = 0.0
            pos[i] = p
        for side, f in (("both", lambda p: p), ("long", lambda p: np.maximum(p, 0)), ("short", lambda p: np.minimum(p, 0))):
            yield f"H ドンチャン {N}h {side}", "H", _pos_pnl(hf, f(pos), dd, spread)
    d = cs.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 * up / (up + dn)).to_numpy()
    for lo_t, hi_t in ((30, 70), (25, 75), (20, 80)):
        for Hh in (1, 4, 8):
            for mode in ("逆張り", "順張り"):
                raw = np.where(rsi < lo_t, 1, np.where(rsi > hi_t, -1, 0)) * (1 if mode == "逆張り" else -1)
                pos = np.zeros(n)
                left, cur = 0, 0
                for i in range(n):
                    if left > 0:
                        left -= 1
                    elif raw[i] != 0:
                        cur, left = raw[i], Hh - 1
                    else:
                        cur = 0
                    pos[i] = cur
                yield f"I RSI{lo_t}/{hi_t} {mode} 保有{Hh}h", "I", _pos_pnl(hf, pos, dd, spread)


FAMILY_NAMES = {"A": "レンジブレイク", "B": "時刻イベント", "C": "時間帯保有", "D": "平均回帰", "E": "前日高安ブレイク",
                "F": "ギャップ埋め", "G": "時系列モメンタム", "H": "ドンチャン", "I": "RSI", "J": "セッション順張り/逆張り"}


# ---------------------------------------------------------------------------
# 統計
# ---------------------------------------------------------------------------
def _stationary_bootstrap_idx(n: int, B: int, mean_block: float, rng) -> np.ndarray:
    p = 1.0 / mean_block
    idx = np.empty((B, n), dtype=np.int64)
    start = rng.integers(0, n, size=B)
    idx[:, 0] = start
    jump = rng.random((B, n)) < p
    new = rng.integers(0, n, size=(B, n))
    for t in range(1, n):
        idx[:, t] = np.where(jump[:, t], new[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def max_t_pvalues(X: np.ndarray, B: int = 1000, block: float = 5.0, seed: int = 0) -> np.ndarray:
    """X: ルール × 日 の日次損益。全ルールの最大 t 値の帰無分布から補正 p 値（single-step max-t）。"""
    rng = np.random.default_rng(seed)
    R, n = X.shape
    mu = X.mean(1)
    sd = X.std(1, ddof=1) + 1e-12
    t = mu / sd * np.sqrt(n)
    Xc = X - mu[:, None]
    idx = _stationary_bootstrap_idx(n, B, block, rng)
    maxt = np.empty(B)
    for b in range(B):
        xb = Xc[:, idx[b]]
        tb = xb.mean(1) / (xb.std(1, ddof=1) + 1e-12) * np.sqrt(n)
        maxt[b] = tb.max()
    return np.array([(maxt >= ti).mean() for ti in t])


def deflated_sharpe(sr: float, sr_all: np.ndarray, n: int, skew: float, kurt: float) -> float:
    """Bailey & López de Prado の DSR（日次 SR、N 回の試行を考慮）。"""
    N = max(len(sr_all), 2)
    v = np.var(sr_all, ddof=1)
    g = 0.5772156649
    sr0 = np.sqrt(v) * ((1 - g) * sps.norm.ppf(1 - 1 / N) + g * sps.norm.ppf(1 - 1 / (N * np.e)))
    den = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-9))
    return float(sps.norm.cdf((sr - sr0) * np.sqrt(n - 1) / den))


def _metrics(p_bp: np.ndarray, p_usd: np.ndarray, tr: np.ndarray, mfe: np.ndarray) -> dict:
    n = len(p_bp)
    nt = int(tr.sum())
    sd = p_bp.std(ddof=1) if n > 1 else np.nan
    t = p_bp.mean() / sd * np.sqrt(n) if sd and sd > 0 else 0.0
    eq = np.cumsum(p_usd)
    dd = float((eq - np.maximum.accumulate(eq)).min()) if n else 0.0
    w = p_usd[tr]
    gains, losses = w[w > 0].sum(), -w[w < 0].sum()
    return {"days": n, "trades": nt, "mean_bp_day": float(p_bp.mean()), "t": float(t),
            "sharpe_ann": float(p_bp.mean() / sd * np.sqrt(252)) if sd and sd > 0 else 0.0,
            "total_usd": float(p_usd.sum()), "per_trade_usd": float(w.mean()) if nt else 0.0,
            "win_rate": float((w > 0).mean()) if nt else 0.0, "profit_factor": float(gains / losses) if losses > 0 else np.inf,
            "avg_win_usd": float(w[w > 0].mean()) if (w > 0).any() else 0.0,
            "avg_loss_usd": float(w[w < 0].mean()) if (w < 0).any() else 0.0,
            "avg_mfe_usd": float(np.nanmean(mfe[tr])) if nt and np.isfinite(mfe[tr]).any() else None,
            "max_dd_usd": dd}


# ---------------------------------------------------------------------------
# 探索
# ---------------------------------------------------------------------------
def search(df: pd.DataFrame, spread: float = 0.30, slip: float = 0.10, is_frac: float = 0.6, top: int = 25,
           min_trades: int = 30, B: int = 1000, verbose: bool = True) -> dict:
    dd = day_matrix(df)
    hf = hourly_frame(df, dd)
    names, fams, P_bp, P_usd, TR, MFE = [], [], [], [], [], []
    gens = [family_range_breakout(dd, spread, slip), family_event(dd, spread, slip), family_time_of_day(dd, spread, slip),
            family_mean_reversion(dd, spread, slip), family_prior_day(dd, spread, slip), family_gap(dd, spread, slip),
            family_session_momentum(dd, spread, slip),
            family_hourly(hf, dd, spread, slip)]
    for g in gens:
        for name, fam, r in g:
            names.append(name)
            fams.append(fam)
            P_bp.append(r["pnl_bp"])
            P_usd.append(r["pnl_usd"])
            TR.append(r["trade"])
            MFE.append(r["mfe_usd"])
        if verbose:
            print(f"  ルール生成: {len(names)} 個", flush=True)
    P_bp, P_usd, TR, MFE = (np.array(a, dtype=float) for a in (P_bp, P_usd, TR, MFE))
    TR = TR.astype(bool)
    R, D = P_bp.shape
    cut = int(D * is_frac)
    IS, OOS = slice(0, cut), slice(cut, D)

    rows = []
    for i in range(R):
        a = _metrics(P_bp[i, IS], P_usd[i, IS], TR[i, IS], MFE[i, IS])
        b = _metrics(P_bp[i, OOS], P_usd[i, OOS], TR[i, OOS], MFE[i, OOS])
        rows.append({"rule": names[i], "family": fams[i], **{f"is_{k}": v for k, v in a.items()},
                     **{f"oos_{k}": v for k, v in b.items()}})
    tab = pd.DataFrame(rows)
    eligible = (tab["is_trades"] >= min_trades).to_numpy()
    if verbose:
        print(f"  多重検定の補正（ブートストラップ {B} 回、対象 {eligible.sum()} ルール）…", flush=True)
    p_adj = np.full(R, 1.0)
    p_adj[eligible] = max_t_pvalues(P_bp[eligible, IS], B=B)
    tab["p_adj"] = p_adj
    tab["p_raw"] = 2 * sps.norm.sf(np.abs(tab["is_t"]))
    sr_all = (tab.loc[eligible, "is_mean_bp_day"] / P_bp[eligible, IS].std(1, ddof=1)).to_numpy()
    dsr = np.full(R, np.nan)
    for i in np.where(eligible)[0]:
        x = P_bp[i, IS]
        sr = x.mean() / (x.std(ddof=1) + 1e-12)
        dsr[i] = deflated_sharpe(sr, sr_all, len(x), float(sps.skew(x)), float(sps.kurtosis(x, fisher=False)))
    tab["dsr"] = dsr
    tab["accepted"] = (tab["p_adj"] < 0.05) & (tab["oos_mean_bp_day"] > 0) & (tab["oos_t"] > 1.65) \
        & (tab["is_trades"] >= min_trades) & (tab["oos_trades"] >= min_trades // 2)

    # 前進型の選択: 毎月、直近 126 日の t 値が最大のルールを翌 21 日間使う
    wf_bp, wf_usd, wf_pick = [], [], []
    for st in range(126, D, 21):
        win = slice(st - 126, st)
        x = P_bp[:, win]
        ntr = TR[:, win].sum(1)
        tt = x.mean(1) / (x.std(1, ddof=1) + 1e-12) * np.sqrt(126)
        tt[ntr < 15] = -np.inf
        k = int(np.argmax(tt))
        en = min(st + 21, D)
        wf_bp.append(P_bp[k, st:en])
        wf_usd.append(P_usd[k, st:en])
        wf_pick.append({"from": str(dd.dates[st].date()), "rule": names[k], "trailing_t": float(tt[k]),
                        "next_usd": float(P_usd[k, st:en].sum())})
    wf = {}
    if wf_bp:
        a = np.concatenate(wf_bp)
        u = np.concatenate(wf_usd)
        sd = a.std(ddof=1)
        wf = {"days": int(len(a)), "mean_bp_day": float(a.mean()), "t": float(a.mean() / sd * np.sqrt(len(a))) if sd > 0 else 0.0,
              "sharpe_ann": float(a.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0, "total_usd": float(u.sum()), "picks": wf_pick}

    fam_sum = tab[eligible].groupby("family").agg(rules=("rule", "size"), best_is_t=("is_t", "max"),
                                                  mean_is_t=("is_t", "mean"), share_pos_oos=("oos_mean_bp_day", lambda s: (s > 0).mean()),
                                                  mean_oos_t=("oos_t", "mean")).reset_index()
    fam_sum["name"] = fam_sum["family"].map(FAMILY_NAMES)
    top_is = tab[eligible].sort_values("is_t", ascending=False).head(top)
    # 値幅: 平均 MFE が大きいルール（参考）
    rng_tab = tab[eligible & tab["is_avg_mfe_usd"].notna()].sort_values("is_avg_mfe_usd", ascending=False).head(10)
    return {
        "period": [str(dd.dates[0].date()), str(dd.dates[-1].date())], "is_period": [str(dd.dates[0].date()), str(dd.dates[cut - 1].date())],
        "oos_period": [str(dd.dates[cut].date()), str(dd.dates[-1].date())], "n_rules": int(R), "n_eligible": int(eligible.sum()),
        "spread": spread, "slip": slip, "table": tab, "top_is": top_is, "accepted": tab[tab["accepted"]].sort_values("p_adj"),
        "families": fam_sum, "walk_forward": wf, "range_capture": rng_tab,
        "expected_max_t_null": float(sps.norm.ppf(1 - 1 / max(eligible.sum(), 2))),
    }


def rules_markdown(res: dict) -> str:
    def f(v, d=2):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-"
        return f"{v:,.{d}f}"

    L = ["# トレードルール探索の結果\n",
         f"- 期間: {res['period'][0]} 〜 {res['period'][1]}（探索 IS: 〜{res['is_period'][1]} / 検証 OOS: {res['oos_period'][0]}〜）",
         f"- 試したルール: {res['n_rules']:,} 個（IS の取引数が十分なもの {res['n_eligible']:,} 個）",
         f"- コスト: スプレッド ${res['spread']:.2f}/oz（往復）、ストップ時スリッページ ${res['slip']:.2f}/oz",
         f"- 参考: これだけの数を試すと、まったく優位性がなくても最良ルールの t 値は {res['expected_max_t_null']:.1f} 前後になります。\n"]
    acc = res["accepted"]
    L.append("## 結論\n")
    if len(acc):
        L.append(f"**採用基準を満たしたルール: {len(acc)} 個**（多重検定補正後 p < 0.05、かつ検証期間でもプラスで t > 1.65）\n")
        L.append("| ルール | IS t | 補正p | DSR | IS 1日平均($) | OOS t | OOS 1日平均(bp) | OOS 勝率 | OOS 1回平均($) | OOS 合計($/oz) |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for _, r in acc.head(20).iterrows():
            L.append(f"| {r['rule']} | {f(r['is_t'])} | {f(r['p_adj'], 3)} | {f(r['dsr'], 3)} | {f(r['is_total_usd'] / max(r['is_days'], 1))} | "
                     f"{f(r['oos_t'])} | {f(r['oos_mean_bp_day'])} | {f(r['oos_win_rate'] * 100, 1)}% | {f(r['oos_per_trade_usd'])} | {f(r['oos_total_usd'])} |")
    else:
        L.append("**採用基準を満たしたルールはありませんでした。** IS で良く見えたルールも、試行回数を考慮すると偶然の範囲か、"
                 "検証期間で再現しませんでした。\n")
    wf = res["walk_forward"]
    if wf:
        L += ["\n## 「毎月、直近 6 か月で最良のルールに乗り換える」運用の成績\n",
              f"探索そのものに価値があるかの検証です。{wf['days']} 日間で 1日平均 {f(wf['mean_bp_day'])}bp、t={f(wf['t'])}、"
              f"年率シャープ {f(wf['sharpe_ann'])}、合計 ${f(wf['total_usd'])}/oz。\n"]
    L += ["\n## ルール群ごとの傾向\n", "| 群 | ルール数 | IS 最良 t | IS 平均 t | OOS でプラスの割合 | OOS 平均 t |", "|---|---|---|---|---|---|"]
    for _, r in res["families"].iterrows():
        L.append(f"| {r['family']} {r['name']} | {r['rules']} | {f(r['best_is_t'])} | {f(r['mean_is_t'])} | {f(r['share_pos_oos'] * 100, 0)}% | {f(r['mean_oos_t'])} |")
    L += ["\n## IS で t 値が高かった上位ルールの検証期間での成績\n",
          "IS（探索期間）だけで選ぶと、上位は偶然良かったものが混ざります。OOS の列で再現しているかを確認してください。\n",
          "| ルール | IS t | 補正p | IS 取引 | IS 勝率 | IS 1回平均($) | OOS t | OOS 取引 | OOS 勝率 | OOS 1回平均($) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in res["top_is"].iterrows():
        L.append(f"| {r['rule']} | {f(r['is_t'])} | {f(r['p_adj'], 3)} | {r['is_trades']} | {f(r['is_win_rate'] * 100, 1)}% | {f(r['is_per_trade_usd'])} | "
                 f"{f(r['oos_t'])} | {r['oos_trades']} | {f(r['oos_win_rate'] * 100, 1)}% | {f(r['oos_per_trade_usd'])} |")
    rc = res["range_capture"]
    if len(rc):
        L += ["\n## 値幅（最大含み益 MFE）が大きいルール（参考）\n", "動く局面を捉えているかの目安です。MFE が大きくても損益がプラスとは限りません。\n",
              "| ルール | 平均MFE($) | 1回平均損益($) | 平均利益($) | 平均損失($) | 勝率 | OOS 1回平均($) |", "|---|---|---|---|---|---|---|"]
        for _, r in rc.iterrows():
            L.append(f"| {r['rule']} | {f(r['is_avg_mfe_usd'])} | {f(r['is_per_trade_usd'])} | {f(r['is_avg_win_usd'])} | {f(r['is_avg_loss_usd'])} | "
                     f"{f(r['is_win_rate'] * 100, 1)}% | {f(r['oos_per_trade_usd'])} |")
    L.append("\n全ルールの成績は rules.csv にあります。損益は 1 オンス（XAUUSD 0.01 ロット）あたり。")
    return "\n".join(L) + "\n"
