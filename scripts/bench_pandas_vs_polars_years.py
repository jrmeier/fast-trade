#!/usr/bin/env python
"""Compare pandas-era (2.1.0 / master) vs Polars-native (3.0.0) strategy throughput.

Builds the same tiled 1m BTCUSDT windows used by ``bench_multi_year.py``, then
times ``run_backtest`` in two isolated processes:

* Polars: current checkout
* pandas: ``/tmp/ft_pandas`` worktree of ``origin/master`` (2.1.0)

Examples:
  python scripts/bench_pandas_vs_polars_years.py
  python scripts/bench_pandas_vs_polars_years.py --years 1 2 5 10 --repeat 3
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "ft_archive" / "binanceus" / "BTCUSDT.parquet"
DEFAULT_STOP = dt.datetime(2026, 9, 12)
PANDAS_ROOT = Path("/tmp/ft_pandas")


def build_tiled(src: pl.DataFrame, years: int, stop: dt.datetime) -> pl.DataFrame:
    start = stop - dt.timedelta(days=365 * years)
    pieces = []
    for i in range(years):
        shift = years - 1 - i
        pieces.append(
            src.with_columns(
                (pl.col("date") - pl.duration(days=365 * shift)).alias("date")
            )
        )
    return (
        pl.concat(pieces)
        .unique(subset=["date"], keep="last")
        .sort("date")
        .filter((pl.col("date") >= start) & (pl.col("date") <= stop))
    )


WORKER = textwrap.dedent(
    r"""
    import json, statistics, sys, time
    from pathlib import Path

    mode = sys.argv[1]
    parquet = Path(sys.argv[2])
    start, stop, freq = sys.argv[3], sys.argv[4], sys.argv[5]
    repeat = int(sys.argv[6])

    strategy = {
        "freq": freq,
        "symbol": "BTCUSDT",
        "exchange": "binanceus",
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

    if mode == "polars":
        import polars as pl
        from fast_trade.run_backtest import prepare_new_backtest, run_backtest
        df = pl.read_parquet(parquet)
        backtest = prepare_new_backtest(strategy)

        def once():
            return run_backtest(backtest, df.clone())
    else:
        import pandas as pd
        from fast_trade.run_backtest import prepare_new_backtest, run_backtest
        raw = pd.read_parquet(parquet)
        if "date" in raw.columns:
            raw["date"] = pd.to_datetime(raw["date"])
            raw = raw.set_index("date")
        raw = raw.sort_index()
        backtest = prepare_new_backtest(strategy)

        def once():
            return run_backtest(backtest, raw.copy())

    once()  # warmup
    times = []
    result = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = once()
        times.append(time.perf_counter() - t0)

    summary = (result or {}).get("summary") or {}
    out_df = (result or {}).get("df")
    rows = len(out_df) if out_df is not None else 0
    print(json.dumps({
        "mode": mode,
        "rows": rows,
        "mean_s": round(statistics.mean(times), 4),
        "min_s": round(min(times), 4),
        "max_s": round(max(times), 4),
        "repeat": repeat,
        "num_trades": summary.get("num_trades") or summary.get("trade_count"),
    }))
    """
)


def run_worker(
    mode: str,
    parquet: Path,
    start: str,
    stop: str,
    freq: str,
    repeat: int,
    package_root: Path,
) -> dict:
    env_python = sys.executable
    cmd = [
        env_python,
        "-c",
        WORKER,
        mode,
        str(parquet),
        start,
        stop,
        freq,
        str(repeat),
    ]
    env = dict(**{k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"})
    env["PYTHONPATH"] = str(package_root)
    cwd = str(package_root)

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{mode} worker failed ({proc.returncode}):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    # last line is JSON
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return json.loads(lines[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--years", type=int, nargs="+", default=[1, 2, 5, 10])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--freq", default="1Min")
    parser.add_argument("--stop", default=DEFAULT_STOP.date().isoformat())
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "bench_pandas_vs_polars_years.json",
    )
    parser.add_argument("--pandas-root", type=Path, default=PANDAS_ROOT)
    args = parser.parse_args()

    pandas_root = args.pandas_root
    if not pandas_root.exists():
        raise SystemExit(
            f"pandas worktree missing at {pandas_root}. "
            "Run: git worktree add /tmp/ft_pandas origin/master"
        )

    src = pl.read_parquet(args.src).sort("date")
    stop = dt.datetime.fromisoformat(args.stop)
    print(f"source rows={src.height:,}  {src['date'].min()} → {src['date'].max()}")
    print(f"pandas root={pandas_root}")

    rows = []
    with tempfile.TemporaryDirectory(prefix="ft_year_bench_") as tmp:
        tmp_path = Path(tmp)
        for years in args.years:
            tiled = build_tiled(src, years, stop)
            start = (stop - dt.timedelta(days=365 * years)).date().isoformat()
            stop_s = stop.date().isoformat()
            parquet = tmp_path / f"btcusdt_{years}y.parquet"
            tiled.write_parquet(parquet)
            print(f"\n=== {years}y  {start} → {stop_s}  bars={tiled.height:,} ===")

            polars = run_worker(
                "polars", parquet, start, stop_s, args.freq, args.repeat, ROOT
            )
            print(f"  polars: {polars['mean_s']:.4f}s  rows={polars['rows']:,}")
            pandas = run_worker(
                "pandas", parquet, start, stop_s, args.freq, args.repeat, pandas_root
            )
            print(f"  pandas: {pandas['mean_s']:.4f}s  rows={pandas['rows']:,}")
            speedup = (
                round(pandas["mean_s"] / polars["mean_s"], 2) if polars["mean_s"] else None
            )
            print(f"  speedup: {speedup}× (pandas/polars)")
            rows.append(
                {
                    "years": years,
                    "start": start,
                    "stop": stop_s,
                    "bars": tiled.height,
                    "polars": polars,
                    "pandas": pandas,
                    "speedup_x": speedup,
                    "data_note": (
                        "1m BTCUSDT tiled from live 1y archive; "
                        "pandas = origin/master 2.1.0, polars = current 3.0.0"
                    ),
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {args.out}")
    print("\n| Horizon | Bars | pandas | Polars | Speedup |")
    print("|---|---:|---:|---:|---:|")
    for r in rows:
        print(
            f"| {r['years']}y | {r['bars']:,} | {r['pandas']['mean_s']:.2f}s | "
            f"{r['polars']['mean_s']:.2f}s | **{r['speedup_x']}×** |"
        )


if __name__ == "__main__":
    main()
