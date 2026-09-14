#!/usr/bin/env python
"""Benchmark EMA-cross + RSI backtests at 2y / 5y / 10y 1m lengths.

The local archive currently holds ~1 year of live BTCUSDT 1m bars. Longer
windows are built by tiling that real series with date shifts so bar counts
match the calendar length. Use this for engine throughput, not strategy PnL.

Examples:
  python scripts/bench_multi_year.py
  python scripts/bench_multi_year.py --years 2 5 10 --repeat 3
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fast_trade.build_data_frame import prepare_df
from fast_trade.build_summary import build_summary
from fast_trade.run_analysis import apply_logic_to_df
from fast_trade.run_backtest import (
    prepare_new_backtest,
    process_logic_and_generate_actions,
    run_backtest,
)
from scripts.bench_strategy_backtest import basic_strategy

DEFAULT_SRC = Path("ft_archive/binanceus/BTCUSDT.parquet")
DEFAULT_STOP = dt.datetime(2026, 9, 12)


def timed(fn: Callable[[], Any], repeat: int) -> tuple[Any, dict]:
    result = fn()
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return result, {
        "mean_s": round(statistics.mean(times), 4),
        "min_s": round(min(times), 4),
        "max_s": round(max(times), 4),
        "repeat": repeat,
    }


def build_tiled(src: pl.DataFrame, years: int, stop: dt.datetime) -> pl.DataFrame:
    start = stop - dt.timedelta(days=365 * years)
    pieces = []
    for i in range(years):
        shift_years = years - 1 - i
        pieces.append(
            src.with_columns(
                (pl.col("date") - pl.duration(days=365 * shift_years)).alias("date")
            )
        )
    return (
        pl.concat(pieces)
        .unique(subset=["date"], keep="last")
        .sort("date")
        .filter((pl.col("date") >= start) & (pl.col("date") <= stop))
    )


def with_summary_cols(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.col("adj_account_value").pct_change().alias("adj_account_value_change_perc"),
        pl.col("adj_account_value").diff().alias("adj_account_value_change"),
    )


def bench_stages(backtest: dict, raw: pl.DataFrame, repeat: int) -> dict:
    prepared = prepare_df(raw, backtest)

    def indicators():
        return prepare_df(raw, backtest)

    _, ind_stats = timed(indicators, repeat)

    with_actions = process_logic_and_generate_actions(prepared, backtest)

    def actions():
        return process_logic_and_generate_actions(prepared, backtest)

    _, action_stats = timed(actions, repeat)

    def simulate():
        return with_summary_cols(apply_logic_to_df(with_actions, backtest))

    simulated, sim_stats = timed(simulate, repeat)

    started = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    def summary():
        return build_summary(simulated, started)

    _, summary_stats = timed(summary, repeat)

    return {
        "rows": len(with_actions),
        "prepare_indicators": ind_stats,
        "generate_actions": action_stats,
        "simulate_account": sim_stats,
        "build_summary": summary_stats,
    }


def run_horizon(
    src: pl.DataFrame,
    years: int,
    stop: dt.datetime,
    symbol: str,
    exchange: str,
    freq: str,
    repeat: int,
) -> dict:
    df = build_tiled(src, years, stop)
    start = (stop - dt.timedelta(days=365 * years)).date().isoformat()
    stop_s = stop.date().isoformat()
    backtest = prepare_new_backtest(
        basic_strategy(symbol, exchange, start, stop_s, freq)
    )
    print(f"\n=== {years}y  {start} → {stop_s}  input_rows={df.height:,} ===")

    result, e2e = timed(lambda: run_backtest(backtest, df), repeat)
    out_df = result.get("df")
    stages = bench_stages(backtest, df, repeat)
    row = {
        "years": years,
        "start": start,
        "stop": stop_s,
        "freq": freq,
        "input_rows": df.height,
        "output_rows": len(out_df) if out_df is not None else 0,
        "run_backtest_e2e": e2e,
        "stages": {k: v for k, v in stages.items() if k != "rows"},
        "stage_rows": stages["rows"],
        "data_note": (
            "1m BTCUSDT bars tiled from live 1y archive (date-shifted) "
            "to match calendar length; throughput benchmark"
        ),
    }
    print(f"output_rows={row['output_rows']:,}")
    print(f"run_backtest_e2e={e2e}")
    print("stages:")
    for name, stats in row["stages"].items():
        print(f"  {name}={stats}")
    return row


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--exchange", default="binanceus")
    parser.add_argument("--freq", default="1Min")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--years", type=int, nargs="+", default=[2, 5, 10])
    parser.add_argument("--stop", default=DEFAULT_STOP.date().isoformat())
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/bench_multi_year_results.json"),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    src = pl.read_parquet(args.src).sort("date")
    stop = dt.datetime.fromisoformat(args.stop)
    print(f"source rows={src.height:,}  {src['date'].min()} → {src['date'].max()}")

    results = [
        run_horizon(
            src,
            years,
            stop,
            args.symbol,
            args.exchange,
            args.freq,
            args.repeat,
        )
        for years in args.years
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
