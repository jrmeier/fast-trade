# Coinbase BTC-USD Strategy Screen

Generated: 2026-05-21

## Scope

- Market: `BTC-USD` on Coinbase.
- Data: hourly candles from `2025-01-01 00:00:00` through `2026-05-21 20:00:00`.
- Source data artifact: `reports/coinbase_btc_usd_1h_screen_data.parquet`.
- Starting balance: `$1000`.
- Fee assumption: `0.6%` per executed side.
- Candidate strategies screened: `315`; valid backtests: `267`; filtered conservative candidates: `21`.

## Recommended Files

| File | Style | Allocation | Full return | 2026 return | Max drawdown | Executed trades |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `generated_strategies/recommended_conservative_mean_revert_25pct.yml` | Low-frequency mean reversion | 25% / $250 max | 0.454% | 0.164% | -0.297% | 4 |
| `generated_strategies/recommended_balanced_trend_35pct.yml` | 4h trend-following | 35% / $350 max | 2.483% | 2.075% | -9.387% | 32 |
| `generated_strategies/recommended_defensive_trend_25pct.yml` | 4h defensive trend-following | 25% / $250 max | 0.759% | 1.221% | -6.414% | 30 |

## Takeaway

The backtests did not find a high-return, low-risk strategy. The best conservative candidates are profitable after a high fee assumption, trade rarely, and avoided the BTC buy-and-hold drawdown in this window, but returns were modest. The balanced 35% trend strategy is the only one worth paper-trading first; do not deploy it live without forward testing and order-size/fee verification in Coinbase.

