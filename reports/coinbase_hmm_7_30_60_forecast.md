# Coinbase HMM Screener

Generated: `2026-05-21T22:09:44.243209+00:00`

Ranges are p25 / p50 / p75 simulated returns from the current HMM state.
This is a probabilistic regime screen, not financial advice or a guarantee.

| Rank | Product | Price | 24h Vol | Avg 30d Vol | 7d | 30d | 60d | 60d DD | Score |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `ZEC-USD` | $672.66 | $93.8M | $53.7M | 3.1% / 23.9% / 52.0% | 34.6% / 111.7% / 239.3% | 59.3% / 222.9% / 576.8% | -19.7% | 257.70 |
| 2 | `VVV-USD` | $18.1437 | $15.4M | $8.5M | -8.5% / 8.2% / 32.3% | -13.5% / 19.6% / 74.3% | -13.9% / 39.5% / 135.2% | -24.0% | 25.89 |
| 3 | `DASH-USD` | $49.74 | $7.9M | $3.7M | -11.2% / 4.8% / 28.6% | -16.4% / 13.9% / 67.9% | -21.2% / 21.9% / 109.5% | -27.4% | 8.50 |
| 4 | `INJ-USD` | $5.24 | $3.8M | $3.0M | -7.7% / -0.5% / 7.2% | -16.6% / -2.2% / 15.1% | -26.9% / -6.8% / 17.5% | -11.6% | -22.21 |
| 5 | `TAO-USD` | $282.42 | $16.1M | $12.3M | -8.8% / -0.9% / 7.7% | -19.4% / -2.6% / 15.5% | -27.8% / -7.0% / 21.0% | -31.0% | -25.52 |
| 6 | `NEAR-USD` | $1.941 | $19.3M | $4.4M | -10.1% / -0.4% / 11.9% | -20.8% / -4.5% / 17.8% | -30.6% / -9.2% / 21.1% | -12.0% | -29.92 |
| 7 | `ONDO-USD` | $0.42623 | $18.9M | $10.3M | -9.6% / -0.0% / 12.1% | -21.7% / -5.4% / 14.9% | -33.5% / -13.2% / 12.5% | -23.8% | -33.64 |
| 8 | `SUI-USD` | $1.1236 | $46.3M | $17.4M | -7.6% / -1.4% / 5.2% | -19.8% / -6.6% / 8.0% | -33.1% / -15.2% / 5.8% | -21.7% | -34.05 |
| 9 | `PENGU-USD` | $0.009521 | $5.5M | $8.6M | -10.8% / -2.0% / 8.6% | -24.1% / -7.4% / 13.4% | -35.1% / -14.7% / 15.8% | -24.3% | -38.86 |
| 10 | `AERO-USD` | $0.47172 | $5.3M | $3.8M | -11.0% / -2.2% / 8.3% | -24.8% / -7.9% / 12.5% | -35.7% / -14.2% / 14.0% | -23.4% | -39.77 |

## Practical Read

- Favor names with positive 7d and 30d medians, tolerable p25 downside, and enough volume.
- Treat very high upside as regime instability; cap position size and avoid averaging down blindly.
- Re-run before trading. A daily-candle HMM can change materially after a single large candle.
