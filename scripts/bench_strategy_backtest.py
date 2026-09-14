#!/usr/bin/env python
"""Benchmark a basic strategy backtest on 1m archive data.

Reports wall times for the full ``run_backtest`` path and the main stages
(load → indicators → actions → simulation → summary) so 1m slowdowns are
easy to spot.

Examples:
  python scripts/bench_strategy_backtest.py
  python scripts/bench_strategy_backtest.py --start 2025-09-12 --stop 2025-10-12 --repeat 3
  python scripts/bench_strategy_backtest.py --freq 5Min --stop 2026-09-12
"""

from __future__ import annotations

import argparse
import datetime
import statistics
import time
from typing import Any, Callable

import polars as pl

from fast_trade.archive.db_helpers import get_kline
from fast_trade.build_data_frame import prepare_df
from fast_trade.build_summary import build_summary
from fast_trade.run_analysis import apply_logic_to_df
from fast_trade.run_backtest import (
    prepare_new_backtest,
    process_logic_and_generate_actions,
    run_backtest,
)


def basic_strategy(symbol: str, exchange: str, start: str, stop: str, freq: str) -> dict:
    """Simple EMA cross + RSI filter — representative research strategy."""
    return {
        "freq": freq,
        "symbol": symbol,
        "exchange": exchange,
        "start": start,
        "stop": stop,
        "any_enter": [],
        "any_exit": [],
        "datapoints": [
            {"name": "ema_fast", "transformer": "ema", "args": [9]},
            {"name": "ema_slow", "transformer": "ema", "args": [21]},
            {"name": "rsi", "transformer": "rsi", "args": [14]},
        ],
        "enter": [["ema_fast", ">", "ema_slow"], ["rsi", ">", 50]],
        "exit": [["ema_fast", "<", "ema_slow"]],
        "base_balance": 1000.0,
        "exit_on_end": True,
        "comission": 0.001,
        "trailing_stop_loss": 0.0,
        "lot_size": 1.0,
        "max_lot_size": 0,
        "rules": [],
    }


def timed(fn: Callable[[], Any], repeat: int) -> tuple[Any, dict]:
    result = fn()  # warmup
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


def _with_summary_cols(df: pl.DataFrame) -> pl.DataFrame:
    """Mirror apply_backtest_to_df post-pass required by build_summary."""
    return df.with_columns(
        pl.col("adj_account_value").pct_change().alias("adj_account_value_change_perc"),
        pl.col("adj_account_value").diff().alias("adj_account_value_change"),
    )


def bench_stages(backtest: dict, repeat: int) -> dict:
    """Time each stage independently (clone inputs so work is comparable)."""
    raw = get_kline(
        backtest["symbol"],
        backtest["exchange"],
        backtest["start"],
        backtest["stop"],
        freq=backtest["freq"],
    )

    def load():
        return get_kline(
            backtest["symbol"],
            backtest["exchange"],
            backtest["start"],
            backtest["stop"],
            freq=backtest["freq"],
        )

    _, load_stats = timed(load, repeat)

    prepared = prepare_df(raw, backtest)

    def indicators():
        # prepare_df builds a new frame; no need to clone the input each time.
        return prepare_df(raw, backtest)

    _, ind_stats = timed(indicators, repeat)

    with_actions = process_logic_and_generate_actions(prepared, backtest)

    def actions():
        return process_logic_and_generate_actions(prepared, backtest)

    _, action_stats = timed(actions, repeat)

    def simulate():
        return _with_summary_cols(apply_logic_to_df(with_actions, backtest))

    simulated, sim_stats = timed(simulate, repeat)

    started = datetime.datetime.utcnow()

    def summary():
        # build_summary only reads the frame.
        return build_summary(simulated, started)

    _, summary_stats = timed(summary, repeat)

    return {
        "rows": len(with_actions),
        "load_kline": load_stats,
        "prepare_indicators": ind_stats,
        "generate_actions": action_stats,
        "simulate_account": sim_stats,
        "build_summary": summary_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--exchange", default="binanceus")
    parser.add_argument("--start", default="2025-09-12")
    parser.add_argument("--stop", default="2025-11-12")
    parser.add_argument("--freq", default="1Min")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    backtest = prepare_new_backtest(
        basic_strategy(args.symbol, args.exchange, args.start, args.stop, args.freq)
    )

    print(
        f"strategy=ema_cross+rsi  {args.exchange}/{args.symbol}  "
        f"freq={args.freq}  {args.start} → {args.stop}  repeat={args.repeat}"
    )

    result, e2e = timed(lambda: run_backtest(backtest), args.repeat)
    df = result.get("df")
    summary = result.get("summary") or {}
    rows = len(df) if df is not None else 0
    print(f"rows={rows:,}")
    print(f"run_backtest_e2e={e2e}")
    interesting = {
        k: summary[k]
        for k in (
            "return_perc",
            "num_trades",
            "win_perc",
            "sharpe_ratio",
            "max_drawdown",
        )
        if k in summary
    }
    if interesting:
        print(f"summary_sample={interesting}")

    stages = bench_stages(backtest, args.repeat)
    print("stages:")
    for name, stats in stages.items():
        if name == "rows":
            print(f"  rows={stats:,}")
        else:
            print(f"  {name}={stats}")


if __name__ == "__main__":
    main()
