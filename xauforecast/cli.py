"""コマンドライン: python -m xauforecast <command> ...

  fetch     データ取得（dukascopy / mt5 / csv）して保存（既存データに追記）
  synth     検証用の合成データを生成
  stats     統計情報を一括計算（JSON + Markdown）
  fit       予測モデルを学習して保存
  forecast  任意の時点（既定: 最新足）から 1分〜24時間先を予測（テキスト + JSON + HTML）
  backtest  ウォークフォワード検証
  live      データ更新 → 必要なら再学習 → 予測 を一定間隔で繰り返す
  all       stats + backtest + fit + forecast をまとめて実行
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from . import report
from .core import Grid
from .data import load_csv, merge, save_csv, synthetic
from .model import Forecaster

DEFAULT_DATA = "data/xauusd_m1.csv.gz"
DEFAULT_MODEL = "models/xauusd_forecaster.pkl"


def _load(path: str, tz: str | None = None, max_days: int | None = None) -> pd.DataFrame:
    df = load_csv(path, tz=tz)
    if max_days:
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=max_days)]
    print(f"データ: {path}  {df.index[0]} 〜 {df.index[-1]}  ({len(df):,} 本)", flush=True)
    return df


def _update(args, existing: pd.DataFrame | None) -> pd.DataFrame:
    from . import sources

    if args.source == "dukascopy":
        start = args.start if existing is None or existing.empty else (existing.index[-1] - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        new = sources.fetch_dukascopy(start=start or "2024-01-01", end=args.end, symbol=args.symbol, point=args.point,
                                      side=args.side, verbose=not getattr(args, "quiet", False))
    elif args.source == "mt5":
        if existing is None or existing.empty:
            new = sources.fetch_mt5(symbol=args.symbol, start=args.start, server_tz=args.tz or "NY+7")
        else:
            new = sources.fetch_mt5(symbol=args.symbol, bars=5000, server_tz=args.tz or "NY+7")
    elif args.source == "csv":
        new = load_csv(args.path, tz=args.tz)
    else:
        raise SystemExit(f"不明なソース: {args.source}")
    return merge(existing, new)


def cmd_fetch(args):
    out = Path(args.out)
    existing = load_csv(out) if out.exists() and not args.overwrite else None
    df = _update(args, existing)
    save_csv(df, out)
    print(f"保存: {out}  {df.index[0]} 〜 {df.index[-1]}  ({len(df):,} 本)")


def cmd_synth(args):
    df = synthetic(days=args.days, seed=args.seed)
    save_csv(df, args.out)
    print(f"合成データを保存: {args.out} ({len(df):,} 本)  ※実際の相場データではありません")


def cmd_stats(args):
    from .stats import collect_stats, load_events

    df = _load(args.data, args.tz, args.max_days)
    ev = load_events(args.events) if args.events else None
    st = collect_stats(df, events=ev)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report.dump_json(st, out / "stats.json")
    md = report.stats_markdown(st)
    (out / "stats.md").write_text(md, encoding="utf-8")
    print(f"保存: {out / 'stats.json'}, {out / 'stats.md'}")


def _fit(df: pd.DataFrame, model_path: str) -> tuple[Forecaster, Grid]:
    grid = Grid(df)
    m = Forecaster()
    print("モデル学習中…", flush=True)
    m.fit(grid, verbose=True)
    m.save(model_path)
    print(f"モデル保存: {model_path}")
    return m, grid


def cmd_fit(args):
    df = _load(args.data, args.tz, args.max_days)
    _fit(df, args.model)


def _get_model(args, df: pd.DataFrame, grid: Grid | None = None) -> tuple[Forecaster, Grid]:
    p = Path(args.model)
    if p.exists() and not getattr(args, "refit", False):
        m = Forecaster.load(p)
        age_h = (df.index[-1] - m.fit_end).total_seconds() / 3600
        if age_h <= args.refit_hours:
            return m, grid or Grid(df)
        print(f"モデルが古いため再学習します（学習末尾から {age_h:.1f} 時間経過）")
    return _fit(df, args.model)


def _do_forecast(args, df: pd.DataFrame, m: Forecaster, grid: Grid, bt: dict | None = None) -> dict:
    from .core import FeatureSet

    fs = FeatureSet(grid, m.profile)
    pos = grid.pos_of(args.at) if getattr(args, "at", None) else grid.n - 1
    fc = m.forecast(grid, fs, pos=pos, n_paths=args.paths)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report.dump_json(fc, out / "forecast.json")
    (out / "forecast.html").write_text(report.forecast_html(fc, bt), encoding="utf-8")
    print(report.forecast_text(fc))
    print(f"\n保存: {out / 'forecast.json'}, {out / 'forecast.html'}")
    return fc


def _model_for(args, df: pd.DataFrame) -> tuple[Forecaster, Grid]:
    """--at が過去の時刻なら、その時刻までのデータだけで学習（先読みなし）。"""
    if getattr(args, "at", None):
        at = pd.Timestamp(args.at)
        at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
        if at < df.index[-1]:
            grid = Grid(df)
            m = Forecaster()
            print(f"--at {at} までのデータのみで学習します（先読み防止）", flush=True)
            m.fit(grid, end=grid.pos_of(at) + 1, verbose=False)
            return m, grid
    return _get_model(args, df)


def cmd_forecast(args):
    df = _load(args.data, args.tz, args.max_days)
    m, grid = _model_for(args, df)
    bt = None
    btp = Path(args.out) / "backtest.json"
    if btp.exists():
        import json

        bt = json.loads(btp.read_text(encoding="utf-8"))
    _do_forecast(args, df, m, grid, bt)


def cmd_backtest(args):
    from .backtest import backtest

    df = _load(args.data, args.tz, args.max_days)
    bt = backtest(df, n_folds=args.folds, test_frac=args.test_frac, touch_origins=args.touch_origins)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report.dump_json(bt, out / "backtest.json")
    md = report.backtest_markdown(bt)
    (out / "backtest.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"保存: {out / 'backtest.json'}, {out / 'backtest.md'}")


def cmd_live(args):
    data_path = Path(args.data)
    while True:
        t0 = time.time()
        try:
            existing = load_csv(data_path) if data_path.exists() else None
            if args.source != "none":
                df = _update(args, existing)
                save_csv(df, data_path)
            else:
                df = existing
            if args.max_days:
                df = df[df.index >= df.index[-1] - pd.Timedelta(days=args.max_days)]
            m, grid = _get_model(args, df)
            print("\n" + "=" * 100)
            _do_forecast(args, df, m, grid)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # ネットワーク障害などでも止めない
            print(f"[{pd.Timestamp.now(tz='UTC')}] エラー: {type(e).__name__}: {e}", file=sys.stderr)
        if args.once:
            break
        time.sleep(max(1.0, args.interval - (time.time() - t0)))


def cmd_all(args):
    args_bt = argparse.Namespace(**vars(args))
    cmd_stats(args)
    cmd_backtest(args_bt)
    df = _load(args.data, args.tz, args.max_days)
    m, grid = _model_for(args, df) if args.at else _fit(df, args.model)
    import json

    bt = json.loads((Path(args.out) / "backtest.json").read_text(encoding="utf-8"))
    _do_forecast(args, df, m, grid, bt)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="xauforecast", description="XAUUSD 統計収集 & 1分〜24時間先の確率予測")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, data=True):
        if data:
            p.add_argument("--data", default=DEFAULT_DATA, help="1分足 CSV（.csv / .csv.gz）")
        p.add_argument("--tz", default=None, help="CSV の時刻のタイムゾーン（例: UTC, Asia/Tokyo, NY+7, UTC+2）")
        p.add_argument("--max-days", type=int, default=730, help="直近何日分を使うか（既定 730）")
        p.add_argument("--out", default="reports", help="出力ディレクトリ")

    def src(p):
        p.add_argument("--source", choices=["dukascopy", "mt5", "csv", "none"], default="dukascopy")
        p.add_argument("--start", default="2024-01-01")
        p.add_argument("--end", default=None)
        p.add_argument("--symbol", default="XAUUSD")
        p.add_argument("--point", type=float, default=1000.0, help="Dukascopy の価格倍率（XAUUSD は 1000）")
        p.add_argument("--side", default="BID", choices=["BID", "ASK"])
        p.add_argument("--path", default=None, help="--source csv のときの CSV パス")

    def model(p):
        p.add_argument("--model", default=DEFAULT_MODEL)
        p.add_argument("--refit-hours", type=float, default=24.0, help="学習末尾からこの時間を超えたら再学習")
        p.add_argument("--refit", action="store_true", help="必ず再学習する")
        p.add_argument("--paths", type=int, default=3000, help="モンテカルロのパス数")

    p = sub.add_parser("fetch", help="データ取得")
    src(p)
    p.add_argument("--tz", default=None)
    p.add_argument("--out", default=DEFAULT_DATA)
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("synth", help="合成データ生成（動作確認用）")
    p.add_argument("--days", type=int, default=420)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default="data/synthetic_m1.csv.gz")
    p.set_defaults(func=cmd_synth)

    p = sub.add_parser("stats", help="統計情報の一括計算")
    common(p)
    p.add_argument("--events", default=None, help="経済指標カレンダー CSV（time,name[,tz]）")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("fit", help="モデル学習")
    common(p)
    model(p)
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("forecast", help="予測")
    common(p)
    model(p)
    p.add_argument("--at", default=None, help="予測の基準時刻（UTC、例 '2025-06-06 12:30'）。省略時は最新足")
    p.set_defaults(func=cmd_forecast)

    p = sub.add_parser("backtest", help="ウォークフォワード検証")
    common(p)
    p.add_argument("--folds", type=int, default=4)
    p.add_argument("--test-frac", type=float, default=0.4)
    p.add_argument("--touch-origins", type=int, default=200)
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("live", help="定期的に データ更新→予測")
    common(p)
    src(p)
    model(p)
    p.add_argument("--interval", type=float, default=60.0, help="更新間隔（秒）")
    p.add_argument("--once", action="store_true")
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("all", help="stats + backtest + fit + forecast")
    common(p)
    model(p)
    p.add_argument("--events", default=None)
    p.add_argument("--folds", type=int, default=4)
    p.add_argument("--test-frac", type=float, default=0.4)
    p.add_argument("--touch-origins", type=int, default=200)
    p.add_argument("--at", default=None)
    p.set_defaults(func=cmd_all)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
