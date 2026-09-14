# Performance

`fast-trade` `3.0.0` is Polars-native so you can iterate on strategies without waiting on backtests.

## Headline numbers

Measured on Binance.US `BTCUSDT` 1m archive data (**525,058** bars, `2025-09-12` → `2026-09-12`):

| Workload | Result |
|---|---|
| Full-year EMA-cross + RSI backtest | **~0.43s** end-to-end |
| 2-month 1m backtest (~89k bars) | **~0.17s** end-to-end |
| FinTA indicator suite vs pandas FinTA | **~1.9×** faster |
| ATR(14) | **~5×** faster |
| WMA(20) | **~100×** faster |
| OBV | **~3×** faster |

### Multi-year 1m throughput (EMA-cross + RSI)

Local archive holds ~1y of live 1m bars. Longer windows tile that real series
with date shifts so bar counts match calendar lengths (engine throughput, not
live multi-year PnL).

Same strategy and bars, **pandas `2.1.0` (`origin/master`)** vs **Polars `3.0.0`**
(mean of 3), after Numba sim + FinTA hotpath work:

| Horizon | Bars | pandas 2.1 | Polars 3.0 | Speedup |
|---|---:|---:|---:|---:|
| 1 year | ~526k | 0.81s | **0.41s** | **1.99×** |
| 2 years | ~1.05M | 1.65s | **0.74s** | **2.22×** |
| 5 years | ~2.63M | 4.29s | **1.81s** | **2.37×** |
| 10 years | ~5.25M | 9.75s | **3.99s** | **2.45×** |

Polars stays roughly linear; the gap widens with length now that account
simulation is no longer the dominant shared Python loop. Raw JSON:
`docs/bench_pandas_vs_polars_years.json`.

Reproduce:

```bash
python scripts/bench_strategy_backtest.py --start 2025-09-12 --stop 2026-09-12 --freq 1Min --repeat 3
python scripts/bench_multi_year.py --years 2 5 10 --repeat 3
# needs a master worktree, e.g. git worktree add /tmp/ft_pandas origin/master
python scripts/bench_pandas_vs_polars_years.py --years 1 2 5 10 --repeat 3
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
| SAR | 0.7663s | 0.7154s | **1.07×** (pre-Numba; now Numba-accelerated) |

**Suite** (SMA+EMA+RSI+ATR+MACD+BBANDS+STOCH+OBV): pandas **0.158s** → Polars **0.082s** (**1.92×**).

## Strategy backtest stages (1 year, 1m)

Post-optimization (mean of 3):

| Stage | ~time | Share |
|---|---:|---:|
| Indicators | ~0.07s | ~17% |
| Summary | ~0.06s | ~13% |
| Load kline | ~0.04s | ~10% |
| Account simulation | ~0.04s | ~10% |
| Action generation | ~0.02s | ~5% |

End-to-end mean **~0.43s** (overhead from frame assembly / validation fills the rest).

## Keeping it fast

Prefer native Polars / NumPy vectorized paths. Avoid `Series.rolling_map` Python
UDFs and per-bar Python loops. Hot stateful paths use Numba (`fast_trade/_accel.py`
+ the simulation kernel in `run_analysis.py`).

| Pattern | Examples | Notes |
|---|---|---|
| `_rolling_mean` / `_ewm_mean` | SMA, EMA, ATR, MACD | Fast path — reuse these |
| Weighted `rolling_mean` / sliding matmul | WMA, HMA | WMA no longer uses `rolling_map` |
| Vectorized NumPy | OBV, RSI, CCI MAD, FVE, LINEAR_REGRESSION | No Python row loops |
| Numba `@njit` | Account sim, SAR, PSAR, KAMA, FRAMA | Required dependency (`numba>=0.60`) |
| Centered Polars rolling | WILLIAMS_FRACTAL | Uses `rolling_max` / `rolling_min` |

### Done (hotpath pass)

1. **Simulation** — float math in-loop; `np.round(..., 8)` once on outputs; Numba kernel with Python fallback (progress callbacks force fallback).
2. **FinTA stateful** — SAR / PSAR / KAMA / FRAMA via Numba kernels in `_accel.py`.
3. **Leftover `rolling_map` / Python loops** — CCI, FVE, WILLIAMS_FRACTAL, LINEAR_REGRESSION vectorized.
4. **Bench scripts** — dropped needless huge-frame `.clone()` in timing loops.

### Remaining FinTA / backtest wins

1. Re-measure SAR/PSAR vs pandas FinTA after Numba (table above still shows pre-Numba SAR).
2. Profile summary / trade-log builders next — they are now competitive with sim.
3. Keep parity tests when rewriting — SMA/EMA/RSI already match pandas FinTA within ~1e-10.

## Benchmarks

```bash
# FinTA pandas-snapshot vs current Polars (needs /tmp/ft_bench/finta_pandas.py)
# Strategy backtest stages on archive 1m data:
python scripts/bench_strategy_backtest.py --start 2025-09-12 --stop 2026-09-12 --freq 1Min --repeat 3

# 2y / 5y / 10y 1m throughput (tiled from live 1y archive):
python scripts/bench_multi_year.py --years 2 5 10 --repeat 3

# pandas 2.1.0 (origin/master worktree) vs Polars 3.0.0:
# git worktree add /tmp/ft_pandas origin/master
python scripts/bench_pandas_vs_polars_years.py --years 1 2 5 10 --repeat 3

# Hotspot profiler
python scripts/profile_backtest_hotspots.py --mode simulation --start 2025-09-12 --stop 2025-11-12
```

Raw timings: `docs/bench_multi_year_results.json`, `docs/bench_pandas_vs_polars_years.json`.
