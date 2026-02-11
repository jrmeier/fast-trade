# Repository Guidelines

## Project Structure & Module Organization
- fast_trade/: core library (backtesting engine, indicators, CLI)
  - run_backtest.py, build_data_frame.py, build_summary.py, finta.py
  - cli.py (entrypoint `ft`), archive/ (data download/update helpers)
- test/: pytest suite (`test_*.py`)
- saved_backtests/: optional output when using `ft backtest --save`
- example_backtest.json, strategy.json: reference strategies
- pyproject.toml: packaging, deps, and console script

## Build, Test, and Development Commands
- Setup (editable): `python -m venv .venv && source .venv/bin/activate && pip install -e .`
- Run tests: `pytest` (or `python -m pytest`)
- Coverage: `coverage run -m pytest && coverage report -m`
- Lint: `flake8` (configured via `.flake8`, max line length 122)
- CLI help: `ft -h`
- Quick run: `ft backtest ./strategy.json [--save] [--plot]`
- Download data: `ft download BTCUSDT binanceus --start 2024-12-01 --end 2025-01-01`

## Coding Style & Naming Conventions
- Python 3.8+; 4‑space indentation; prefer type hints where practical.
- Use snake_case for modules/functions/variables; CapWords for classes.
- Keep functions small and fast; avoid unnecessary allocations in hot paths.
- Lint with `flake8` (line length 122; excludes build/dist/test per `.flake8`).
- Public API lives under `fast_trade/`; avoid breaking changes without discussion.

## Testing Guidelines
- Framework: `pytest`; place unit tests in `test/` as `test_*.py`.
- Aim for focused, deterministic tests (no network calls). Use small CSV/fixtures.
- Cover new logic in `run_backtest.py`, `build_summary.py`, and helpers.
- Validate strategies with `validate_backtest` where relevant.
- Measure coverage with `coverage`; source is configured to `./fast_trade` in `.coveragerc`.

## Commit & Pull Request Guidelines
- Commits: short, imperative summaries (e.g., "fix archive update"); keep changes scoped.
- Reference issues (e.g., `#123`) when applicable; include rationale in the body.
- PRs must include: clear description, before/after behavior, test coverage, and docs/README updates when user‑facing.
- Ensure `pytest`, `flake8`, and coverage run clean locally before requesting review.

## Security & Configuration Tips
- Do not commit real secrets; use a local `.env` only for development. No API keys are required for archive downloads.
- Archive path defaults to `./archive` when using the CLI; prefer this in examples.
