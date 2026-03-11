# Release Guide

This project is currently prepared for the `2.0.0` release.

## Scope

`2.0.0` is a major release. It includes:

- terminal and CLI workflow expansion
- live and stream runners with persistent JSONL logging
- paper portfolio runner with daemon support
- MCP server support
- ML tooling and examples
- internal modularization of summary, CLI, and backtest logic

## Pre-Release Checklist

Run these from the repo root:

```bash
source venv/bin/activate
python -m pytest
flake8
python -m fast_trade.cli --help
python -m fast_trade.cli terminal --help
python -m fast_trade.cli portfolio --help
python -m fast_trade.cli logs --help
python -m fast_trade.mcp_server
```

Notes:

- `python -m fast_trade.mcp_server` is a smoke check for import and startup. Do not leave it running during the release pass.
- If you want a packaging check, also run:

```bash
python -m build
```

## Docs To Verify

Confirm these stay in sync:

- `README.md`
- `docs/Terminal.md`
- `docs/CHANGELOG.md`
- `pyproject.toml`

Specific things to check:

- version is `2.0.0`
- terminal commands match actual CLI behavior
- log paths use `.jsonl`
- YAML examples are referenced instead of removed JSON examples

## Release Notes Summary

Use this summary for GitHub or PyPI:

- Expanded `ft terminal` into a full operational interface for backtests, live signals, streams, and logs.
- Added a daemonized paper portfolio runner with persisted state, trade history, and logs.
- Added MCP server support so external agents can use the CLI and portfolio/log workflows.
- Refactored core logic into smaller modules to reduce redundancy and improve maintainability.
- Standardized examples and workflows around YAML configs and archive-backed parquet data.

## Release Steps

1. Run the pre-release checklist.
2. Review `git diff --stat` and `git status`.
3. Confirm `docs/CHANGELOG.md` and `README.md` reflect the final state.
4. Create the release commit and push it.
5. Tag the release as `v2.0.0`.
6. Publish the package and attach release notes.

## Post-Release Checks

- install from the published artifact into a clean environment
- run `ft --help`
- run `ft terminal --help`
- run `ft portfolio --help`
- verify PyPI metadata renders `README.md` correctly
