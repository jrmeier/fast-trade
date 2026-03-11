# Run Analysis Optimization Plan

This file tracks the next optimization pass for `fast_trade/run_analysis.py`, centered on `apply_logic_to_df()`.

## Baseline Profile

Profile run on:

- symbol: `BTCUSDT`
- exchange: `binanceus`
- freq: `1Min`
- range: `2024-01-01` to `2024-03-01`
- prepared rows: `87840`
- action counts: `{'h': 33445, 'e': 28801, 'x': 25594}`

Observed timing:

- `apply_logic_to_df()` mean wall time: about `0.48s`

Primary hotspots from `cProfile`:

- `convert_aux_to_base()` cumulative time: about `0.27s`
- built-in `round()` time: about `0.25s`
- `convert_base_to_aux()` is much smaller
- pandas column assignment cost is minor relative to the loop itself

## Interpretation

This is now mostly a Python math loop problem, not a pandas problem.

The current simulation loop spends most of its time on:

- repeated conversion helpers inside the inner loop
- repeated rounding inside those helpers
- string action checks in the loop
- reading previous values from arrays instead of keeping local rolling state

## Remediation Path

### Phase 1: Low-risk loop tightening

- inline `convert_base_to_aux`, `convert_aux_to_base`, and fee math in the main loop
- defer rounding until output assignment instead of rounding inside every conversion
- map actions to compact integer codes once before the loop
- keep `in_trade`, `account_value`, and `aux` as local rolling scalars, then write arrays

Expected impact:

- should reduce Python call overhead and the `round()` hotspot materially
- should preserve behavior with small numerical drift risk if rounding is deferred

### Phase 2: Specialized simulation kernel

- split simulation into a dedicated pure-array kernel
- optionally JIT it with Numba if dependency policy allows
- keep the public `apply_logic_to_df()` wrapper stable

Expected impact:

- highest likely gain on long backtests
- larger implementation and verification cost

## Guardrails

- preserve existing tests in `test/test_run_analysis.py`
- compare summary outputs before and after on representative backtests
- treat rounding behavior as user-visible and verify carefully

## Tooling

Use `scripts/profile_backtest_hotspots.py` to rerun comparable hotspot profiles.

## Progress Log

- `2026-03-11`: Initial profile recorded. No code changes applied yet for `run_analysis.py`.
- `2026-03-11`: First implementation pass completed in `apply_logic_to_df()`. The loop now uses local rolling state, precomputed enter/exit masks, inline transaction math, and a vectorized post-pass for `adj_account_value`.
- `2026-03-11`: `test/test_run_analysis.py` passed after the refactor.
- `2026-03-11`: Representative simulation benchmark improved from about `0.48s` mean to about `0.18s` mean on the `1Min` BTCUSDT case, roughly a `2.7x` speedup for `apply_logic_to_df()`.
- `2026-03-11`: Phase 2 implemented. The simulation loop is now extracted into a dedicated pure-array kernel inside `run_analysis.py`, and `apply_logic_to_df()` acts as the stable pandas wrapper.
- `2026-03-11`: After extraction, the representative simulation benchmark measured about `0.21s` mean. This is slightly slower than the fully inlined version, but still materially better than the original `0.48s` baseline while leaving the code in a cleaner state for a future JIT pass.
- `2026-03-11`: Full verification completed after Phase 2: `python -m pytest` passed (`137 passed`) and `flake8` passed.
