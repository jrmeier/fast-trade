# Coinbase Top 10 Coin Screen: 30-60 Day Model

Generated: `2026-05-21T21:35:06.975946+00:00`
Source: Coinbase public Exchange API `/products`, `/ticker`, and daily `/candles` endpoints.
Fee note: Coinbase Advanced fees vary by maker/taker order type and fee tier; verify your account fee preview before trading.

## Quality Top 10 For Trading

Filter: at least `$3M` 24h quote volume, at least `$3M` 30-day average dollar volume, at least 180 daily candles, and 60-day drawdown no worse than `-45%`.

| Rank | Coin | Price | 24h $Vol | 30d avg $Vol | 30d | 60d | 30d practical goal | 60d practical goal | Downside p25 30/60 | 60d DD | HMM 30d |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `VVV-USD` | $18.19 | $15,660,151 | $8,479,080 | 104.9% | 207.5% | 30.0% to 50.0% | 50.0% to 90.0% | 130.3% / 499.7% | -24.0% | 121.1% |
| 2 | `ZEC-USD` | $676 | $96,720,659 | $53,661,162 | 112.8% | 210.6% | 30.0% to 50.0% | 50.0% to 90.0% | 106.3% / 405.0% | -19.7% | 329.9% |
| 3 | `ONDO-USD` | $0.4163 | $18,607,940 | $10,304,251 | 61.1% | 69.3% | 21.4% to 38.6% | 24.3% to 46.1% | 32.2% / 91.4% | -23.8% | 37.8% |
| 4 | `DASH-USD` | $49.76 | $7,864,864 | $3,712,414 | 35.5% | 54.7% | 12.4% to 24.5% | 19.2% to 38.1% | 9.5% / 35.9% | -27.4% | 106.4% |
| 5 | `INJ-USD` | $5.238 | $4,126,697 | $3,044,979 | 60.4% | 77.6% | 21.1% to 38.2% | 27.1% to 50.7% | 34.3% / 95.6% | -11.6% | 4.2% |
| 6 | `NEAR-USD` | $1.958 | $19,281,110 | $4,427,445 | 41.3% | 53.7% | 14.4% to 27.7% | 18.8% to 37.5% | 26.5% / 79.2% | -12.0% | -4.2% |
| 7 | `AERO-USD` | $0.4702 | $4,952,627 | $3,821,624 | 23.5% | 51.2% | 8.2% to 17.9% | 17.9% to 36.2% | 9.4% / 35.8% | -23.4% | -2.6% |
| 8 | `PENGU-USD` | $0.009652 | $5,624,117 | $8,565,056 | 24.1% | 44.4% | 8.4% to 18.3% | 15.5% to 32.4% | 9.3% / 29.8% | -24.3% | -4.2% |
| 9 | `TAO-USD` | $284.2 | $16,265,875 | $12,303,358 | 16.0% | 8.5% | 5.6% to 13.8% | 3.0% to 12.7% | 3.3% / 20.5% | -31.0% | -7.3% |
| 10 | `SUI-USD` | $1.133 | $46,793,547 | $17,411,307 | 19.3% | 25.1% | 6.8% to 15.6% | 8.8% to 21.8% | 0.0% / 9.6% | -21.7% | -2.6% |

## Raw Speculative Momentum Names

These appeared in the raw score before the stricter quality framing. Some have thinner average volume, newer listings, or extremely convex bootstrap tails. Treat as watchlist/speculative only.

| Rank | Coin | 24h $Vol | 30d avg $Vol | 30d | 60d | Raw p75 30d | 60d DD |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `VVV-USD` | $15,660,151 | $8,479,080 | 104.9% | 207.5% | 283.8% | -24.0% |
| 2 | `ZEC-USD` | $96,720,659 | $53,661,162 | 112.8% | 210.6% | 233.7% | -19.7% |
| 3 | `FIDA-USD` | $6,782,736 | $514,557 | 155.8% | 201.4% | 271.5% | -19.2% |
| 4 | `USELESS-USD` | $5,799,655 | $1,632,865 | 81.3% | 119.8% | 144.5% | -29.6% |
| 5 | `JTO-USD` | $5,249,300 | $1,807,998 | 58.2% | 92.8% | 104.7% | -31.0% |
| 6 | `ONDO-USD` | $18,607,940 | $10,304,251 | 61.1% | 69.3% | 82.7% | -23.8% |
| 7 | `DASH-USD` | $7,864,864 | $3,712,414 | 35.5% | 54.7% | 64.1% | -27.4% |
| 8 | `INJ-USD` | $4,126,697 | $3,044,979 | 60.4% | 77.6% | 81.6% | -11.6% |
| 9 | `NEAR-USD` | $19,281,110 | $4,427,445 | 41.3% | 53.7% | 76.3% | -12.0% |
| 10 | `PROVE-USD` | $5,891,711 | $379,285 | 34.3% | 30.9% | 41.4% | -31.5% |

## Method

- Liquidity source: current Coinbase public ticker plus daily candle dollar volume.
- Model: recent 30/60/90-day momentum, 30-day average dollar volume, 60-day drawdown, bootstrapped 30/60-day return distributions from the last 90 daily returns, plus a 3-state Gaussian HMM regime estimate.
- Practical goals are intentionally capped below raw model tails. The bootstrap/HMM outputs can get absurd after fast moves; the planning ranges are what I would use for expectation setting.
- This is a trading shortlist, not financial advice. Use limit orders, check spread/depth, and size positions so a 20-40% adverse move is survivable.
