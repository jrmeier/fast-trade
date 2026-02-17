# FT Terminal Guide

This document describes the interactive `ft terminal` experience and how it connects to the CLI, live runs, streams, and the paper portfolio runner.

## Overview

`ft terminal` is an interactive TTY UI used to explore saved backtests, view plots and summaries, and run live/paper components. It loads a saved backtest run and provides shortcuts for pages and actions.

Important behaviors:
- Terminal requires a real TTY. It will exit in non‑interactive environments.
- Terminal can run any CLI command that is not handled by the UI directly. This keeps it in sync with the CLI.
- Live and stream output is logged to disk for later review.
- Paper portfolio runs can be started from the terminal and can run as background daemons.

## How To Start

### Open Terminal

```bash
ft terminal
```

By default it opens the most recent saved backtest. You can select a specific run:

```bash
ft terminal --index 1        # 1 = latest
ft terminal --index 3        # 3rd most recent
ft terminal --run-id <ID>    # exact run folder name
```

### Requirements

You need saved backtests in the archive. If you do not have any:

```bash
ft backtest ./strategy.yml --save --all
```

This writes the backtest to `ft_archive/backtests/<RUN_ID>/`.

## Terminal Pages

The terminal UI has several “pages.” Use these short commands to switch between them:

- `DB` — Dashboard (default)
- `TR` — Trades table
- `SUM` — Summary page
- `TS` — Tearsheet page
- `GP` — Graph page
- `POS` — Positions metrics page
- `LIVE` — Live status page
- `STREAM` — Stream status page
- `HELP` — Command help page

Navigation shortcuts:
- `N` / `P` — Next/Previous page in trades view
- `Q` — Quit

## Strategy Selection

Terminal keeps a “current strategy” so you can run or edit it.

### Pick a Strategy

```text
OPEN STRAT
```

Select from:
- `ft_archive/strategies/*.yml`
- (fallback) repo root `*.yml` files

The selection is persisted to `ft_archive/last_strategy_path.txt`.

### Show Current Strategy

```text
SHOW STRAT
```

### Edit Current Strategy

```text
EDIT STRAT
```

This writes `strategy.override.yml` into the backtest run folder (same as the current run).

### Create a New Strategy

```text
NEW STRAT
```

Defaults to saving under `ft_archive/strategies/strategy.new.yml`.

## Backtests From Terminal

You can run a backtest from the terminal using the current strategy.

```text
BT
```

Optional flags:
- `BT SAVE` — Save results
- `BT PLOT` — Plot results
- `BT MODS key value ...` — Override strategy fields

Example:

```text
BT SAVE PLOT MODS freq 1H trailing_stop_loss 0.02
```

## Live Runner (Paper Signals)

The live runner **does not execute trades**. It reads the latest OHLCV from the archive and produces ENTER/EXIT/HOLD actions.

### Start Live

```text
LIVE START [SYMBOL]
```

- If a symbol is provided, it overrides the strategy symbol for the live run.
- Default symbol is taken from the selected strategy.

### View Live

```text
LIVE VIEW
```

Live actions are also written to:

```
ft_archive/live_logs/<RUN_ID>.log
```

### Stop Live

```text
LIVE STOP
```

## Stream Runner (Coinbase Websocket)

The stream runner subscribes to Coinbase Advanced Trade websocket channels and writes market data to the archive.

### Start Stream

```text
STREAM START <SYMBOL> channels=trades,level2
```

- Default channel is `market_trades` if none specified.
- `trades` is mapped to `market_trades`.

### View Stream

```text
STREAM VIEW
```

### Stop Stream

```text
STREAM STOP
```

### What Is Written

- Trades: `ft_archive/coinbase/trades/<SYMBOL>-YYYY-MM-DD.parquet`
- Klines: `ft_archive/coinbase/<SYMBOL>.parquet`

The stream builds candles in memory and flushes every minute. It also writes the current in‑progress minute.

## Logs In Terminal

Use `LOGS` to view persisted log files without leaving the terminal.

