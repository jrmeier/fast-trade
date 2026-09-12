"""Batch walk-forward search: persist, rank, promote, confirm holdout.

Problems 3–7: cheap comparable runs, screen/promote, locked holdout,
on-disk artifacts, and process-pool fan-out.
"""

from __future__ import annotations

import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import yaml

from fast_trade.ml.search_config import (
    SearchSpec,
    TrialConfig,
    expand_trials,
    slice_holdout_df,
    slice_search_df,
)
from fast_trade.ml.walk_forward import (
    FoldMetrics,
    WalkForwardReport,
    evaluate_fixed_split,
    report_to_frame,
    walk_forward_evaluate,
)


@dataclass
class TrialResult:
    trial: TrialConfig
    status: str
    row: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    folds_path: Optional[str] = None
    summary_path: Optional[str] = None
    report: Any = None


def composite_score(row: Dict[str, Any]) -> float:
    """Rank key: stability first, then median OOS return (Problem 4)."""
    beat_bh = float(row.get("pct_folds_beat_buy_hold") or 0.0)
    beat_rsi = float(row.get("pct_folds_beat_rsi") or 0.0)
    median_ret = float(row.get("median_ml_return_perc") or 0.0)
    return beat_bh + beat_rsi + median_ret


def trial_row(trial: TrialConfig, report: WalkForwardReport) -> Dict[str, Any]:
    agg = dict(report.aggregate)
    row = {
        "trial_id": trial.trial_id,
        "stage": trial.stage,
        "status": "ok",
        "horizon": trial.horizon,
        "threshold": trial.threshold,
        "train_size": trial.train_size,
        "test_size": trial.test_size,
        "use_ta": trial.use_ta,
        "include_basic": trial.include_basic,
        "freq": trial.freq,
        **agg,
        "composite_score": 0.0,
    }
    row["composite_score"] = composite_score(row)
    return row


def holdout_row(trial: TrialConfig, metrics: FoldMetrics) -> Dict[str, Any]:
    row = {
        "trial_id": trial.trial_id,
        "stage": "holdout",
        "status": "ok",
        "horizon": trial.horizon,
        "threshold": trial.threshold,
        "train_size": trial.train_size,
        "test_size": metrics.test_rows,
        "use_ta": trial.use_ta,
        "include_basic": trial.include_basic,
        "freq": trial.freq,
        "n_folds": 1,
        "median_ml_return_perc": metrics.ml_return_perc,
        "mean_ml_return_perc": metrics.ml_return_perc,
        "median_buy_hold_return_perc": metrics.buy_hold_return_perc,
        "median_rsi_return_perc": metrics.rsi_return_perc,
        "median_random_return_perc": metrics.random_return_perc,
        "median_test_roc_auc": metrics.test_roc_auc,
        "pct_folds_beat_buy_hold": 100.0 if metrics.beats_buy_hold else 0.0,
        "pct_folds_beat_rsi": 100.0 if metrics.beats_rsi else 0.0,
        "pct_folds_beat_random": 100.0 if metrics.beats_random else 0.0,
        "total_ml_trades": metrics.ml_num_trades,
        "beats_buy_hold": metrics.beats_buy_hold,
        "beats_rsi": metrics.beats_rsi,
        "beats_random": metrics.beats_random,
        "composite_score": 0.0,
    }
    row["composite_score"] = composite_score(row)
    return row


def rank_trials(
    rows: Sequence[Dict[str, Any]],
    *,
    min_trades: int = 0,
) -> pd.DataFrame:
    """Filter thin trade counts, then sort by composite score (Problem 4)."""
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return frame
    ok = frame[frame["status"] == "ok"].copy() if "status" in frame.columns else frame.copy()
    if "total_ml_trades" in ok.columns:
        ok = ok[ok["total_ml_trades"].fillna(0) >= min_trades]
    if ok.empty:
        return ok
    ok = ok.sort_values(
        ["composite_score", "median_ml_return_perc", "total_ml_trades"],
        ascending=False,
    )
    return ok.reset_index(drop=True)


