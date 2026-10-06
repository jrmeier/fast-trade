"""Run a purged walk-forward evaluation and save a reproducible research report.

Examples:
  python examples/ml_walk_forward.py --synthetic
  python examples/ml_walk_forward.py --datafile ft_archive/coinbase/BTC-USD.parquet \
      --start 2025-01-01 --stop 2025-03-31 --comission 0.1 --out-dir ft_archive/research/btc-q1

Signals fill at the following bar close; commission is charged on both sides.
The report is a comparison of independent folds, not a live trading result.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
import pprint

import numpy as np
import polars as pl
import yaml

from fast_trade.archive.db_helpers import ARCHIVE_PATH, get_kline
from fast_trade.build_data_frame import parse_date_bound
from fast_trade.frames import freq_to_timedelta
from fast_trade.ml.walk_forward import report_to_frame, walk_forward_evaluate
from fast_trade.utils import resample_ohlcv


def _synthetic_ohlcv(rows: int, freq: str) -> pl.DataFrame:
    rng = np.random.default_rng(7)
    interval = freq_to_timedelta(freq)
    start = parse_date_bound("2024-01-01")
    dates = pl.datetime_range(start, start + (rows - 1) * interval, interval=interval, eager=True)
    close = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, rows))
    return pl.DataFrame({
        "date": dates, "open": np.r_[close[0], close[:-1]],
        "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": rng.uniform(100, 1000, rows),
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--exchange", default="coinbase")
    parser.add_argument("--datafile", type=Path, help="Local OHLCV Parquet file")
    parser.add_argument("--freq", default="1h")
    parser.add_argument("--start")
    parser.add_argument("--stop")
    parser.add_argument("--train-size", type=int, default=400)
    parser.add_argument("--test-size", type=int, default=100)
    parser.add_argument("--step-size", type=int)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--comission", type=float, default=0.01)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--signal-lag", type=int, default=1)
    parser.add_argument("--no-ta", action="store_true")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    if args.synthetic:
        df = _synthetic_ohlcv(max(args.train_size + args.test_size * 4 + 100, 900), args.freq)
        source = "synthetic, seed=7"
    elif args.datafile:
        df = resample_ohlcv(pl.read_parquet(args.datafile), args.freq)
        source = str(args.datafile)
    else:
        cache = Path(ARCHIVE_PATH) / args.exchange / f"{args.symbol}.parquet"
        if not cache.is_file():
            raise SystemExit("Local archive is missing; download data first or pass --datafile/--synthetic")
        df = get_kline(args.symbol, args.exchange, freq=args.freq)
        source = str(cache)
    for value, upper in ((args.start, False), (args.stop, True)):
        if value:
            bound = parse_date_bound(value, upper=upper)
            df = df.filter(pl.col("date") <= bound if upper else pl.col("date") >= bound)
    settings = {
        "train_size": args.train_size, "test_size": args.test_size, "step_size": args.step_size,
        "horizon": args.horizon, "threshold": args.threshold, "freq": args.freq,
        "comission": args.comission, "random_state": args.random_state,
        "signal_lag": args.signal_lag, "use_ta": not args.no_ta,
    }
    report = walk_forward_evaluate(df, **settings)
    frame = report_to_frame(report)
    print(f"Input: {source}, {df.height} bars, {df['date'].min()} to {df['date'].max()}")
    print(frame.select("fold", "test_roc_auc", "ml_return_perc", "buy_hold_return_perc", "rsi_return_perc"))
    pprint.pprint(report.aggregate)
    pprint.pprint(report.extras)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=False)
        snapshot = args.out_dir / "input.parquet"
        df.write_parquet(snapshot)
        frame.write_csv(args.out_dir / "folds.csv")
        payload = asdict(report)
        payload["environment"] = {
            "python": platform.python_version(),
            **{name: version(name) for name in ("fast-trade", "polars", "numpy", "scikit-learn")},
        }
        payload["input"] = {
            "source": source, "symbol": args.symbol, "exchange": args.exchange,
            "rows": df.height, "start": str(df["date"].min()), "stop": str(df["date"].max()),
            "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        }
        (args.out_dir / "report.yml").write_text(yaml.safe_dump(payload, sort_keys=False))
        (args.out_dir / "settings.yml").write_text(yaml.safe_dump(settings, sort_keys=False))
        print(f"Saved input snapshot, settings, report and folds to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
