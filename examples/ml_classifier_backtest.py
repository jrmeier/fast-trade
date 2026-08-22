"""Example: train a return classifier and backtest its ``ml_signal``.

Usage:
  python examples/ml_classifier_backtest.py
  python examples/ml_classifier_backtest.py --symbol BTCUSDT --exchange binanceus
  python examples/ml_classifier_backtest.py --synthetic

Requires archive data unless ``--synthetic`` is passed:
  ft download BTCUSDT binanceus --start 2024-01-01 --end 2025-01-01
"""

from __future__ import annotations

import argparse
import pprint
import sys

import numpy as np
import pandas as pd

from fast_trade.archive.db_helpers import get_kline
from fast_trade.ml.classifier import run_classifier_backtest


def _synthetic_ohlcv(rows: int = 1500, seed: int = 7, freq: str = "1h") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq=freq, tz="UTC")
    # Mild drift + noise so both label classes appear.
    rets = rng.normal(0.0004, 0.01, size=rows)
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
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--train-frac", type=float, default=0.7)
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use generated OHLCV instead of the local archive",
    )
    parser.add_argument(
        "--backtest-on",
        choices=("test", "all"),
        default="test",
        help="Backtest holdout only (default) or full usable history",
    )
    args = parser.parse_args(argv)

    if args.synthetic:
        df = _synthetic_ohlcv(freq=args.freq)
        print(f"Using synthetic OHLCV: {len(df)} rows @ {args.freq}")
    else:
        df = _load_archive(args.symbol, args.exchange, args.start, args.stop, args.freq)
        print(
            f"Loaded {args.exchange}:{args.symbol} "
            f"{df.index.min()} → {df.index.max()} ({len(df)} rows)"
        )

    result = run_classifier_backtest(
        df,
        horizon=args.horizon,
        threshold=args.threshold,
        train_frac=args.train_frac,
        backtest_on=args.backtest_on,
        strategy_overrides={
            "symbol": args.symbol,
            "exchange": args.exchange,
            "freq": args.freq,
        },
    )

    fit = result.fit
    print("\nClassifier")
    print(f"  features:        {fit.feature_columns}")
    print(f"  label:           forward {fit.label_horizon} bars > {fit.label_threshold:.2%}")
    print(f"  train / test:    {fit.train_rows} / {fit.test_rows}")
    print(f"  train accuracy:  {fit.train_accuracy:.3f}")
    print(f"  test accuracy:   {fit.test_accuracy:.3f}")
    if fit.test_roc_auc is not None:
        print(f"  test ROC AUC:    {fit.test_roc_auc:.3f}")
    print(f"  window:          {result.extras['test_start']} → {result.extras['test_end']}")

    summary = result.summary
    keep = [
        "return_perc",
        "equity_peak",
        "max_drawdown",
        "num_trades",
        "win_perc",
        "sharpe_ratio",
        "buy_and_hold_perc",
    ]
    slim = {k: summary.get(k) for k in keep if k in summary}
    print("\nBacktest summary (holdout)")
    pprint.pprint(slim)
    print(f"\nStrategy enter/exit: {result.strategy.get('enter')} / {result.strategy.get('exit')}")
    print("Datapoints:", result.strategy.get("datapoints"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
