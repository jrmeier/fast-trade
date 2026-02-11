#!/usr/bin/env python
# Example script demonstrating how to use the parallel backtest functionality

import datetime
import time
import pandas as pd
from fast_trade import prepare_df
from fast_trade.archive.db_helpers import get_kline
from fast_trade.run_backtest import (
    run_backtest,
    run_backtests_parallel,
    run_backtest_chunked,
)

# Define a base strategy
base_strategy = {
    "freq": "5Min",
    "any_enter": [],
    "any_exit": [],
    "enter": [
        ["rsi", "<", 30],
        ["bbands_bbands_bb_lower", ">", "close"],
    ],
    "exit": [
        ["rsi", ">", 70],
        ["bbands_bbands_bb_upper", "<", "close"],
    ],
    "datapoints": [
        {"name": "ema", "transformer": "ema", "args": [5]},
        {"name": "sma", "transformer": "sma", "args": [20]},
        {"name": "rsi", "transformer": "rsi", "args": [14]},
        {"name": "obv", "transformer": "obv", "args": []},
        {"name": "bbands", "transformer": "bbands", "args": [20, 2]},
    ],
    "base_balance": 1000.0,
    "exit_on_end": False,
    "comission": 0.0,
    "trailing_stop_loss": 0.0,
    "lot_size_perc": 1.0,
    "max_lot_size": 0.0,
    "start_date": datetime.datetime(2024, 1, 1, 0, 0),
    "end_date": datetime.datetime(2024, 2, 1, 0, 0),
    "rules": None,
    "symbol": "BTC-USDT",
    "exchange": "coinbase",
}


def create_strategy_variations():
    """Create multiple variations of the strategy for parallel testing"""
    strategies = []

    # Vary RSI parameters
    for rsi_period in [7, 14, 21]:
        for rsi_lower in [20, 25, 30]:
            for rsi_upper in [70, 75, 80]:
                strategy = base_strategy.copy()

                # Update datapoints
                strategy["datapoints"] = base_strategy["datapoints"].copy()
                for i, dp in enumerate(strategy["datapoints"]):
                    if dp["name"] == "rsi":
                        strategy["datapoints"][i] = {
                            "name": "rsi",
                            "transformer": "rsi",
                            "args": [rsi_period],
                        }

                # Update enter/exit conditions
                strategy["enter"] = [
                    ["rsi", "<", rsi_lower],
                    ["bbands_bbands_bb_lower", ">", "close"],
                ]
                strategy["exit"] = [
                    ["rsi", ">", rsi_upper],
                    ["bbands_bbands_bb_upper", "<", "close"],
                ]

                # Add to list
                strategies.append(strategy)

    return strategies


def run_single_backtest_example():
    """Run a single backtest using the standard method"""
    print("Running single backtest...")
    start_time = time.time()

    # Get data
    df = get_kline(
        "BTCUSDT", "binanceus", start_date="2024-01-01", end_date="2024-02-01"
    )

    # Run backtest
    result = run_backtest(base_strategy, df)

    end_time = time.time()
    print(f"Single backtest completed in {end_time - start_time:.2f} seconds")
    print(f"Return: {result['summary']['return_perc']:.2f}%")

    return result


def run_chunked_backtest_example():
    """Run a single backtest using the chunked method for parallel processing"""
    print("\nRunning chunked backtest...")
    start_time = time.time()

    # Get data
    df = get_kline(
        "BTCUSDT", "binanceus", start_date="2024-01-01", end_date="2024-02-01"
    )

    # Run backtest with chunking
    result = run_backtest_chunked(base_strategy, df, chunk_size=1000)

    end_time = time.time()
    print(f"Chunked backtest completed in {end_time - start_time:.2f} seconds")
    print(f"Return: {result['summary']['return_perc']:.2f}%")

    return result


def run_multiple_backtests_example():
    """Run multiple backtests in parallel"""
    print("\nRunning multiple backtests in parallel...")
    start_time = time.time()

    # Create strategy variations
    strategies = create_strategy_variations()
    print(f"Testing {len(strategies)} strategy variations")

    # Get data (shared across all backtests)
    df = get_kline(
        "BTCUSDT", "binanceus", start_date="2024-01-01", end_date="2024-02-01"
    )

    # Run backtests in parallel
    results = run_backtests_parallel(strategies, df)

    end_time = time.time()
    print(f"Parallel backtests completed in {end_time - start_time:.2f} seconds")

    # Find best strategy
    best_return = -float("inf")
    best_strategy_idx = -1

    for i, result in enumerate(results):
        return_perc = result["summary"]["return_perc"]
        if return_perc > best_return:
            best_return = return_perc
            best_strategy_idx = i

    if best_strategy_idx >= 0:
        best_strategy = strategies[best_strategy_idx]
        print(f"Best strategy return: {best_return:.2f}%")
        print(
            f"Best RSI period: {[dp['args'][0] for dp in best_strategy['datapoints'] if dp['name'] == 'rsi'][0]}"
        )
        print(f"Best RSI lower threshold: {best_strategy['enter'][0][2]}")
        print(f"Best RSI upper threshold: {best_strategy['exit'][0][2]}")

    return results


def compare_performance():
    """Compare performance between different methods"""
    print("\nComparing performance between methods...")

    # Get data
    df = get_kline(
        "BTCUSDT", "binanceus", start_date="2024-01-01", end_date="2024-02-01"
    )

    # Prepare data once to make comparison fair
    prepared_df = prepare_df(df, base_strategy)

    # Time standard method
    start_time = time.time()
    run_backtest(base_strategy, prepared_df.copy())
    standard_time = time.time() - start_time
    print(f"Standard method: {standard_time:.2f} seconds")

    # Time chunked method
    start_time = time.time()
    run_backtest_chunked(base_strategy, prepared_df.copy())
    chunked_time = time.time() - start_time
    print(f"Chunked method: {chunked_time:.2f} seconds")

    # Calculate speedup
    speedup = standard_time / chunked_time if chunked_time > 0 else float("inf")
    print(f"Speedup: {speedup:.2f}x")


if __name__ == "__main__":
    # Run examples
    run_single_backtest_example()
    run_chunked_backtest_example()
    run_multiple_backtests_example()
    compare_performance()
