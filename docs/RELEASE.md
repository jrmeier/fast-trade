# Release Guide

This project is currently prepared for the `2.1.0` release.

## Scope

`2.1.0` is a minor release. It includes:

- FXMacroData REST client and `build_macro_context` helper
- MCP tool `fxmacrodata_macro_context`
- README notes for API host and env-based auth
- Productized HMM screener (`ft screen hmm`, MCP `hmm_screen`, archive-first + optional live adapters)

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

- version is `2.1.0`
- FXMacroData README section documents host + env vars
- MCP tools `fxmacrodata_macro_context` and `hmm_screen` are mentioned
- `ft screen hmm` / `hmm_screen_example.yml` are documented
- changelog includes the `2.1.0` section

## Release Notes Summary

Use this summary for GitHub or PyPI:

- Added an FXMacroData client and `build_macro_context` helper for pair-level macro/FX context.
- Exposed `fxmacrodata_macro_context` on the MCP server for agent use.
- Documented API host and `FXMACRODATA_API_KEY` / `FXMD_API_KEY` auth in the README.

## Release Steps

1. Run the pre-release checklist.
2. Review `git diff --stat` and `git status`.
3. Confirm `docs/CHANGELOG.md` and `README.md` reflect the final state.
4. Create the release commit and push it.
5. Tag the release as `v2.1.0`.
6. Publish the package and attach release notes.

## Post-Release Checks

- install from the published artifact into a clean environment
- run `ft --help`
- run `ft terminal --help`
- run `ft portfolio --help`
- verify PyPI metadata renders `README.md` correctly
