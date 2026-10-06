# BTC-USD walk-forward benchmark: 2025 Q1

This exploratory run does **not establish a trading edge**. Across 17 test folds,
the classifier lost 0.13% at the median and 1.39% on average after commission.
It beat buy-and-hold in 7 of 17 folds and RSI in 6 of 17. A median ROC AUC of
0.643 did not translate into consistent trading profits at the fixed 0.5 signal
cutoff. Beating a random signal is a sanity check, not sufficient evidence.

| Strategy | Median fold return | Folds beaten by classifier |
| --- | ---: | ---: |
| Classifier | -0.1299% | — |
| Buy-and-hold | -0.2820% | 7/17 (41.2%) |
| RSI 14, enter below 30 / exit above 70 | 0.0000% | 6/17 (35.3%) |
| Random exposure | -2.6067% | 12/17 (70.6%) |

The classifier completed 82 trades. Each fold starts with $1,000; the results
are independent windows, so their means and medians are not a compounded or
annualized portfolio return.

## Data and fixed settings

The included `input.parquet` contains 2,160 hourly Coinbase BTC-USD bars for
January 1 through March 31, 2025 (UTC, stored as naive datetimes). They were
aggregated from the existing local archive: open=first, high=max, low=min,
close=last, volume=sum. The source segment contains 129,600 distinct minute
bars, exactly 60 per hour, with no missing minutes. The period was selected
for complete archived coverage. Other portions of the archive have gaps.

This snapshot is historical research data, not a prospectively reserved
holdout. No parameter search was performed for this report. The fixed setup is:

- Eleven causal features: seven OHLCV features plus RSI 14, EMA 12, EMA 26 and
  ATR 14. Twenty bars provide feature warmup.
- A rolling 400-bar training window, with five final rows purged. All 395
  training labels finish before the first test bar. Each fold fits sklearn's
  `HistGradientBoostingClassifier` with seed `42 + fold` and default settings.
- A positive label means a forward five-bar close return above 1%. The model
  enters at probability 0.5 or higher, and exits otherwise.
- Nonoverlapping 100-bar test windows, stepping by 100 bars. Evaluation runs
  from January 18 12:00 through March 30 07:00. The final 40 input bars do not
  form a complete fold. Classification scores omit each test window's last
  five labels so their outcomes cannot cross its end.
- All four strategies observe a signal at the close and fill at the following
  bar close. Each begins flat and closes any final position at its last test
  close. RSI gets the same preceding price history for indicator warmup.
- Commission is an illustrative 0.1% per side (not a verified account fee
  tier). Slippage, spreads and financing are absent. Random signals use the
  training positive-label fraction, with seed `42 + 1000 + fold`.

Research returns use `(final_equity / initial_cash - 1) * 100`, including both
entry and exit fees. Trade counts are completed positions. These definitions
are specific to this report; see [library metric definitions](../../../docs/METRICS.md)
for the legacy summary formulas. The fold Sharpe uses the per-bar equity
returns, with forced-exit cost included on the final real bar, `ddof=1`, zero
risk-free rate, and `sqrt(test_size)` scaling. It is not annualized.

## Reproduce

From the repository root, with the development environment installed:

```bash
source venv/bin/activate
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
python examples/ml_walk_forward.py \
  --datafile examples/research/btc_usd_2025_q1/input.parquet \
  --freq 1h --train-size 400 --test-size 100 --step-size 100 \
  --horizon 5 --threshold 0.01 --comission 0.1 \
  --random-state 42 --signal-lag 1 \
  --out-dir ft_archive/research/btc_usd_2025_q1_reproduced
```

Choose a new output directory for every run. The example writes the input
snapshot, a YAML settings file, the fold CSV and a YAML report with dataset
SHA-256 and Python/library versions. `report.yml` records the environment used
here; use those versions for the closest reproduction. The source path in that
report identifies the archive used when creating the snapshot; the command
above needs only the committed snapshot, with no network calls.

Any strategy selected or tuned after inspecting these results needs a new,
untouched period for evaluation. A future benchmark should also test realistic
execution costs and additional periods and assets before drawing conclusions.
