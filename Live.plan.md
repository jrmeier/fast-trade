# Live Plan

## Goals
- Live WebSocket execution for strategies with paper trading.
- Low-latency updates, safe reconnects, and deterministic state recovery.
- Store all events in DuckDB, and periodically export to Parquet for analytics.

## Architecture Overview

### Components
1) **MarketData WS Client**
   - Connect to exchange WebSocket(s)
   - Subscribe to tick/trade or kline streams
   - Reconnect with exponential backoff
   - Detect gaps and trigger REST backfill

2) **Candle Aggregator**
   - Aggregate ticks into candles by `freq`
   - Emits `candle_update` (partial) and `candle_close` (final)

3) **Indicator Engine**
   - Incrementally update indicators from candle stream
   - Use rolling windows per indicator
   - Avoid full dataframe recompute

4) **Strategy Evaluator**
   - Evaluate `enter/exit/any_*` on candle close
   - Emits `signal` events

5) **Execution Engine**
   - Paper trading initially (market orders only)
   - Fill price = last close ± slippage
   - Fees applied per trade
   - Risk checks (max position, max drawdown)

6) **Storage Layer**
   - DuckDB append-only event tables
   - Parquet export per day
   - State snapshots for recovery

### Data Flow
```
WS Ticks -> Aggregator -> Candle Close
         -> Indicators -> Strategy Eval -> Signals
         -> Execution -> Fills -> Storage
```

## File Layout
- `fast_trade/live/runner.py`  (orchestration)
- `fast_trade/live/market_data.py` (WS + REST backfill)
- `fast_trade/live/aggregator.py`  (candle builder)
- `fast_trade/live/indicators.py`  (rolling indicators)
- `fast_trade/live/strategy.py`    (signal eval)
- `fast_trade/live/executor.py`    (paper trading)
- `fast_trade/live/storage.py`     (DuckDB + Parquet export)

## Storage Details

### DuckDB tables
- **ticks**: `ts, price, size, symbol, exchange`
- **candles**: `ts, open, high, low, close, volume, symbol, exchange, freq`
- **signals**: `ts, action, reason, symbol, exchange`
- **fills**: `ts, side, price, qty, fee, order_id, symbol, exchange`
- **state**: `ts, cash, position_qty, position_avg, equity, last_candle_ts`

### Parquet export
- Export every N minutes or on shutdown
- Partition by day: `archive/live/<exchange>/<symbol>/candles/date=YYYY-MM-DD/*.parquet`
- Similar for ticks, fills, signals
- Optional prune DuckDB rows after export

## Paper Trading Rules
- `lot_size_perc` of available cash
- `max_lot_size` cap (optional)
- Fee model: % of notional
- Slippage model: `price * (1 ± slippage)`
- Long-only to start; optional short support later

## Recovery Model
- On startup, load `state.yml` (cash, position, last candle)
- Backfill missing candles from REST between last candle and now
- Resume streaming updates

## CLI Design
```
ft live strategy.yml --paper --exchange binanceus --symbol BTCUSDT --freq 1m \
  --slippage 0.0005 --fee 0.0005 --flush-interval 60
```

Options:
- `--paper` / `--live`
- `--exchange`, `--symbol`, `--freq`
- `--slippage`, `--fee`
- `--flush-interval`
- `--log-level`

## Milestones
1) **Skeleton + schemas**
2) **WS client + backfill**
3) **Aggregation + indicators**
4) **Strategy + paper execution**
5) **CLI + logging**
6) **Tests + resilience**

## Tests
- Aggregator correctness (edge candles)
- Indicator rollups (match batch results)
- Paper fills (cash/position math)
- DuckDB export integrity
- Recovery from state snapshot

## Open Questions
- Which exchange first (Binance US vs Coinbase)?
- Candle close only vs intrabar?
- Risk defaults (max drawdown, max position)?
