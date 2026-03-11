# Getting Started

`fast-trade` is a backtesting and strategy execution toolkit for market data stored in a local archive.

At a high level, it gives you:

- strategy configs in YAML
- local market data management
- backtests with summaries and saved runs
- an interactive terminal UI
- live signal generation and stream ingestion
- a paper portfolio runner
- optional ML tooling for optimization and regime analysis

## What It Is

`fast-trade` is designed around a simple workflow:

1. download or update market data into `ft_archive/`
2. define a strategy in YAML
3. validate and run backtests
4. review saved runs in the terminal
5. optionally run live signals, streams, or a paper portfolio

The project uses pandas-based dataframes internally, parquet storage for archive data, and a CLI-first interface through `ft`.

## Install

### Local Development Install

From the repo root:

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
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

### 5. Open the Terminal UI

```bash
ft terminal
```

From there you can:

- browse backtests
- view trades and summaries
- open or edit strategies
- run live signals
- review persisted logs
- start a paper portfolio

Full reference:

- `docs/Terminal.md`

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

### Terminal

```bash
ft terminal
ft logs --kind all --tail 200
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

## Important Files

- `README.md`: top-level project overview
- `docs/Terminal.md`: terminal command guide
- `docs/CHANGELOG.md`: release notes and major changes
- `docs/RELEASE.md`: release checklist
- `docs/ACTION_ENGINE_PLAN.md`: action-engine optimization notes
- `docs/RUN_ANALYSIS_PLAN.md`: simulation-engine optimization notes

## Tips

- Keep strategies in YAML, not JSON.
- Use `ft_archive/strategies/` as the default strategy location.
- Use `ft terminal` when you want the fastest way to inspect runs and operate the paper/live workflows.
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

- `docs/Terminal.md`
- `docs/CHANGELOG.md`
- `docs/RELEASE.md`
