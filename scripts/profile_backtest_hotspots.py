#!/usr/bin/env python

import argparse
import cProfile
import io
import pstats
import statistics
import time
from collections import deque

from fast_trade.archive.db_helpers import get_kline
from fast_trade.build_data_frame import prepare_df
from fast_trade.run_analysis import apply_logic_to_df
from fast_trade.run_backtest import (
    compile_action_logic,
    determine_action_compiled,
    prepare_new_backtest,
    process_logic_and_generate_actions,
    take_action,
)


def build_backtest(symbol, exchange, start, stop, freq):
    return prepare_new_backtest(
        {
            "freq": freq,
            "symbol": symbol,
            "exchange": exchange,
            "start": start,
            "stop": stop,
            "any_enter": [],
            "any_exit": [],
            "datapoints": [
                {"name": "ema_fast", "transformer": "ema", "args": [9]},
                {"name": "ema_slow", "transformer": "ema", "args": [26]},
                {"name": "rsi", "transformer": "rsi", "args": [14]},
            ],
            "enter": [["ema_fast", ">", "ema_slow"], ["rsi", ">", 55]],
            "exit": [["ema_fast", "<", "ema_slow"], ["rsi", "<", 45]],
            "base_balance": 1000.0,
            "exit_on_end": False,
            "comission": 0.0,
            "trailing_stop_loss": 0.0,
            "lot_size_perc": 1.0,
            "max_lot_size": 0.0,
            "rules": [],
        }
    )


def benchmark(label, fn, repeat):
    timings = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        timings.append(time.perf_counter() - t0)
    print(
        label,
        {
            "mean_s": round(statistics.mean(timings), 4),
            "min_s": round(min(timings), 4),
            "max_s": round(max(timings), 4),
        },
    )
    return result


def profile(label, fn, top_n):
    profiler = cProfile.Profile()
    profiler.enable()
    fn()
    profiler.disable()
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).sort_stats("cumulative").print_stats(top_n)
    print(f"\n=== {label} profile ===")
    print(output.getvalue())


def run_simulation_mode(args):
    backtest = build_backtest(args.symbol, args.exchange, args.start, args.stop, args.freq)
    df = get_kline(args.symbol, args.exchange, args.start, args.stop, freq=args.freq)
    df = prepare_df(df, backtest)
    df = process_logic_and_generate_actions(df, backtest)

    print("rows", len(df))
    print("action_counts", df["action"].value_counts().to_dict())

    benchmark("apply_logic_to_df", lambda: apply_logic_to_df(df.copy(), backtest), args.repeat)
    profile("apply_logic_to_df", lambda: apply_logic_to_df(df.copy(), backtest), args.top_n)


def run_action_mode(args):
    backtest = build_backtest(args.symbol, args.exchange, args.start, args.stop, args.freq)
    backtest["enter"] = [["ema_fast", ">", "ema_slow", 3], ["rsi", ">", 55, 2]]
    backtest["exit"] = [["ema_fast", "<", "ema_slow", 2], ["rsi", "<", 45, 2]]

    df = get_kline(args.symbol, args.exchange, args.start, args.stop, freq=args.freq)
    df = prepare_df(df, backtest)
    frames = list(df.itertuples())
    compiled = compile_action_logic(backtest)
    max_last = 3

    def old_determine(frame, last_frames):
        if backtest.get("trailing_stop_loss") and frame.close <= frame.trailing_stop_loss:
            return "tsl"
        if take_action(frame, backtest.get("exit", []), last_frames):
            return "x"
        if take_action(frame, backtest.get("any_exit", []), last_frames, require_any=True):
            return "ax"
        if take_action(frame, backtest.get("enter", []), last_frames):
            return "e"
        if take_action(frame, backtest.get("any_enter", []), last_frames, require_any=True):
            return "ae"
        return "h"

    def run_old():
        last_frames = []
        out = []
        for frame in frames:
            last_frames.insert(0, frame)
            if len(last_frames) >= max_last + 1:
                last_frames.pop()
            out.append(old_determine(frame, last_frames))
        return out

    def run_new():
        last_frames = deque(maxlen=max_last)
        out = []
        for frame in frames:
            last_frames.appendleft(frame)
            out.append(determine_action_compiled(frame, compiled, last_frames))
        return out

    old_actions = run_old()
    new_actions = run_new()
    print("rows", len(df))
    print("actions_equal", old_actions == new_actions)

    benchmark("action_old", run_old, args.repeat)
    benchmark("action_new", run_new, args.repeat)


def main():
    parser = argparse.ArgumentParser(description="Profile backtest hotspots.")
    parser.add_argument("--mode", choices=["simulation", "action"], default="simulation")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--exchange", default="binanceus")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--stop", default="2024-03-01")
    parser.add_argument("--freq", default="1Min")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=30)
    args = parser.parse_args()

    if args.mode == "simulation":
        run_simulation_mode(args)
    else:
        run_action_mode(args)


if __name__ == "__main__":
    main()
