# Release Guide

This project is prepared for the `3.0.0` release.

## Scope

`3.0.0` is a **major** release. It includes:

- Polars-native dataframes across the library (FinTA, archive, backtest, summary, CLI, ML)
- Removal of the pandas dependency
- Explicit `date` column instead of a DatetimeIndex
- Multiprocessing spawn pools for parallel/chunked backtests
- Headline speed: ~0.58s for a 1-year BTCUSDT 1m strategy backtest; FinTA suite ~1.9× vs pandas (see `docs/PERFORMANCE.md`)
- Prior `2.1.0` work (FXMacroData, HMM screener, MCP coverage, terminal UI removal) remains in tree

## Pre-Release Checklist

Run these from the repo root:

```bash
source venv/bin/activate
pip install -e ".[dev]"
python -m pytest
flake8
coverage run -m pytest && coverage report -m
python -m fast_trade.cli --help
python -m fast_trade.cli backtests --help
python -m fast_trade.cli portfolio --help
python -m fast_trade.cli logs --help
python -m fast_trade.cli screen --help
python -m fast_trade.mcp_server
python -m build
```

Notes:

- `python -m fast_trade.mcp_server` is a smoke check for import and startup. Do not leave it running during the release pass.
- `coverage report` must satisfy `.coveragerc` `fail_under = 100`.
- `python -m build` requires the `dev` extra (includes `build`, `pytest`, `coverage`, `flake8`).
- Confirm `rg "import pandas|from pandas" fast_trade` is empty.

## Docs To Verify

Confirm these stay in sync:

- `README.md`
- `docs/GETTING_STARTED.md`
- `docs/CONTRIBUTING.md`
- `docs/README.md`
- `docs/CHANGELOG.md`
- `docs/RELEASE.md`
- `docs/FEATURES.md`
- `docs/FINTA_README.md`
- `AGENTS.md`
- `pyproject.toml`

Specific things to check:

- version is `3.0.0`
- description/keywords say Polars (not pandas)
- changelog includes the `3.0.0` breaking-change section
- README / GETTING_STARTED describe Polars frames + `date` column
- FinTA docs say Polars-only input/output
- no stale “pandas DataFrame” claims for `run_backtest` results

## Release Notes Summary

Use this summary for GitHub or PyPI:

- Migrated the library from pandas to Polars-native dataframes.
- Removed pandas from package dependencies.
- OHLC data uses an explicit `date` column; strategy YAML inputs are unchanged.
- Fixed parallel/chunked backtests to use spawn pools under Polars.
- **Speed:** ~0.58s for a 1-year BTCUSDT 1m EMA-cross+RSI backtest; FinTA suite ~1.9× vs pandas (ATR ~5×, WMA ~100×, OBV ~3×).

## Release Steps

1. Run the pre-release checklist.
2. Review `git diff --stat` and `git status`.
3. Confirm `docs/CHANGELOG.md` and `README.md` reflect the final state.
4. Merge the release-prep PR and checkout `master`.
5. Create the release commit if needed, then tag and push:

```bash
git tag -a v3.0.0 -m "Release 3.0.0"
git push origin v3.0.0
```

6. Create the GitHub release from tag `v3.0.0` (this triggers the PyPI publish workflow).
7. Attach release notes from `docs/CHANGELOG.md` section **3.0.0**.

## Post-Release Checks

- Confirm the GitHub Actions publish workflow succeeded.
- Confirm `pip install fast-trade==3.0.0` resolves and imports without pandas.
- Spot-check `ft --help`, `ft backtest`, and `from fast_trade import run_backtest`.
