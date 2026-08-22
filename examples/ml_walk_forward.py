"""Walk-forward classifier evaluation vs buy-and-hold / RSI / random baselines.

Usage:
  python examples/ml_walk_forward.py --synthetic
  python examples/ml_walk_forward.py --symbol BTCUSDT --exchange binanceus \\
      --start 2024-01-01 --stop 2025-01-01

Requires archive data unless ``--synthetic`` is passed.
"""

from __future__ import annotations

import argparse
import pprint
import sys

import numpy as np
import pandas as pd

from fast_trade.archive.db_helpers import get_kline
from fast_trade.ml.walk_forward import report_to_frame, walk_forward_evaluate


def _synthetic_ohlcv(rows: int = 1200, seed: int = 7, freq: str = "1h") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq=freq, tz="UTC")
    rets = rng.normal(0.0003, 0.01, size=rows)
    close = 100 * np.cumprod(1.0 + rets)
    high = close * (1.0 + rng.uniform(0.0, 0.008, size=rows))
    low = close * (1.0 - rng.uniform(0.0, 0.008, size=rows))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(100.0, 1000.0, size=rows)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _load_archive(symbol: str, exchange: str, start: str, stop: str, freq: str) -> pd.DataFrame:
    df = get_kline(symbol, exchange, start_date=start, end_date=stop, freq=freq)
    if df is None or df.empty:
        raise SystemExit(
            f"No archive data for {exchange}:{symbol}. "
            f"Download first or pass --synthetic.\n"
            f"  ft download {symbol} {exchange} --start {start} --end {stop}"
        )
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--exchange", default="binanceus")
    parser.add_argument("--freq", default="1h")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--stop", default="2025-01-01")
    parser.add_argument("--train-size", type=int, default=400)
    parser.add_argument("--test-size", type=int, default=100)
    parser.add_argument("--step-size", type=int, default=None)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--comission", type=float, default=0.01)
    parser.add_argument("--no-ta", action="store_true", help="Disable TA datapoint features")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use generated OHLCV instead of the local archive",
    )
    args = parser.parse_args(argv)

    if args.synthetic:
        # Enough bars for several folds with default train/test sizes.
        rows = max(args.train_size + args.test_size * 4, 900)
        df = _synthetic_ohlcv(rows=rows, freq=args.freq)
        print(f"Using synthetic OHLCV: {len(df)} rows @ {args.freq}")
    else:
        df = _load_archive(args.symbol, args.exchange, args.start, args.stop, args.freq)
        print(
            f"Loaded {args.exchange}:{args.symbol} "
            f"{df.index.min()} → {df.index.max()} ({len(df)} rows)"
        )

    report = walk_forward_evaluate(
        df,
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
        horizon=args.horizon,
        threshold=args.threshold,
        use_ta=not args.no_ta,
        freq=args.freq,
        comission=args.comission,
    )

    frame = report_to_frame(report)
    print("\nWalk-forward folds")
    print(
        frame[
            [
                "fold",
                "test_rows",
                "test_roc_auc",
                "ml_return_perc",
                "buy_hold_return_perc",
                "rsi_return_perc",
                "random_return_perc",
                "beats_buy_hold",
                "beats_rsi",
            ]
        ].to_string(index=False)
    )

    print("\nAggregate")
    pprint.pprint(report.aggregate)
    print(f"\nFeatures ({len(report.feature_columns)}): {report.feature_columns}")
    print(
        f"Label: forward {report.label_horizon} bars > {report.label_threshold:.2%} | "
        f"windows train={report.train_size} test={report.test_size} step={report.step_size}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
