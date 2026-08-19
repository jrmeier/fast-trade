# Changelog

## Unreleased

## 2.1.0

### Release Highlights
- FXMacroData integration for macro/FX context from catalogues, calendars, announcements, and forex data.
- New MCP tool `fxmacrodata_macro_context` for agent workflows.
- Productized HMM multi-asset screener (`ft screen hmm`) with archive-first loading and optional live Coinbase/Hyperliquid fetch.
- Full-package test coverage with correctness-first backtest checks and documented metric formulas (`docs/METRICS.md`).
- Removed the interactive `ft terminal` UI and related live/stream TTY helpers; use `ft backtests` / `ft logs --name <NAME>` / `ft portfolio` instead.

### New Features
- Added `fast_trade.fxmacrodata.FXMacroDataClient` and `build_macro_context(...)`.
- Public exports: `FXMacroDataClient`, `build_macro_context`.
- MCP server tool: `fxmacrodata_macro_context(base, quote="usd", indicator="policy_rate", limit=10)`.
- Auth via `FXMACRODATA_API_KEY` / `FXMD_API_KEY`, constructor `api_key`, or `X-API-Key` header.
- Canonical API host: `https://api.fxmacrodata.com/v1/`.
- Stronger client errors for HTTP/URL/timeout/invalid JSON, plus fail-fast when a non-USD call has no API key.
- `build_macro_context` fetches sections in parallel and returns per-section errors on partial failure.
- Added `fast_trade.ml.hmm_screen` and `fast_trade.ml.hmm_data` for HMM forecast screening.
- CLI: `ft screen hmm [config.yml] [--live] [--symbol ...]`.
- MCP tool: `hmm_screen(...)`.
- Example config: `hmm_screen_example.yml`.
- `scripts/*_hmm_screener.py` are thin wrappers around the product API.

### Breaking Changes (vs 2.0.0)
- Removed `ft terminal`, `fast_trade/terminal_ui.py`, and `docs/Terminal.md`.
- Dropped unused `prompt_toolkit` and `websockets` dependencies that supported the terminal UI.
- `ft logs` is portfolio-only (`--name <NAME>`); it no longer reads legacy `live_logs/` or `stream_logs/` from the terminal UI era.
- Use `ft backtests`, `ft logs --name <NAME>`, and `ft portfolio` for saved-run browsing, log tailing, and paper workflows.
- Saved backtests live under `ft_archive/backtests/` (not the old `saved_backtests/` directory).
- Dropped unused leftover files from the live/terminal era: `Live.plan.md`, standalone `genes.yml`, and unused `MANIFEST.INI`.

### Tests
- `test/test_fxmacrodata.py` (mocked URL construction, env key loading, HTTP/URL/JSON errors, context request shape, partial success).
- `test/test_hmm_screen.py` (synthetic OHLCV screen/filter/report coverage, MCP smoke).
- MCP smoke coverage in `test/test_mcp_server.py`.
- Expanded CLI coverage to 100%: logs tail/follow, portfolio passthrough, archive helpers, and `_parse_simple_yaml` edge cases (`test/test_cli_coverage_remaining.py` and related CLI suites).
- Correctness-first suite: golden `run_backtest` e2e, fee equity curve, trailing-stop PnL, action/sim path parity, trade quality, and documented metric formulas in `docs/METRICS.md` (`test/test_run_backtest_e2e.py`).
- Full-package line coverage gated at 100% via `.coveragerc` `fail_under = 100`.

## 2.0.0

### Release Highlights
- Major CLI/Terminal expansion: live/stream support, persistent JSONL logging, and terminal command mirroring.
- New paper portfolio runner with state persistence and daemon support.
- ML tooling additions (evolver/markov/regime) with examples and tests.
- Summary and backtest logic refactored into cleaner, modular components.
- YAML-first workflow: examples and strategies standardized to `.yml`.

### New Features

**Terminal & CLI**
- Interactive `ft terminal` improvements:
- Live runner (`LIVE START/STOP/VIEW`)
- Stream runner (`STREAM START/STOP/VIEW`)
- Persistent JSONL logs and terminal `LOGS` commands
- Terminal now forwards unknown commands to CLI (`ft <command>`)
- New `docs/Terminal.md` full usage guide.

**Paper Portfolio**
- New paper portfolio runner:
- `ft portfolio start` (daemon by default)
- `ft portfolio status`
- `ft portfolio stop`
- Persistent state and trade logs under `ft_archive/portfolio/<name>/`.
- Persistent state, parquet trades, and JSONL logs under `ft_archive/portfolio/<name>/`.

**ML Toolkit**
- Added `fast_trade/ml` package:
- `evolver.py`, `markov.py`, `regime.py`
- Example configs: `evolver_example.yml`, `regime_example.yml`
- New tests: `test/test_evolver.py`

### Refactors & Cleanup

**Summary System**
- `build_summary.py` split into:
- `fast_trade/summary/metrics.py`
- `fast_trade/summary/trades.py`
- Public API preserved via `fast_trade/summary/__init__.py`.

**Backtest Logic**
- Vectorization and logic helpers moved to `fast_trade/logic_utils.py`.
- `run_backtest.py` simplified and easier to maintain.

**CLI Rendering**
- Rendering utilities moved into `fast_trade/cli_render.py`.

### Behavior Changes (Potentially Breaking)
1. **Version Bump**
   - `pyproject.toml` now `2.0.0`.
2. **YAML-first examples**
   - JSON strategy/backtest examples removed (`*.json` deleted).
   - All sample configs now YAML.
3. **Terminal/CLI expansion**
   - Terminal now mirrors CLI commands by default (unknown commands run `ft <command>`).
4. **Log format**
   - Live, stream, and portfolio logs now default to `.jsonl`.
   - CLI readers keep backward compatibility with legacy `.log` files when present.

### Files Added / Removed

**Added**
- `fast_trade/portfolio.py`
- `fast_trade/logic_utils.py`
- `fast_trade/cli_render.py`
- `fast_trade/summary/*`
- `fast_trade/ml/*`
- `docs/Terminal.md`
- `evolver_example.yml`, `regime_example.yml`, `genes.yml`
- `run_parallel_example.py`

**Removed**
- `example_backtest.json`
- `strategy.json`
- `sma_strategy.json`

### Tests
- New test coverage for portfolio helpers.
- ML evolver tests added.
- All tests passing on `pytest -q`.

### Migration Notes
- Convert JSON strategy configs to YAML (`.yml`).
- Summary internals moved, public API preserved.
- Terminal now runs unknown commands via `ft <command>` by default.
- If you consume logs programmatically, switch to JSONL readers for:
  - `ft_archive/live_logs/<RUN_ID>.jsonl`
  - `ft_archive/stream_logs/<RUN_ID>.jsonl`
  - `ft_archive/portfolio/<NAME>/portfolio.jsonl`
