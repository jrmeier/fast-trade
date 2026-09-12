# Performance Notes

How to keep Polars-native `fast-trade` fast, and where the remaining gaps are.

## FinTA indicators

Prefer native Polars / NumPy vectorized paths. Avoid `Series.rolling_map` Python
UDFs and per-bar Python loops.

| Pattern | Examples | Notes |
|---|---|---|
| `_rolling_mean` / `_ewm_mean` | SMA, EMA, ATR, MACD | Fast path — reuse these |
| Weighted `rolling_mean` / sliding matmul | WMA, HMA | WMA no longer uses `rolling_map` |
| Vectorized NumPy | OBV, RSI helpers | No Python row loops |
| Stateful Python loop | SAR, PSAR | Still ~pandas speed; best next win is Numba/`@njit` |

### Remaining FinTA wins (priority)

1. **SAR / PSAR** — compile the state machine with Numba (optional extra) or a small Rust/Cython helper. Pure Polars cannot express the path-dependent AF logic.
2. **Scan for leftover `rolling_map` / Python `for` loops** in exotic indicators (HMA path is fine via WMA; check IFT_RSI, DYMI, etc. if they show up in profiles).
3. **Keep parity tests** when rewriting — SMA/EMA/RSI already match pandas FinTA within ~1e-10.

## Strategy backtests (1m)

On ~525k 1m bars (1 year BTCUSDT), a basic EMA-cross+RSI backtest is ~0.58s
end-to-end. Stage split:

| Stage | ~share | Notes |
|---|---|---|
| Account simulation (`apply_logic_to_df`) | ~60% | Dominated by Python loop + per-fill `round()` |
| Indicators (`prepare_df`) | ~12% | Already cheap for EMA/RSI |
| Summary | ~10% | |
| Load kline | ~7% | Parquet archive |
| Action generation | ~4% | Compiled path is already fast |

### Remaining backtest wins (priority)

1. **Remove or batch `round(..., 8)`** inside `_simulate_account_path` — large share of sim time. Prefer float math during the loop and round once on output columns.
2. **Numba/JIT the simulation kernel** — already a pure-array loop; good Numba candidate (see `docs/RUN_ANALYSIS_PLAN.md`).
3. **Avoid cloning huge frames** in hot caller loops when benchmarking parameter sweeps; reuse prepared indicator frames.

## Benchmarks

```bash
# FinTA pandas-snapshot vs current Polars (needs /tmp/ft_bench/finta_pandas.py)
# Strategy backtest stages on archive 1m data:
python scripts/bench_strategy_backtest.py --start 2025-09-12 --stop 2026-09-12 --freq 1Min --repeat 3

# Hotspot profiler
python scripts/profile_backtest_hotspots.py --mode simulation --start 2025-09-12 --stop 2025-11-12
```
