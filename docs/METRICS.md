# Metric Definitions

These are the formulas implemented by `fast_trade`. Tests lock these definitions.
They are library-specific and may differ from industry-standard finance conventions.

## Return percentage (`return_perc`)

Computed from the trade log’s adjusted account value:

```text
return_perc = 100 - (first_adj_account_value / last_adj_account_value) * 100
```

Rounded to 3 decimal places. Empty trade log or zero last value → `0.0`.

This is **not** `(last / first - 1) * 100`.

## Buy and hold percentage (`buy_and_hold_perc`)

```text
buy_and_hold_perc = (1 - (first_close / last_close)) * 100
```

Rounded to 3 decimal places. Zero last close → `0.0`.

## Sharpe ratio (`sharpe_ratio` / `calculate_shape_ratio`)

On per-bar `adj_account_value_change_perc`:

```text
sharpe = (mean / std) * sqrt(n_bars)
```

- Not annualized to a calendar convention (no `* sqrt(252)`).
- No risk-free rate subtraction.
- Zero / NaN std or mean → `0.0`.
- Rounded to 3 decimal places.

## Top-level max drawdown (`max_drawdown` in `build_summary`)

```text
max_drawdown = min(adj_account_value)
```

This is the **minimum equity value**, not a peak-to-trough percentage.

## Nested drawdown metrics (`drawdown_metrics`)

`calculate_drawdown_metrics` reports peak-to-trough style fields such as
`max_drawdown_pct` (percentage). Prefer these when comparing to conventional
drawdown definitions.

## Portfolio vs backtest

Paper portfolio `apply_action` does not apply the same commission model as
`run_analysis.apply_logic_to_df`. Do not expect identical equity for the same
signals across the two paths.
