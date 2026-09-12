# ML walk-forward search funnel

This is the research path for judging classifier configs **before** trusting `ml_signal`. It is scaffolding, not a strategy.

## The 7 problems (sub-agent tickets)

| ID | Problem | Owner module | Done when |
|---|---|---|---|
| P1 | Define a trial config | `fast_trade/ml/search_config.py` | YAML space expands to `TrialConfig` rows |
| P2 | Freeze search vs holdout dates | `search_config.DataSplit` | Holdout starts after search; slices never overlap |
| P3 | Keep runs cheap and comparable | `examples/ml_search.yml` screen baselines | Same fees/windows; `--limit` dry run |
| P4 | Screen, don't crown | `search_batch.rank_trials` | Ranked CSV + `composite_score` |
| P5 | Don't overfit the search | `confirm_holdout` + `must_beat` | Top N only see holdout |
| P6 | Persist everything | `ft_archive/ml_search/<name>/` | spec, ranking, per-trial config/summary/folds |
| P7 | Parallelize configs | `run_trials(..., workers=N)` | Process pool, one config per process |

## How to run

```bash
# Dry run (20 configs, synthetic split remapped onto generated data)
python examples/ml_walk_forward_batch.py --synthetic --limit 8 --workers 2

# Archive data using the locked dates in the spec
python examples/ml_walk_forward_batch.py --spec examples/ml_search.yml --limit 20
```

Do not jump to 1k trials until a 20-run table looks trustworthy.

## Funnel

```text
expand space → screen (cheap baselines)
            → promote top N (full baselines)
            → confirm top few on locked holdout
            → pass only if must_beat + min_trades
```

## Related

- `fast_trade/ml/walk_forward.py` — fold engine + `evaluate_fixed_split` for holdout
- `fast_trade/ml/classifier.py` — single-split demo
- `examples/ml_search.yml` — frozen contract
