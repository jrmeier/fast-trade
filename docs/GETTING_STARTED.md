# Getting Started

`fast-trade` is a backtesting and strategy execution toolkit for market data stored in a local archive.

At a high level, it gives you:

- strategy configs in YAML
- local market data management
- backtests with summaries and saved runs
- non-interactive backtest browsing via `ft backtests`
- log tailing via `ft logs`
- a paper portfolio runner
- optional ML tooling for optimization, regime analysis, and HMM screening

## What It Is

`fast-trade` is designed around a simple workflow:

1. download or update market data into `ft_archive/`
2. define a strategy in YAML
3. validate and run backtests
4. review saved runs with `ft backtests`
5. optionally tail logs with `ft logs` or run a paper portfolio with `ft portfolio`

The project uses pandas-based dataframes internally, parquet storage for archive data, and a CLI-first interface through `ft`.

## Install

### Local Development Install

From the repo root:

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Package Install

```bash
pip install fast-trade
```

## Basic Concepts

### Archive

The archive is the local data store used by the CLI and backtest engine.

Default location:

```bash
ft_archive/
```

Common contents:

- `ft_archive/binanceus/*.parquet`
- `ft_archive/coinbase/*.parquet`
- `ft_archive/backtests/<RUN_ID>/`
- `ft_archive/strategies/*.yml`

### Strategy

A strategy is a YAML file that defines:

- market symbol and exchange
- timeframe or frequency
- indicators to compute
- entry and exit rules
- position sizing and optional stop behavior

Example files in the repo:

- `strategy.yml`
- `example_backtest.yml`
- `zma1_strat.yml`

### Backtest

A backtest runs a strategy against historical archive data and returns:

- summary metrics
- processed dataframe
- trade log dataframe

## First Run

### 1. Check the CLI

```bash
ft --help
```

### 2. Download Data

Example:

```bash
ft download BTCUSDT binanceus --start 2024-12-01 --end 2025-01-01
```

Or for Coinbase:

```bash
ft download BTC-USD coinbase --start 2025-01-01 --end 2025-02-01
```

### 3. Validate a Strategy

```bash
ft validate strategy.yml
```

### 4. Run a Backtest

```bash
ft backtest strategy.yml --save
```

Useful flags:

- `--save` saves the run into `ft_archive/backtests/`
- `--plot` generates a plot
- `--mods key value ...` overrides strategy fields at runtime

Example:

```bash
ft backtest strategy.yml --save --mods freq 1H trailing_stop_loss 0.02
```

### 5. Browse saved runs

```bash
ft backtests list
ft backtests show --index 1
ft logs --name demo --tail 200
```

## Common Commands

### Data

```bash
ft assets --exchange coinbase
ft download BTC-USD coinbase --start 2025-01-01 --end 2025-02-01
ft update_archive
```

### Backtests

```bash
ft validate strategy.yml
ft backtest strategy.yml
ft backtest strategy.yml --save
ft backtests list
```

### Logs

```bash
ft logs --name demo --tail 200
```

### Paper Portfolio

```bash
ft portfolio start strategy.yml --symbol BTC-USD --name demo
ft portfolio status demo
ft portfolio stop demo
```

### Machine Learning

```bash
ft evolve evolver_example.yml
ft regime_train regime_example.yml data.csv --out regime_model.pkl
ft regime_apply regime_model.pkl data.csv --out regime_output.csv
```

### HMM Screener

Rank symbols with a Gaussian HMM + Monte Carlo forecast screen. This ships in `2.1.0` as `ft screen hmm` (not available in PyPI `2.0.0`).

Archive-first example:

```bash
ft download BTC-USD coinbase --start 2024-01-01
ft screen hmm hmm_screen_example.yml
```

Live fetch example:

```bash
ft screen hmm --exchange coinbase --symbol BTC-USD --symbol ETH-USD --live
ft screen hmm --exchange hyperliquid --symbol BTC --live --json-out ft_archive/screens/hl.json
```

See `hmm_screen_example.yml` for filters, horizons, and output paths. Agents can call the MCP tool `hmm_screen`.

## Important Files

- `README.md`: top-level project overview
- `docs/CHANGELOG.md`: release notes and major changes
- `docs/RELEASE.md`: release checklist
- `docs/METRICS.md`: summary metric definitions used by backtests
- `docs/FEATURES.md`: CLI ↔ MCP feature matrix
- `hmm_screen_example.yml`: example config for `ft screen hmm`

## Tips

- Keep strategies in YAML, not JSON.
- Use `ft_archive/strategies/` as the default strategy location.
- Use `ft backtests list` / `ft backtests show` to inspect runs, `ft logs --name <NAME>` to tail portfolio JSONL logs, and `ft portfolio` for paper trading.
- Upgrading from `2.0.0`: `ft terminal` was removed in `2.1.0`; use the CLI commands above instead.
- Use `python -m pytest` instead of bare `pytest` if you want to guarantee the active environment is used.

## Troubleshooting

### No Saved Backtests

Run:

```bash
ft backtest strategy.yml --save --all
```

### Missing Archive Data

Check the local archive and download a range explicitly:

```bash
ft assets --exchange binanceus
ft download BTCUSDT binanceus --start 2024-12-01 --end 2025-01-01
```

### Need More Detail

Use these docs next:

- `docs/CHANGELOG.md`
- `docs/RELEASE.md`
