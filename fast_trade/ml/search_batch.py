"""Bounded search, promotion and optional fixed-holdout evaluation."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field, replace
import hashlib
from importlib.metadata import version
import multiprocessing
from pathlib import Path
import platform
from typing import Any, Sequence

import numpy as np
import polars as pl
from threadpoolctl import threadpool_limits
import yaml

from fast_trade.ml.search_config import (
    SearchSpace, SearchSpec, TrialConfig, expand_trials, slice_holdout_df, slice_search_df,
)
from fast_trade.ml.walk_forward import (
    FoldMetrics, WalkForwardReport, build_feature_matrix, evaluate_fixed_split, report_to_frame, walk_forward_evaluate,
)


@dataclass
class TrialResult:
    trial: TrialConfig
    status: str
    row: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    folds_path: str | None = None
    summary_path: str | None = None
    report: WalkForwardReport | None = None


def composite_score(row: dict[str, Any]) -> float:
    """Exploratory rank heuristic; not a significance test or profit forecast."""
    return sum(float(row.get(key) or 0.0) for key in (
        "pct_folds_beat_buy_hold", "pct_folds_beat_rsi", "median_ml_return_perc",
    ))


def trial_row(trial: TrialConfig, report: WalkForwardReport) -> dict[str, Any]:
    row = {**trial.to_dict(), "status": "ok", **report.aggregate}
    row["composite_score"] = composite_score(row)
    return row


def holdout_row(trial: TrialConfig, metrics: FoldMetrics) -> dict[str, Any]:
    row = {
        **trial.to_dict(), "status": "ok", "test_size": metrics.test_rows, "n_folds": 1,
        "median_ml_return_perc": metrics.ml_return_perc, "mean_ml_return_perc": metrics.ml_return_perc,
        "median_test_roc_auc": metrics.test_roc_auc, "total_ml_trades": metrics.ml_num_trades,
    }
    for name in ("buy_hold", "rsi", "random"):
        beaten = getattr(metrics, f"beats_{name}")
        row[f"median_{name}_return_perc"] = getattr(metrics, f"{name}_return_perc")
        row[f"beats_{name}"] = beaten
        row[f"pct_folds_beat_{name}"] = float(beaten) * 100 if beaten is not None else None
    row["composite_score"] = composite_score(row)
    return row


def _table(rows: Sequence[dict[str, Any]]) -> pl.DataFrame:
    # Nested config values are saved in YAML, not CSV cells.
    return pl.DataFrame([{k: v for k, v in row.items() if k != "baselines"} for row in rows], infer_schema_length=None)


def rank_trials(rows: Sequence[dict[str, Any]], *, min_trades: int = 0) -> pl.DataFrame:
    frame = _table(rows)
    if frame.is_empty():
        return frame
    return frame.filter(
        (pl.col("status") == "ok") & (pl.col("total_ml_trades").fill_null(0) >= min_trades)
        & pl.col("composite_score").is_finite()
    ).sort(["composite_score", "median_ml_return_perc", "total_ml_trades", "trial_id"],
           descending=[True, True, True, False])


def promote_trials(ranked: pl.DataFrame, *, top_n: int) -> pl.DataFrame:
    return ranked.head(top_n)


def holdout_passes(row: dict[str, Any], must_beat: Sequence[str], min_trades: int) -> bool:
    if set(must_beat) - {"buy_hold", "rsi", "random"}:
        raise ValueError("Unknown holdout comparator")
    return (row.get("status") == "ok" and int(row.get("total_ml_trades") or 0) >= min_trades
            and all(row.get(f"beats_{name}") is True for name in must_beat))


def _write_yaml(path: Path, value: Any) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def persist_trial(run_dir: Path, result: TrialResult) -> TrialResult:
    trial_dir = run_dir / "trials" / result.trial.stage / result.trial.trial_id
    trial_dir.mkdir(parents=True, exist_ok=False)
    _write_yaml(trial_dir / "config.yml", result.trial.to_dict())
    summary_path = trial_dir / "summary.yml"
    _write_yaml(summary_path, {"status": result.status, "error": result.error, "row": result.row})
    result.summary_path = str(summary_path)
    if result.report is not None:
        folds_path = trial_dir / "folds.csv"
        report_to_frame(result.report).write_csv(folds_path)
        _write_yaml(trial_dir / "report.yml", asdict(result.report))
        result.folds_path = str(folds_path)
    return result


def write_table(path: Path, frame: pl.DataFrame) -> None:
    frame.write_csv(path)


def _failure(trial: TrialConfig, error: Exception) -> TrialResult:
    message = f"{type(error).__name__}: {error}"
    return TrialResult(trial, "failed", {
        "trial_id": trial.trial_id, "stage": trial.stage, "status": "failed", "error": message,
        "composite_score": float("-inf"), "total_ml_trades": 0, "median_ml_return_perc": None,
    }, error=message)


def execute_trial(df: pl.DataFrame, trial: TrialConfig, test_start_row: int | None = None) -> TrialResult:
    try:
        with threadpool_limits(limits=1):
            report = walk_forward_evaluate(df, test_start_row=test_start_row, **trial.walk_forward_kwargs())
        return TrialResult(trial, "ok", trial_row(trial, report), report=report)
    except Exception as exc:
        # A bad trial is recorded and excluded; the remaining trials still run.
        return _failure(trial, exc)


def _common_test_start(df: pl.DataFrame, trials: Sequence[TrialConfig], space: SearchSpace | None = None) -> int:
    warmups = []
    modes = ({(t.use_ta, t.include_basic) for t in trials} if space is None else
             {(ta, basic) for ta in space.use_ta for basic in space.include_basic if ta or basic})
    for ta, basic in sorted(modes):
        features, cols = build_feature_matrix(df, use_ta=ta, include_basic=basic)
        valid = features.select(pl.all_horizontal(pl.col(c).is_finite() for c in cols)).to_series().fill_null(False)
        positions = np.flatnonzero(valid.to_numpy())
        if len(positions):
            warmups.append(int(positions[0]))
    largest_train = max(t.train_size for t in trials) if space is None else max(space.train_sizes)
    return max(warmups, default=20) + largest_train


def _execute_trial_payload(payload) -> TrialResult:
    return execute_trial(*payload)


def run_trials(df: pl.DataFrame, trials: Sequence[TrialConfig], *, run_dir: Path, workers: int = 1,
               test_start_row: int | None = None) -> list[TrialResult]:
    if type(workers) is not int or workers < 1 or not trials:
        raise ValueError("Positive workers and nonempty trials are required")
    df = df.sort("date")
    start = _common_test_start(df, trials) if test_start_row is None else test_start_row
    payloads = [(df, trial, start) for trial in trials]
    if workers == 1:
        results = [_execute_trial_payload(payload) for payload in payloads]
    else:
        # Polars and OpenMP must not inherit a forked parent's live thread pools.
        with ProcessPoolExecutor(max_workers=min(workers, len(trials)),
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            results = list(pool.map(_execute_trial_payload, payloads))
    return [persist_trial(run_dir, result) for result in sorted(results, key=lambda item: item.trial.trial_id)]


def confirm_holdout(search_df: pl.DataFrame, holdout_df: pl.DataFrame, trial: TrialConfig,
                    *, baselines: Sequence[str]) -> TrialResult:
    holdout_trial = replace(trial, stage="holdout", baselines=tuple(baselines))
    try:
        search_df, holdout_df = search_df.sort("date"), holdout_df.sort("date")
        if search_df.height < trial.train_size:
            raise ValueError("Search data does not contain the full configured training window")
        options = trial.walk_forward_kwargs()
        for key in ("train_size", "test_size", "step_size"):
            options.pop(key)
        options["baselines"] = tuple(baselines)
        with threadpool_limits(limits=1):
            metrics = evaluate_fixed_split(
                pl.concat([search_df, holdout_df]),
                search_df.tail(trial.train_size)["date"], holdout_df["date"], **options,
            )
        _, cols = build_feature_matrix(search_df, use_ta=trial.use_ta, include_basic=trial.include_basic)
        report = WalkForwardReport(
            [metrics], cols, trial.horizon, trial.threshold, trial.train_size, holdout_df.height, holdout_df.height,
            {}, {"fixed_holdout": True, "refit_on_holdout": False, "signal_lag": trial.signal_lag,
                 "comission": trial.comission, "base_balance": trial.base_balance},
        )
        return TrialResult(holdout_trial, "ok", holdout_row(holdout_trial, metrics), report=report)
    except Exception as exc:
        return _failure(holdout_trial, exc)


def run_search(df: pl.DataFrame, spec: SearchSpec, *, run_dir: Path | None = None, limit: int | None = 20,
               workers: int = 1, promote: bool = True, confirm: bool = False) -> dict[str, Any]:
    """Freeze the contract, rank on search data, then optionally score a holdout.

    The default limit is 20 trials; confirmation is explicit. Existing output
    directories are rejected. Selection is saved before any holdout model fit.
    All configurations share the same first test bar and subsequent test dates.
    """
    spec.validate()
    screen_trials = expand_trials(spec, limit=limit)
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    search_df = slice_search_df(df, spec)
    holdout_df = slice_holdout_df(df, spec) if confirm else None
    # The full contract fixes dates even for a smaller --limit smoke run.
    anchor = _common_test_start(search_df, screen_trials, spec.space)
    out = Path(run_dir) if run_dir is not None else Path(spec.output_dir) / spec.name
    out.mkdir(parents=True, exist_ok=False)
    _write_yaml(out / "spec.yml", spec.to_dict())
    hashes = {}
    for name, snapshot in (("search", search_df), ("holdout", holdout_df)):
        if snapshot is not None:
            path = out / f"{name}.parquet"
            snapshot.write_parquet(path)
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_yaml(out / "run.yml", {
        "limit": limit, "workers": workers, "promote": promote, "confirm": confirm,
        "search_rows": search_df.height, "test_start_row": anchor, "input_sha256": hashes,
        "environment": {"python": platform.python_version(),
                        **{name: version(name) for name in ("fast-trade", "polars", "numpy", "scikit-learn")}},
    })
    screen_results = run_trials(search_df, screen_trials, run_dir=out, workers=workers, test_start_row=anchor)
    screen_ranked = rank_trials([item.row for item in screen_results], min_trades=spec.screen.min_trades)
    write_table(out / "ranking.csv", screen_ranked)
    promoted = (promote_trials(screen_ranked, top_n=min(spec.screen.top_n, spec.promote.top_n))
                if promote else pl.DataFrame())
    write_table(out / "promoted.csv", promoted)
    by_id = {trial.trial_id: trial for trial in screen_trials}
    promote_results = []
    promote_ranked = pl.DataFrame()
    if not promoted.is_empty():
        configs = [replace(by_id[value], stage="promote", baselines=spec.promote.baselines)
                   for value in promoted["trial_id"]]
        promote_results = run_trials(search_df, configs, run_dir=out, workers=workers, test_start_row=anchor)
        promote_ranked = rank_trials([item.row for item in promote_results], min_trades=spec.promote.min_trades)
    write_table(out / "promoted_full.csv", promote_ranked)
    source = promote_ranked if promote else screen_ranked.head(spec.screen.top_n)
    selected = [] if source.is_empty() else source["trial_id"].head(spec.holdout.top_n).to_list()
    _write_yaml(out / "selection.yml", {"trial_ids": selected, "basis": "search data only", "confirm": confirm})
    holdout_results = []
    if confirm:
        for value in selected:
            result = confirm_holdout(search_df, holdout_df, by_id[value], baselines=spec.holdout.baselines)
            result.row["passed"] = holdout_passes(result.row, spec.holdout.must_beat, spec.holdout.min_trades)
            persist_trial(out, result)
            holdout_results.append(result)
    confirmed = _table([item.row for item in holdout_results])
    write_table(out / "holdout.csv", confirmed)
    return {
        "run_dir": str(out), "search_rows": search_df.height, "screen": screen_results,
        "screen_ranked": screen_ranked, "promoted": promoted, "promote_results": promote_results,
        "promote_ranked": promote_ranked, "holdout_results": holdout_results, "holdout": confirmed,
    }