def promote_trials(
    ranked: pd.DataFrame,
    *,
    top_n: int,
) -> pd.DataFrame:
    if ranked.empty:
        return ranked
    return ranked.head(int(top_n)).reset_index(drop=True)


def holdout_passes(row: Dict[str, Any], must_beat: Sequence[str], min_trades: int) -> bool:
    if int(row.get("total_ml_trades") or 0) < min_trades:
        return False
    checks = {
        "buy_hold": bool(row.get("beats_buy_hold")),
        "rsi": bool(row.get("beats_rsi")),
        "random": bool(row.get("beats_random")),
    }
    return all(checks[name] for name in must_beat if name in checks)


def persist_trial(
    run_dir: Path,
    result: TrialResult,
    *,
    report: Optional[WalkForwardReport] = None,
) -> TrialResult:
    trial_dir = run_dir / "trials" / result.trial.trial_id
    trial_dir.mkdir(parents=True, exist_ok=True)
    config_path = trial_dir / "config.yml"
    with config_path.open("w") as fh:
        yaml.safe_dump(result.trial.to_dict(), fh, sort_keys=False)
    summary = {
        "status": result.status,
        "error": result.error,
        "row": result.row,
    }
    summary_path = trial_dir / "summary.yml"
    with summary_path.open("w") as fh:
        yaml.safe_dump(summary, fh, sort_keys=False)
    result.summary_path = str(summary_path)
    if report is not None:
        folds = report_to_frame(report)
        folds_path = trial_dir / "folds.csv"
        folds.to_csv(folds_path, index=False)
        result.folds_path = str(folds_path)
    return result


def write_table(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if frame.empty:
        frame.to_csv(path, index=False)
        return
    frame.to_csv(path, index=False)


def execute_trial(df: pd.DataFrame, trial: TrialConfig) -> TrialResult:
    try:
        report = walk_forward_evaluate(df, **trial.walk_forward_kwargs())
        row = trial_row(trial, report)
        return TrialResult(trial=trial, status="ok", row=row, report=report)
    except Exception as exc:  # noqa: BLE001 — batch must survive bad configs
        return TrialResult(
            trial=trial,
            status="failed",
            row={
                "trial_id": trial.trial_id,
                "stage": trial.stage,
                "status": "failed",
                "error": str(exc),
                "composite_score": float("-inf"),
                "total_ml_trades": 0,
                "median_ml_return_perc": 0.0,
            },
            error=f"{exc}\n{traceback.format_exc()}",
        )


def _execute_trial_payload(payload: Dict[str, Any]) -> TrialResult:
    df = payload["df"]
    raw = dict(payload["trial"])
    raw["baselines"] = tuple(raw.get("baselines") or ())
    trial = TrialConfig(**raw)
    return execute_trial(df, trial)


def run_trials(
    df: pd.DataFrame,
    trials: Sequence[TrialConfig],
    *,
    run_dir: Path,
    workers: int = 1,
) -> List[TrialResult]:
    run_dir.mkdir(parents=True, exist_ok=True)
    results: List[TrialResult] = []
    if workers <= 1:
        raw_results = [execute_trial(df, trial) for trial in trials]
    else:
        payloads = [{"df": df, "trial": trial.to_dict()} for trial in trials]
        raw_results = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_execute_trial_payload, payload) for payload in payloads]
            for fut in as_completed(futures):
                raw_results.append(fut.result())
        raw_results.sort(key=lambda item: item.trial.trial_id)

    for result in raw_results:
        persist_trial(run_dir, result, report=result.report)
        results.append(result)
    return results


