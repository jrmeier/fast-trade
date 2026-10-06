# Feature Matrix

Current surface area for `fast-trade` `3.0.0`. Use this table to see what exists in the CLI, what is exposed on the MCP server, and what changed since earlier PyPI releases. Dataframes throughout are Polars (`pl.DataFrame` with a `date` column).

| Feature | CLI | MCP tool | Since | Notes |
|---------|-----|----------|-------|-------|
| Polars-native dataframes | — | — | 3.0.0 | Breaking: `pl.DataFrame` + `date` column; no pandas dependency |
| Download archive data | `ft download` | `download` | stable | Binance / Coinbase |
| List assets | `ft assets` | `assets`, `list_assets` | stable | `list_assets` returns a plain list helper |
| Run backtest | `ft backtest` | `backtest` | stable | |
| Browse saved backtests | `ft backtests` | `backtests` | stable | |
| Migrate saved backtests | `ft migrate_backtests` | `migrate_backtests` | stable | sqlite/json → parquet/yml |
| Migrate archive sqlite | `ft migrate_archive` | `migrate_archive` | stable | |
| Validate strategy | `ft validate` | `validate` | stable | |
| Tail portfolio logs | `ft logs --name <NAME>` | `logs`, `tail_log` | stable | Portfolio JSONL only; `tail_log` reads directly |
| Update archive | `ft update_archive` | `update_archive` | stable | |
| GA evolver | `ft evolve` | `evolve` | 2.0.0 | |
| Regime train | `ft regime_train` | `regime_train` | 2.0.0 | |
| Regime apply | `ft regime_apply` | `regime_apply` | 2.0.0 | |
| Paper portfolio start | `ft portfolio start` | `portfolio_start` | 2.0.0 | Paper only |
| Paper portfolio status | `ft portfolio status` | `portfolio_status`, `portfolio_state` | 2.0.0 | `portfolio_state` reads JSON directly |
| Paper portfolio stop | `ft portfolio stop` | `portfolio_stop` | 2.0.0 | |
| HMM forecast screen | `ft screen hmm` | `screen_hmm`, `hmm_screen` | 2.1.0 | `screen_hmm` wraps CLI; `hmm_screen` returns JSON |
| Classifier → `ml_signal` example | `examples/ml_classifier_backtest.py` | — | 2.1.x | Library helpers in `fast_trade.ml.classifier`; uses `column` datapoint |
| Walk-forward classifier benchmark | `examples/ml_walk_forward.py` | — | unreleased | Polars, purged rolling training windows, matching execution and costs for baselines; `fast_trade.ml.walk_forward` |
| FXMacroData context | — | `fxmacrodata_macro_context` | 2.1.0 | API helper, no dedicated CLI |
| List strategy files | — | `list_strategies` | stable | Helper over `ft_archive/strategies/` |
| Escape hatch | any `ft ...` | `ft_command`, `ft_command_str` | stable | Raw CLI passthrough |

## MCP-only helpers

These are not separate CLI commands but remain useful for agents:

- `list_strategies`
- `list_assets`
- `portfolio_state`
- `tail_log`
- `hmm_screen`
- `fxmacrodata_macro_context`

## Raw CLI access

Every `ft` command is also available through:

```python
ft_command(["backtest", "strategy.yml", "--save"])
ft_command_str("backtests show --index 1")
```

All dedicated MCP CLI wrappers run with `--no-interactive`.

## Backtest correctness

- `start` and `stop` are optional. Archive loading accepts ISO dates, datetimes,
  and epoch seconds/milliseconds; date-only stop bounds include the entire day.
- Archive warmup includes float-valued indicator periods such as `41.0`.
- Legacy frequency aliases remain supported; a bare number such as `"30"`
  means 30 minutes. Validation uses the same frequency parser as the engine.
- Invalid `any_enter`/`any_exit` rules raise during strategy validation.
- Peak equity includes the marked value of open positions. Missing metrics or
  malformed summary evaluation rules raise rather than silently being skipped.

## Related entrypoints

- `ftv convert` is a separate console script and is not part of the MCP server today.
- Start the MCP server with `python -m fast_trade.mcp_server`.
