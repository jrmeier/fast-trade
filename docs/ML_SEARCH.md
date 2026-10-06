# Bounded classifier search

Search a YAML grid on historical data, rank candidates, and optionally evaluate
a few selected settings on a separate fixed holdout. These are exploratory
research tools, not a profitable strategy or a statistical significance test.
The implementation uses Polars with an explicit `date` column.

## Run a small search

```bash
source venv/bin/activate
python examples/ml_walk_forward_batch.py --synthetic --limit 4 --workers 2 \
  --out ft_archive/ml_search/synthetic_demo

python examples/ml_walk_forward_batch.py --spec examples/ml_search.yml \
  --datafile examples/research/btc_usd_2025_q1/input.parquet --limit 4 \
  --out ft_archive/ml_search/btc_q1_search
```

The default cap is 20 screen trials. `--limit` controls screen fits; promotion
can add up to `min(screen.top_n, promote.top_n)` full-baseline trials. Library
callers can explicitly use `limit=None` for the full grid. `--workers N` uses
spawned processes, with bounded native math threads. `--no-promote` skips the
second search stage. No network download is performed: use a local Parquet or
download archive data first with `ft download`.

The example's 2025 Q1 data has already been examined in the committed benchmark.
It illustrates the workflow; it is not a new untouched holdout. Synthetic runs
remap the split before fitting and record `SYNTHETIC` / `synthetic` provenance.

## Freeze dates and comparison rules

`examples/ml_search.yml` defines prices, frequency, commission, seeds, signal
lag, starting cash, date ranges, grid dimensions and stage rules. YAML feature
flags must be real booleans, and empty lists, duplicate grid values, unknown
fields and invalid ranges are rejected. Loaded contracts are immutable.

- Date ranges are half-open: start inclusive, stop exclusive. Bounds are UTC;
  timezone-aware columns are supported. The search ends before holdout starts.
  If `search_stop` is omitted, it defaults to `holdout_start`.
- Each search uses one frequency and test-window size. Training sizes,
  horizons, label thresholds and feature families may vary. Every trial starts
  testing at the same bar, after the largest training window and feature
  warmup in the full spec. All subsequent test dates match, including when
  `--limit` evaluates only part of the grid.
- Promotion uses the same dates, model seeds and settings as screening; it
  adds the configured baselines. Every strategy has the same starting cash,
  signal delay, commission on both sides and final exit. Input must contain
  real, regular bars. Missing feature rows do not remove market bars.
- Training labels are purged at each boundary. RSI has preceding indicator
  history, and random exposure is calibrated from training labels only.
  Returns use initial cash and trade counts represent completed positions;
  see [METRICS.md](METRICS.md).

Ranking excludes failed trials and configurations below the stage's
`min_trades`. The fixed heuristic is the sum of the percentage of folds beating
buy-and-hold, the percentage beating RSI, and median net return in percentage
points. Unevaluated comparators contribute zero to the score. This heuristic
orders candidates within a stage; it is not a probability, expected return or
significance measure. Exact ties sort by trial ID. Random exposure is a sanity
baseline and does not contribute to this rank heuristic.

## Confirm only after selection

Confirmation is off by default. Reserve a new period before searching, then
explicitly add `--confirm-holdout` when ready to evaluate the selected settings.
The workflow writes `selection.yml` before any holdout model fit. It never
reranks candidates on holdout results.

Each selected configuration fits once on its last `train_size` raw search
bars, purging the final `horizon` rows. Earlier search data provides feature
warmup. It then scores the entire holdout with a frozen model, without refitting
on any holdout bar. Search and holdout must be adjacent and gap-free for this
confirmation path. A search/holdout gap fails confirmation instead of filling
invented bars or silently using extra training history.

`passed` requires the configured minimum completed trades and strict wins over
every `holdout.must_beat` comparator. Required comparators must actually be
evaluated. Failure records always fail the gate. Passing does not establish an
edge: multiple trials, limited periods, transaction assumptions and chance can
all produce apparent winners. Slippage, spreads and financing are not modeled.

Once holdout results influence a new strategy choice, that period has become
research data. Repeating confirmation in a new directory does not make it
untouched again. Reserve another period for subsequent evaluation.

## Saved evidence

Every run requires a new directory and writes:

- `spec.yml`: the complete contract, which `load_search_spec` can reload.
- `run.yml`: runtime flags, common test anchor, snapshot SHA-256 and versions.
- `search.parquet`; also `holdout.parquet` when confirmation is requested.
- `ranking.csv`, `promoted.csv`, `promoted_full.csv`, `selection.yml`,
  and `holdout.csv`. Empty stages produce empty tables.
- `trials/<stage>/<trial_id>/`: config and summary YAML; successful fits also
  save `folds.csv` and `report.yml`. Holdout summaries include `passed`.

Screen, promote and holdout artifacts have separate paths. Existing run and
trial directories are rejected, so stage records and earlier runs are preserved.
Failures retain their exception type/message and remain outside the ranking.

Library entrypoints are `load_search_spec`, `expand_trials`, `run_search`,
`run_trials` and `confirm_holdout`. The shared walk-forward module also exposes
`evaluate_fixed_split` for explicit adjacent date Series and `test_start_row`
for anchoring rolling tests. The [single-run benchmark](../examples/research/btc_usd_2025_q1/README.md)
documents execution assumptions and a reproducible historical result.
