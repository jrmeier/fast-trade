# Hyperliquid HMM Screener

Generated: `2026-05-21T22:13:20.643306+00:00`

Ranges are p25 / p50 / p75 simulated returns from the current HMM state.
This screens Hyperliquid perpetual markets. It does not size leverage or place trades.

| Rank | Coin | Price | 24h Ntl Vol | Avg 30d Ntl Vol | 7d | 30d | 60d | 60d DD | Funding | Score |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `ZEC` | $670.78 | $236.6M | $152.4M | 1.4% / 19.6% / 41.5% | 34.4% / 106.3% / 227.6% | 73.5% / 279.5% / 794.6% | -19.7% | 0.0% | 280.44 |
| 2 | `VVV` | $18.132 | $25.9M | $13.5M | -9.3% / 8.4% / 32.8% | -3.7% / 33.2% / 94.2% | 7.7% / 69.5% / 182.7% | -24.1% | 0.0% | 64.23 |
| 3 | `HYPE` | $57.864 | $2.00B | $365.2M | -7.6% / 3.0% / 15.4% | -14.2% / 5.0% / 31.4% | -19.2% / 9.3% / 46.4% | -13.0% | 0.0% | -4.57 |
| 4 | `BTC` | $77661 | $2.39B | $2.11B | -3.3% / -0.1% / 2.9% | -12.1% / -3.3% / 4.5% | -21.1% / -8.1% / 4.0% | -7.5% | 0.0% | -19.37 |
| 5 | `SOL` | $87.362 | $231.6M | $214.4M | -5.5% / -0.8% / 4.3% | -13.5% / -3.9% / 6.4% | -23.5% / -9.7% / 5.9% | -13.9% | 0.0% | -22.26 |
| 6 | `XRP` | $1.374 | $25.1M | $34.9M | -5.5% / -1.6% / 2.8% | -15.4% / -6.9% / 2.7% | -25.7% / -13.4% / 0.1% | -8.3% | 0.0% | -29.00 |
| 7 | `TON` | $2.0519 | $43.5M | $51.7M | -10.0% / -1.3% / 7.9% | -19.5% / -4.7% / 13.1% | -29.1% / -10.2% / 13.6% | -29.9% | 0.0% | -29.30 |
| 8 | `ETH` | $2134.3 | $827.3M | $751.6M | -4.1% / 0.0% / 4.0% | -17.6% / -5.5% / 5.8% | -30.6% / -13.5% / 3.9% | -12.7% | 0.0% | -29.82 |
| 9 | `TAO` | $283.08 | $16.4M | $14.4M | -9.1% / -1.3% / 7.4% | -20.7% / -5.2% / 12.3% | -29.9% / -10.1% / 15.7% | -31.0% | 0.0% | -30.94 |
| 10 | `NEAR` | $1.9337 | $36.5M | $11.9M | -9.9% / -0.5% / 11.4% | -20.9% / -5.2% / 16.6% | -30.3% / -10.4% / 20.2% | -11.9% | 0.0% | -31.34 |
| 11 | `DOGE` | $0.10537 | $22.5M | $34.3M | -6.4% / -1.6% / 3.4% | -17.6% / -7.8% / 3.1% | -29.9% / -15.8% / -0.2% | -10.9% | 0.0% | -33.23 |
| 12 | `PUMP` | $0.001821 | $13.8M | $11.1M | -10.6% / -1.7% / 7.9% | -25.7% / -9.9% / 9.4% | -40.1% / -20.1% / 6.1% | -23.5% | 0.0% | -45.66 |
| 13 | `FARTCOIN` | $0.20087 | $14.4M | $16.0M | -13.7% / -2.0% / 11.2% | -30.3% / -9.0% / 20.2% | -42.3% / -14.1% / 28.5% | -31.3% | 0.0% | -46.39 |
| 14 | `SUI` | $1.1235 | $67.8M | $23.9M | -9.4% / -3.1% / 3.5% | -26.7% / -13.3% / 3.0% | -41.1% / -25.5% / -4.4% | -21.8% | 0.0% | -52.69 |

## Practical Read

- Favor positive 7d and 30d medians with controlled p25 downside and strong notional volume.
- Hyperliquid perps add liquidation and funding risk; this report assumes no leverage.
- Very high upside usually means unstable regime behavior.
- Size smaller on lower-liquidity alts, especially when using perps.

## Skipped

- `LIT`: only 151 candles
- `ASTER`: below 30d average notional volume threshold
- `WLD`: below 30d average notional volume threshold
- `ONDO`: below 30d average notional volume threshold
- `XMR`: below 30d average notional volume threshold
- `PURR`: below 30d average notional volume threshold
