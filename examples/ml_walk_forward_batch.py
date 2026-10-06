"""Run a bounded classifier search; holdout confirmation is explicit.

python examples/ml_walk_forward_batch.py --synthetic --limit 4 --workers 2
python examples/ml_walk_forward_batch.py --spec examples/ml_search.yml --datafile prices.parquet
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path

# Bound each process's native pools before importing Polars/numpy/sklearn.
for key in ("POLARS_MAX_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(key, "1")

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from fast_trade.archive.db_helpers import ARCHIVE_PATH, get_kline  # noqa: E402
from fast_trade.build_data_frame import parse_date_bound  # noqa: E402
from fast_trade.frames import freq_to_timedelta  # noqa: E402
from fast_trade.ml.search_batch import run_search  # noqa: E402
from fast_trade.ml.search_config import DataSplit, load_search_spec  # noqa: E402
from fast_trade.utils import resample_ohlcv  # noqa: E402


def _synthetic_ohlcv(freq: str) -> pl.DataFrame:
    rng = np.random.default_rng(7)
    interval = freq_to_timedelta(freq)
    start = parse_date_bound("2024-01-01")
    close = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, 1600))
    return pl.DataFrame({
        "date": pl.datetime_range(start, start + interval * 1599, interval=interval, eager=True),
        "open": np.r_[close[0], close[:-1]], "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": rng.uniform(100, 1000, 1600),
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=Path("examples/ml_search.yml"))
    parser.add_argument("--datafile", type=Path, help="Local OHLCV Parquet; no network download")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, help="New output directory; existing paths are rejected")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--no-promote", action="store_true")
    parser.add_argument("--confirm-holdout", action="store_true",
                        help="Evaluate the reserved window once after selection")
    args = parser.parse_args(argv)
    spec = load_search_spec(args.spec)
    if args.synthetic:
        df = _synthetic_ohlcv(spec.freq)
        cut = str(df["date"][1200])
        spec = replace(spec, symbol="SYNTHETIC", exchange="synthetic", data=DataSplit(
            search_start=str(df["date"][0]), search_stop=cut, holdout_start=cut,
            holdout_stop=str(df["date"][-1] + freq_to_timedelta(spec.freq)),
        ))
    elif args.datafile:
        df = resample_ohlcv(pl.read_parquet(args.datafile), spec.freq)
    else:
        cache = Path(ARCHIVE_PATH) / spec.exchange / f"{spec.symbol}.parquet"
        if not cache.is_file():
            raise SystemExit("Local archive missing; download first or pass --datafile/--synthetic")
        df = get_kline(spec.symbol, spec.exchange, freq=spec.freq)
    payload = run_search(df, spec, run_dir=args.out, limit=args.limit, workers=args.workers,
                         promote=not args.no_promote, confirm=args.confirm_holdout)
    print(f"Saved research run to {payload['run_dir']} ({payload['search_rows']} search bars)")
    ranked = payload["screen_ranked"]
    if not ranked.is_empty():
        print(ranked.select("trial_id", "median_ml_return_perc", "total_ml_trades", "composite_score").head(10))
    if not payload["holdout"].is_empty():
        print(payload["holdout"].select("trial_id", "median_ml_return_perc", "total_ml_trades", "passed"))
    failed = sum(result.status == "failed" for result in payload["screen"])
    print(f"Failed screen trials: {failed}; failures are saved and excluded from ranking.")
    return int(ranked.is_empty())


if __name__ == "__main__":
    raise SystemExit(main())
