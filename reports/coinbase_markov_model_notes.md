# Coinbase BTC-USD Markov/HMM Screen

Data: `reports/coinbase_btc_usd_1h_screen_data.parquet` from `2025-01-01 00:00:00` through `2026-05-21 20:00:00`.
Training window: before `2026-01-01 00:00:00`. Out-of-sample check: `2026-01-01 00:00:00` onward.

## Actual 2026 Returns

| Rank | Strategy | 2026 return | Full return | Max drawdown | Trades |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | `recommended_balanced_trend_35pct` | 2.351% | 2.483% | -9.387% | 32 |
| 2 | `03_btc_4h_trend_ema12_84_rsi60_45` | 1.692% | 1.881% | -6.801% | 32 |
| 3 | `04_btc_4h_trend_ema12_84_rsi60_42` | 1.690% | 1.420% | -7.221% | 32 |
| 4 | `05_btc_4h_trend_ema12_84_rsi60_48` | 1.690% | 1.153% | -7.463% | 34 |
| 5 | `recommended_defensive_trend_25pct` | 1.193% | 0.759% | -6.414% | 30 |
| 6 | `02_btc_1h_mean_revert_rsi28_62_bb20` | 0.164% | 0.594% | -0.738% | 6 |
| 7 | `recommended_conservative_mean_revert_25pct` | 0.163% | 0.454% | -0.297% | 4 |

## Markov/HMM Model Selection

| Rank | Model | 2026 selected return | Selected drawdown | Current predicted best |
| ---: | --- | ---: | ---: | --- |
| 1 | `hmm_s5_vol12_trend24_volume0` | 0.770% | -3.534% | `recommended_conservative_mean_revert_25pct` |
| 2 | `hmm_s3_vol20_trend48_volume0` | 0.163% | -0.297% | `02_btc_1h_mean_revert_rsi28_62_bb20` |
| 3 | `hmm_s3_vol48_trend120_volume0` | 0.163% | -0.297% | `recommended_balanced_trend_35pct` |
| 4 | `hmm_s4_vol48_trend120_volume1` | 0.163% | -0.297% | `recommended_balanced_trend_35pct` |
| 5 | `hmm_s5_vol20_trend48_volume1` | 0.163% | -0.297% | `05_btc_4h_trend_ema12_84_rsi60_48` |
| 6 | `hmm_s4_vol20_trend48_volume1` | -4.603% | -4.829% | `recommended_balanced_trend_35pct` |

## Current Consensus

| Rank | Strategy | Votes | Avg expected next-hour return | Avg score |
| ---: | --- | ---: | ---: | ---: |
| 1 | `recommended_balanced_trend_35pct` | 3 | 0.00187% | 0.0148 |
| 2 | `recommended_conservative_mean_revert_25pct` | 1 | 0.00035% | 0.0399 |
| 3 | `02_btc_1h_mean_revert_rsi28_62_bb20` | 1 | 0.00029% | 0.0239 |
| 4 | `05_btc_4h_trend_ema12_84_rsi60_48` | 1 | 0.00135% | 0.0157 |

## Interpretation

The current HMM consensus favors `recommended_balanced_trend_35pct`.
Treat this as a regime filter, not a forecast guarantee. Expected next-hour edge is tiny because these strategies trade rarely.
