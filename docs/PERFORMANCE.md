# Performance

`fast-trade` `3.0.0` is Polars-native so you can iterate on strategies without waiting on backtests.

## Headline numbers

Measured on Binance.US `BTCUSDT` 1m archive data (**525,058** bars, `2025-09-12` → `2026-09-12`):

| Workload | Result |
|---|---|
| Full-year EMA-cross + RSI backtest | **~0.62s** end-to-end |
| 2-month 1m backtest (~89k bars) | **~0.17s** end-to-end |
| FinTA indicator suite vs pandas FinTA | **~1.9×** faster |
| ATR(14) | **~5×** faster |
| WMA(20) | **~100×** faster |
| OBV | **~3×** faster |

### Multi-year 1m throughput (EMA-cross + RSI)

Local archive holds ~1y of live 1m bars. Longer windows tile that real series
with date shifts so bar counts match 2y / 5y / 10y calendar lengths (engine
throughput, not live multi-year PnL).

| Horizon | Bars | End-to-end (mean of 3) |
|---|---:|---:|
| 1 year | ~526k | **~0.62s** |
| 2 years | ~1.05M | **~1.14s** |
| 5 years | ~2.63M | **~2.73s** |
| 10 years | ~5.25M | **~5.52s** |

Scaling is roughly linear (~0.55–0.62s per year of 1m bars). Simulation remains
~60–65% of wall time at every horizon.

Reproduce:

```bash
python scripts/bench_strategy_backtest.py --start 2025-09-12 --stop 2026-09-12 --freq 1Min --repeat 3
python scripts/bench_multi_year.py --years 2 5 10 --repeat 3
```

## FinTA indicator table (pandas FinTA snapshot vs Polars)

| Indicator | pandas | Polars | Speedup |
|---|---:|---:|---:|
| SMA(50) | 0.0076s | 0.0041s | **1.83×** |
| EMA(50) | 0.0060s | 0.0036s | **1.67×** |
| RSI(14) | 0.0197s | 0.0164s | **1.20×** |
| ATR(14) | 0.0600s | 0.0118s | **5.08×** |
| MACD | 0.0155s | 0.0095s | **1.64×** |
| BBANDS(20) | 0.0162s | 0.0137s | **1.19×** |
| WMA(20) | 0.5486s | 0.0052s | **105×** |
| STOCH | 0.0176s | 0.0168s | ~1.05× |
| OBV | 0.0296s | 0.0096s | **3.08×** |
| SAR | 0.7663s | 0.7154s | **1.07×** |

**Suite** (SMA+EMA+RSI+ATR+MACD+BBANDS+STOCH+OBV): pandas **0.158s** → Polars **0.082s** (**1.92×**).

## Strategy backtest stages (1 year, 1m)

| Stage | ~time | Share |
|---|---:|---:|
| Account simulation | ~0.34s | ~60% |
| Indicators | ~0.07s | ~12% |
| Summary | ~0.06s | ~10% |
| Load kline | ~0.04s | ~7% |
| Action generation | ~0.02s | ~4% |

## Keeping it fast

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

On ~526k 1m bars (1 year BTCUSDT), a basic EMA-cross+RSI backtest is ~0.62s
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

# 2y / 5y / 10y 1m throughput (tiled from live 1y archive):
python scripts/bench_multi_year.py --years 2 5 10 --repeat 3

# Hotspot profiler
python scripts/profile_backtest_hotspots.py --mode simulation --start 2025-09-12 --stop 2025-11-12
```

Raw multi-year timings: `docs/bench_multi_year_results.json`.
