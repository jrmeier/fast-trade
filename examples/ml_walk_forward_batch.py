"""Screen a walk-forward config grid, promote winners, confirm on holdout.

Usage:
  python examples/ml_walk_forward_batch.py --synthetic --limit 8
  python examples/ml_walk_forward_batch.py --spec examples/ml_search.yml --limit 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fast_trade.archive.db_helpers import get_kline
from fast_trade.ml.search_batch import run_search
from fast_trade.ml.search_config import load_search_spec


def _synthetic_ohlcv(rows: int = 1600, seed: int = 7, freq: str = "1h") -> pd.DataFrame:
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
    parser.add_argument("--spec", default="examples/ml_search.yml")
    parser.add_argument("--limit", type=int, default=20, help="Max screen trials (dry-run default)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", default=None, help="Override output directory")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--no-promote", action="store_true")
    parser.add_argument("--no-holdout", action="store_true")
    args = parser.parse_args(argv)

    spec = load_search_spec(args.spec)
    if args.synthetic:
        df = _synthetic_ohlcv(freq=spec.freq)
        print(f"Using synthetic OHLCV: {len(df)} rows @ {spec.freq}")
        # Keep the locked relative split, but remap onto synthetic dates.
        start = df.index[0]
        cut = df.index[int(len(df) * 0.75)]
        stop = df.index[-1] + pd.Timedelta(hours=1)
        spec.data = type(spec.data)(
            search_start=str(start),
            search_stop=str(cut),
            holdout_start=str(cut),
            holdout_stop=str(stop),
        )
    else:
        start = spec.data.search_start or "2024-01-01"
        stop = spec.data.holdout_stop or spec.data.holdout_start
        df = _load_archive(spec.symbol, spec.exchange, start, stop, spec.freq)
        print(
            f"Loaded {spec.exchange}:{spec.symbol} "
            f"{df.index.min()} → {df.index.max()} ({len(df)} rows)"
        )

    payload = run_search(
        df,
        spec,
        run_dir=Path(args.out) if args.out else None,
        limit=args.limit,
        workers=args.workers,
        promote=not args.no_promote,
        confirm=not args.no_holdout,
    )
    ranked = payload["screen_ranked"]
    print(f"\nRun dir: {payload['run_dir']}")
    print(f"Search rows: {payload['search_rows']}")
    if ranked is not None and not ranked.empty:
        cols = [
            c
            for c in (
                "trial_id",
                "horizon",
                "threshold",
                "use_ta",
                "median_ml_return_perc",
                "pct_folds_beat_buy_hold",
                "total_ml_trades",
                "composite_score",
            )
            if c in ranked.columns
        ]
        print("\nScreen ranking")
        print(ranked[cols].head(10).to_string(index=False))
    holdout = payload["holdout"]
    if holdout is not None and not holdout.empty:
        print("\nHoldout confirmation")
        show = [
            c
            for c in (
                "trial_id",
                "median_ml_return_perc",
                "beats_buy_hold",
                "beats_rsi",
                "total_ml_trades",
                "passed",
            )
            if c in holdout.columns
        ]
        print(holdout[show].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
