# Action Engine Optimization Plan

This file tracks the optimization work for `determine_action` / `take_action` and related hot-path logic.

## Goals

- reduce Python overhead in action generation
- preserve existing strategy semantics and public API behavior
- keep the code covered by tests and measured with profiling

## Baseline

Initial profiling on representative local backtests showed:

- `run_backtest` time is split across archive loading, dataframe prep, and action/simulation logic
- `determine_action` / `take_action` are still called per row in non-vectorized paths
- repeated row conversion and temporary list allocation appear in the current hot path

## Work Items

- [x] Create a tracked optimization plan
- [x] Remove avoidable allocations and repeated row conversions in the action engine
- [x] Preserve behavior with targeted and full test coverage
- [x] Re-profile the action path and record results here
- [x] Decide whether a second pass should introduce compiled logic or a ring buffer

## Current Pass Scope

First pass is intentionally conservative:

- remove mutable default arguments
- stop converting row tuples to dicts for every field lookup
- short-circuit `all` / `any` logic evaluation instead of building result lists
- avoid slicing temporary `last_frames` lists when evaluating lookback logic

## Progress Log

- `2026-03-11`: Plan created. First implementation pass in progress.
- `2026-03-11`: Reworked `determine_action` / `take_action` hot path to remove mutable defaults, avoid repeated row dict conversion, short-circuit logic evaluation, and avoid slicing `last_frames` for lookback rules.
- `2026-03-11`: Targeted benchmark on a `1Min` BTCUSDT backtest (`2024-01-01` to `2024-03-01`) improved from roughly `2.68s` mean to `1.94s` mean, about a `27%` reduction in wall time.
- `2026-03-11`: Second pass implemented. Backtest action generation now compiles rule groups once and uses a fixed-size `deque` ring buffer for lookback evaluation. Live and portfolio action evaluation now use the same compiled path.
- `2026-03-11`: Lookback-heavy benchmark on prepared `1Min` BTCUSDT data (`2024-01-01` to `2024-01-15`) produced identical actions while reducing action-generation time from roughly `0.78s` mean to `0.24s` mean, about a `3.2x` speedup for the targeted path.
- `2026-03-11`: Validation complete. Targeted `test/test_run_backtest.py` passed, full `python -m pytest` passed (`136 passed`), and `flake8` passed.