```text
LOGS
LOGS LIVE
LOGS STREAM
LOGS FOLLOW
LOGS LIVE FOLLOW
LOGS STREAM FOLLOW
```

The logs are stored at:

- Live: `ft_archive/live_logs/<RUN_ID>.log`
- Stream: `ft_archive/stream_logs/<RUN_ID>.log`
- Portfolio: `ft_archive/portfolio/<NAME>/portfolio.log`

## Paper Portfolio Runner

The paper portfolio runner simulates a single‑symbol strategy and persists state and trades.

### Start Portfolio

In terminal, if you have a strategy selected (`OPEN STRAT`), you can run:

```text
PORTFOLIO START --symbol BTC-USD
```

If you don’t pass a strategy path, it uses the current selected strategy.

By default it runs **as a daemon**. Use `--no-daemon` to run in the foreground.

Useful flags:
- `--symbol BTC-USD`
- `--cash 10000`
- `--name my_portfolio`
- `--once` (single cycle)
- `--no-daemon` (foreground)

### Status

```text
PORTFOLIO STATUS <name>
```

Shows current cash, position, equity, and runner status (pid if running).

### Stop

```text
PORTFOLIO STOP <name>
```

### Data Files

- State: `ft_archive/portfolio/<name>/state.json`
- Trades: `ft_archive/portfolio/<name>/trades.parquet`
- Logs: `ft_archive/portfolio/<name>/portfolio.log`

### Important Notes

- Portfolio uses the archive OHLCV data; make sure streams are running or `ft update_archive` runs periodically.
- The portfolio runner does not place real trades. It simulates fills at the latest close price.

## CLI Mirroring Inside Terminal

Any command not handled by the terminal UI is forwarded to the CLI.

Example:

```text
ASSETS --exchange coinbase
DOWNLOAD BTC-USD coinbase --start 2024-12-01 --end 2025-01-01
PORTFOLIO START --symbol BTC-USD
```

The terminal automatically lowercases the first two tokens for compatibility.

## Full Command List (Terminal)

### Navigation
- `DB` — Dashboard
- `TR` — Trades
- `SUM` — Summary
- `TS` — Tearsheet
- `GP` — Graph
- `POS` — Positions
- `HELP` — Help
- `Q` — Quit
- `N` / `P` — Next/Prev page in trades

### Live & Stream
- `LIVE START [SYMBOL]`
- `LIVE STOP`
- `LIVE VIEW`
- `STREAM START <SYMBOL> channels=trades,level2`
- `STREAM STOP`
- `STREAM VIEW`

### Strategies
- `OPEN STRAT`
- `SHOW STRAT`
- `EDIT STRAT`
- `NEW STRAT`

### Backtests
- `BT` (runs current strategy)
- `BT SAVE`
- `BT PLOT`
- `BT MODS key value ...`

### Logs
- `LOGS [LIVE|STREAM|ALL] [FOLLOW]`

### Portfolio
- `PORTFOLIO START [--symbol ...] [--cash ...] [--name ...] [--once] [--no-daemon]`
- `PORTFOLIO STATUS <name>`
- `PORTFOLIO STOP <name>`

### Other
- `UA` — Update archive
- `EVOLVE <config.yml>` — Run GA optimization (see `evolver_example.yml`)
- `REGIME TRAIN <config.yml> <data.csv> [--out regime_model.pkl]` — Train regime model
- `REGIME APPLY <model.pkl> <data.csv> [--out regime_output.csv]` — Apply regime model

## Troubleshooting

### “No saved backtests found”
Run a backtest with `--save`:

```bash
ft backtest ./strategy.yml --save --all
```

### Live Actions Are Not Updating
- Ensure the stream is running for the same symbol.
- Verify archive file mtime:

```bash
stat ft_archive/coinbase/<SYMBOL>.parquet
```

### Logs Not Updating
- Use `LOGS STREAM FOLLOW` or `LOGS LIVE FOLLOW` to verify live stream output.
- Check file paths under `ft_archive/`.
