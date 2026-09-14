# Documentation

Project documentation lives in this directory.

Library dataframes are Polars (`pl.DataFrame` with a `date` column) as of `3.0.0`. Headline speed: ~0.58s for a full-year 1m backtest — see `PERFORMANCE.md`.

## Core Docs

- `GETTING_STARTED.md` — install, first run, and common CLI workflows
- `PERFORMANCE.md` — speed headlines, FinTA table, strategy stage breakdown
- `ROADMAP.md` — strategic direction and near/medium/long-term priorities
- `CHANGELOG.md` — release history and migration notes
- `RELEASE.md` — release checklist and publish steps
- `CONTRIBUTING.md` — local dev setup and PR expectations
- `METRICS.md` — backtest summary metric definitions
- `FEATURES.md` — CLI ↔ MCP feature matrix

## Reference Docs

- `FINTA_README.md` — Polars-native FinTA indicator fork
- `TRANSFORMER_README.md`
