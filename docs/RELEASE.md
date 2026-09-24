# Release Guide

This project is prepared for the `3.0.0` release.

## Scope

`3.0.0` is a **major** release. It includes:

- Polars-native dataframes across the library (FinTA, archive, backtest, summary, CLI, ML)
- Removal of the pandas dependency
- Python 3.11 minimum; supported and tested on Python 3.11–3.13
- Explicit `date` column instead of a DatetimeIndex
- Multiprocessing spawn pools for parallel/chunked backtests
- Headline speed: ~0.43s for a 1-year BTCUSDT 1m strategy backtest (~2× vs pandas 2.1); FinTA suite ~1.9× vs pandas (see `docs/PERFORMANCE.md`)
- Prior `2.1.0` work (FXMacroData, HMM screener, MCP coverage, terminal UI removal) remains in tree

## Pre-Release Checklist

Run these from the repo root with Python 3.11–3.13. Python 3.14 is experimental because `hmmlearn` requires a source build; do not declare support until installation and the full tests pass.

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
python examples/ml_classifier_backtest.py --synthetic
python examples/ml_classifier_backtest.py --synthetic --signal-threshold 0.55
python -m fast_trade.mcp_server
python -m build
python -m twine check --strict dist/*
```

Notes:

- `python -m fast_trade.mcp_server` is a smoke check for import and startup. Do not leave it running during the release pass.
- `coverage report` must satisfy `.coveragerc` `fail_under = 100`.
- Build and metadata checks use the `dev` extra (includes `build`, `twine`, `pytest`, `coverage`, `flake8`).
- Confirm `rg "import pandas|from pandas" fast_trade` is empty.
- Confirm the required **Python application** jobs pass: tests and coverage on Python 3.11, 3.12, and 3.13; lint, package build, `twine check`, and installed-wheel smoke checks on Python 3.13 in a fresh environment without pandas. The Python 3.14 test job is experimental and does not gate publishing.

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
- Python minimum is 3.11 in package metadata, setup docs, and badges; supported/tested versions are 3.11–3.13
- description/keywords say Polars (not pandas)
- changelog includes the `3.0.0` breaking-change section
- README / GETTING_STARTED describe Polars frames + `date` column
- FinTA docs say Polars-only input/output
- no stale “pandas DataFrame” claims for `run_backtest` results

## Release Notes Summary

Use this summary for GitHub or PyPI:

- Migrated the library from pandas to Polars-native dataframes.
- Removed pandas from package dependencies.
- Raised the minimum Python version to 3.11; Python 3.11–3.13 are supported and tested.
- Completed the Polars migration for classifier features, signals, and the `column` transformer.
- OHLC data uses an explicit `date` column; strategy YAML inputs are unchanged.
- Fixed parallel/chunked backtests to use spawn pools under Polars.
- **Speed:** ~0.43s for a 1-year BTCUSDT 1m EMA-cross+RSI backtest; FinTA suite ~1.9× vs pandas (ATR ~5×, WMA ~100×, OBV ~3×).

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

6. Create and publish the GitHub release from the existing tag, with release notes from `docs/CHANGELOG.md` section **3.0.0**:

```bash
gh release create v3.0.0 --verify-tag --title "3.0.0"
```

The published release event triggers the PyPI publish workflow. A tag push or draft release alone does not publish to PyPI. The publish workflow first calls the reusable **Python application** workflow for required tests, lint, build, metadata validation with `twine check`, and installed-wheel smoke checks. PyPI receives the artifact produced by that validated build only after all required checks pass.

## Post-Release Checks

- Confirm the GitHub Actions validation and publish jobs succeeded for the release tag.
- Confirm `pip install fast-trade==3.0.0` resolves and imports without pandas.
- Spot-check `ft --help`, `ft backtest`, and `from fast_trade import run_backtest`.