def confirm_holdout(
    search_df: pd.DataFrame,
    holdout_df: pd.DataFrame,
    trial: TrialConfig,
    *,
    baselines: Sequence[str],
) -> TrialResult:
    combined = pd.concat([search_df, holdout_df]).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    holdout_trial = TrialConfig(
        **{
            **trial.to_dict(),
            "stage": "holdout",
            "baselines": tuple(baselines),
        }
    )
    try:
        metrics = evaluate_fixed_split(
            combined,
            search_df.index,
            holdout_df.index,
            horizon=trial.horizon,
            threshold=trial.threshold,
            use_ta=trial.use_ta,
            include_basic=trial.include_basic,
            freq=trial.freq,
            comission=trial.comission,
            random_state=trial.random_state,
            baselines=baselines,
        )
        return TrialResult(
            trial=holdout_trial,
            status="ok",
            row=holdout_row(holdout_trial, metrics),
        )
    except Exception as exc:  # noqa: BLE001
        return TrialResult(
            trial=holdout_trial,
            status="failed",
            row={
                "trial_id": trial.trial_id,
                "stage": "holdout",
                "status": "failed",
                "error": str(exc),
                "composite_score": float("-inf"),
                "total_ml_trades": 0,
            },
            error=f"{exc}\n{traceback.format_exc()}",
        )


def run_search(
    df: pd.DataFrame,
    spec: SearchSpec,
    *,
    run_dir: Optional[Path] = None,
    limit: Optional[int] = None,
    workers: int = 1,
    promote: bool = True,
    confirm: bool = True,
) -> Dict[str, Any]:
    """Screen → optional promote → optional holdout (Problems 3–7)."""
    spec.validate()
    out = Path(run_dir or Path(spec.output_dir) / spec.name)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "spec.yml").open("w") as fh:
        yaml.safe_dump(
            {
                "name": spec.name,
                "symbol": spec.symbol,
                "exchange": spec.exchange,
                "freq": spec.freq,
                "data": asdict(spec.data),
            },
            fh,
            sort_keys=False,
        )

    search_df = slice_search_df(df, spec)
    screen_trials = expand_trials(
        spec, limit=limit, stage="screen", baselines=spec.screen.baselines
    )
    screen_results = run_trials(search_df, screen_trials, run_dir=out, workers=workers)
    screen_rows = [item.row for item in screen_results]
    screen_ranked = rank_trials(screen_rows, min_trades=spec.screen.min_trades)
    write_table(out / "ranking.csv", screen_ranked)

    promoted = promote_trials(screen_ranked, top_n=spec.promote.top_n) if promote else pd.DataFrame()
    write_table(out / "promoted.csv", promoted)

    promote_results: List[TrialResult] = []
    if promote and not promoted.empty:
        promote_cfgs = []
        by_id = {t.trial_id: t for t in screen_trials}
        for trial_id in promoted["trial_id"].tolist():
            base = by_id[trial_id]
            promote_cfgs.append(
                TrialConfig(
                    **{
                        **base.to_dict(),
                        "stage": "promote",
                        "baselines": spec.promote.baselines,
                    }
                )
            )
        promote_results = run_trials(
            search_df, promote_cfgs, run_dir=out, workers=workers
        )
        promote_ranked = rank_trials(
            [item.row for item in promote_results],
            min_trades=spec.promote.min_trades,
        )
        write_table(out / "promoted_full.csv", promote_ranked)
        holdout_source = promote_ranked
    else:
        promote_ranked = pd.DataFrame()
        holdout_source = screen_ranked.head(spec.holdout.top_n)

    holdout_results: List[TrialResult] = []
    confirmed = pd.DataFrame()
    if confirm and spec.data.holdout_start and not holdout_source.empty:
        holdout_df = slice_holdout_df(df, spec)
        by_id = {t.trial_id: t for t in screen_trials}
        for trial_id in holdout_source["trial_id"].head(spec.holdout.top_n).tolist():
            result = confirm_holdout(
                search_df,
                holdout_df,
                by_id[trial_id],
                baselines=spec.holdout.baselines,
            )
            persist_trial(out, result)
            if result.status == "ok":
                result.row["passed"] = holdout_passes(
                    result.row,
                    spec.holdout.must_beat,
                    spec.holdout.min_trades,
                )
            holdout_results.append(result)
        confirmed = pd.DataFrame([item.row for item in holdout_results])
        write_table(out / "holdout.csv", confirmed)

    return {
        "run_dir": str(out),
        "search_rows": len(search_df),
        "screen": screen_results,
        "screen_ranked": screen_ranked,
        "promoted": promoted,
        "promote_results": promote_results,
        "promote_ranked": promote_ranked,
        "holdout_results": holdout_results,
        "holdout": confirmed,
    }
