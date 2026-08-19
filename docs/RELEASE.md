# Release Guide

This project is prepared for the `2.1.0` release.

## Scope

`2.1.0` is a minor release. It includes:

- FXMacroData REST client and `build_macro_context` helper
- MCP tool `fxmacrodata_macro_context`
- README notes for API host and env-based auth
- Productized HMM multi-asset screener (`ft screen hmm`, MCP `hmm_screen`, archive-first + optional live adapters)
- Full-package test coverage with correctness-first backtest checks and documented metrics (`docs/METRICS.md`)
- Removal of the interactive `ft terminal` UI (breaking vs 2.0.0); use `ft backtests`, `ft logs --name <NAME>`, and `ft portfolio` instead

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

## Docs To Verify

Confirm these stay in sync:

- `README.md`
- `docs/GETTING_STARTED.md`
- `docs/CONTRIBUTING.md`
- `docs/README.md`
- `docs/CHANGELOG.md`
- `docs/RELEASE.md`
- `pyproject.toml`

Specific things to check:

- version is `2.1.0`
- FXMacroData README section documents host + env vars
- MCP tools cover every `ft` CLI command; verify against `docs/FEATURES.md`
- `ft screen hmm` / `hmm_screen_example.yml` are documented
- changelog includes the `2.1.0` section with terminal removal and test/coverage notes
- no stale references to `ft terminal` or `docs/Terminal.md`

## Release Notes Summary

Use this summary for GitHub or PyPI:

- Added an FXMacroData client and `build_macro_context` helper for pair-level macro/FX context.
- Exposed `fxmacrodata_macro_context` and `hmm_screen` on the MCP server for agent use.
- Productized HMM multi-asset screening via `ft screen hmm` with archive-first loading and optional live fetch.
- Expanded test coverage to 100% line coverage across `fast_trade` with correctness-first backtest regression checks.
- Removed the interactive `ft terminal` UI; browse saved runs with `ft backtests` and tail portfolio logs with `ft logs --name <NAME>`.

## Release Steps

1. Run the pre-release checklist.
2. Review `git diff --stat` and `git status`.
3. Confirm `docs/CHANGELOG.md` and `README.md` reflect the final state.
4. Merge the release-prep PR and checkout `master`.
5. Create the release commit if needed, then tag and push:

```bash
git tag -a v2.1.0 -m "Release 2.1.0"
git push origin v2.1.0
```

6. Create the GitHub release from tag `v2.1.0` (this triggers the PyPI publish workflow).
7. Attach release notes from `docs/CHANGELOG.md` section **2.1.0**.

## Post-Release Checks

After the GitHub release publishes to PyPI:

- install from the published artifact into a clean environment: `pip install fast-trade==2.1.0`
- run `ft --help` and confirm `ft screen hmm --help` is present
- run `ft backtests --help`
- run `ft portfolio --help`
- verify PyPI metadata renders `README.md` correctly
