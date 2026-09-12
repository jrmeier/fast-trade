"""Walk-forward evaluation for classifier signals vs simple baselines.

Trains only on each fold's train window, predicts ``ml_signal`` on the test
window, backtests that holdout, and compares against buy-and-hold, RSI, and
random-entry baselines on the same OOS bars.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from fast_trade.build_data_frame import apply_transformers_to_dataframe
from fast_trade.ml.classifier import (
    attach_ml_signal,
    build_classifier_features,
    default_classifier_strategy,
    label_forward_return,
    predict_ml_signal,
)
from fast_trade.run_backtest import run_backtest


DEFAULT_TA_DATAPOINTS: List[Dict[str, Any]] = [
    {"name": "rsi", "transformer": "rsi", "args": [14]},
    {"name": "ema_fast", "transformer": "ema", "args": [12]},
    {"name": "ema_slow", "transformer": "ema", "args": [26]},
    {"name": "atr", "transformer": "atr", "args": [14]},
]


@dataclass(frozen=True)
class FoldWindow:
    fold: int
    train_index: pd.Index
    test_index: pd.Index

    @property
    def train_start(self) -> Any:
        return self.train_index[0]

    @property
    def train_end(self) -> Any:
        return self.train_index[-1]

    @property
    def test_start(self) -> Any:
        return self.test_index[0]

    @property
    def test_end(self) -> Any:
        return self.test_index[-1]


@dataclass
class FoldMetrics:
    fold: int
    train_rows: int
    test_rows: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    test_accuracy: Optional[float]
    test_roc_auc: Optional[float]
    ml_return_perc: float
    ml_num_trades: int
    ml_sharpe_ratio: float
    buy_hold_return_perc: float
    rsi_return_perc: float
    rsi_num_trades: int
    random_return_perc: float
    random_num_trades: int
    beats_buy_hold: bool
    beats_rsi: bool
    beats_random: bool


@dataclass
class WalkForwardReport:
    folds: List[FoldMetrics]
    feature_columns: List[str]
    label_horizon: int
    label_threshold: float
    train_size: int
    test_size: int
    step_size: int
    aggregate: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


def iter_rolling_folds(
    index: pd.Index,
    *,
    train_size: int,
    test_size: int,
    step_size: Optional[int] = None,
) -> List[FoldWindow]:
    """Build contiguous rolling train/test folds over ``index``."""
    if train_size < 20:
        raise ValueError("train_size must be >= 20")
    if test_size < 5:
        raise ValueError("test_size must be >= 5")
    step = step_size if step_size is not None else test_size
    if step < 1:
        raise ValueError("step_size must be >= 1")

    n = len(index)
    need = train_size + test_size
    if n < need:
        raise ValueError(f"Need at least {need} rows for one fold; got {n}")

    folds: List[FoldWindow] = []
    start = 0
    fold_i = 0
    while start + need <= n:
        train_idx = index[start:start + train_size]
        test_idx = index[start + train_size:start + need]
        folds.append(FoldWindow(fold=fold_i, train_index=train_idx, test_index=test_idx))
        fold_i += 1
        start += step
    return folds


def _numeric_feature_columns(df: pd.DataFrame, exclude: Iterable[str]) -> List[str]:
    skip = set(exclude)
    cols: List[str] = []
    for col in df.columns:
        if col in skip:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


def build_feature_matrix(
    df: pd.DataFrame,
    *,
    use_ta: bool = True,
    ta_datapoints: Optional[Sequence[Mapping[str, Any]]] = None,
    include_basic: bool = True,
    feature_columns: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Build the feature matrix used across all walk-forward folds.

    Indicators are computed once on the full frame (rolling TA is causal).
    Labels still must be sliced so the horizon does not cross into the test
    window during training.
    """
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataframe missing required columns: {sorted(missing)}")

    parts: List[pd.DataFrame] = []
    if include_basic:
        parts.append(build_classifier_features(df))

    if use_ta:
        dps = [dict(dp) for dp in (ta_datapoints or DEFAULT_TA_DATAPOINTS)]
        ohlcv = df[["open", "high", "low", "close", "volume"]].copy()
        ta_df = apply_transformers_to_dataframe(ohlcv, dps)
        # Drop raw OHLCV duplicates; keep only transformer outputs.
        ta_only = ta_df.drop(columns=["open", "high", "low", "close", "volume"], errors="ignore")
        parts.append(ta_only)

    if not parts:
        raise ValueError("No features selected; enable include_basic and/or use_ta")

    features = pd.concat(parts, axis=1)
    features = features.loc[:, ~features.columns.duplicated()]
    features = features.replace([np.inf, -np.inf], np.nan)

    if feature_columns is not None:
        cols = list(feature_columns)
        missing_cols = [c for c in cols if c not in features.columns]
        if missing_cols:
            raise ValueError(f"Unknown feature columns: {missing_cols}")
    else:
        cols = _numeric_feature_columns(
            features, exclude={"open", "high", "low", "close", "volume", "y", "ml_signal"}
        )
        if not cols:
            raise ValueError("No numeric feature columns available")

    return features[cols], cols


def buy_hold_return_perc(close: pd.Series) -> float:
    if close.empty:
        return 0.0
    first = float(close.iloc[0])
    last = float(close.iloc[-1])
    if first == 0:
        return 0.0
    return float((last / first - 1.0) * 100.0)


def _strategy_for_signal(
    *,
    signal_column: str = "ml_signal",
    freq: str = "1h",
    comission: float = 0.01,
    **overrides: Any,
) -> Dict[str, Any]:
    strategy = default_classifier_strategy(
        freq=freq, signal_column=signal_column, comission=comission, **overrides
    )
    strategy["start"] = None
    strategy["stop"] = None
    return strategy


def _run_signal_backtest(
    ohlcv: pd.DataFrame,
    signal: pd.Series,
    *,
    freq: str,
    comission: float,
) -> Dict[str, Any]:
    frame = attach_ml_signal(ohlcv, signal, column="ml_signal")
    result = run_backtest(
        _strategy_for_signal(freq=freq, comission=comission),
        df=frame,
    )
    return result["summary"]


def _rsi_baseline_summary(
    ohlcv: pd.DataFrame,
    *,
    freq: str,
    comission: float,
) -> Dict[str, Any]:
    strategy = {
        "name": "rsi_baseline",
        "freq": freq,
        "comission": comission,
        "any_enter": [],
        "any_exit": [],
        "datapoints": [{"name": "rsi", "transformer": "rsi", "args": [14]}],
        "enter": [["rsi", "<", 30]],
        "exit": [["rsi", ">", 70]],
        "exit_on_end": True,
        "base_balance": 1000,
        "lot_size": 1,
        "start": None,
        "stop": None,
    }
    result = run_backtest(strategy, df=ohlcv.copy())
    return result["summary"]


def _random_signal(index: pd.Index, positive_rate: float, seed: int) -> pd.Series:
    rate = float(np.clip(positive_rate, 0.0, 1.0))
    rng = np.random.default_rng(seed)
    values = (rng.random(len(index)) < rate).astype(int)
    return pd.Series(values, index=index, name="ml_signal")


def _safe_auc(y_true: np.ndarray, y_score: np.ndarray) -> Optional[float]:
    if len(np.unique(y_true)) < 2:
        return None
    return float(roc_auc_score(y_true, y_score))


def _summary_metrics(summary: Mapping[str, Any]) -> Tuple[float, int, float]:
    return (
        float(summary.get("return_perc") or 0.0),
        int(summary.get("num_trades") or 0),
        float(summary.get("sharpe_ratio") or 0.0),
    )


def walk_forward_evaluate(
    df: pd.DataFrame,
    *,
    train_size: int = 400,
    test_size: int = 100,
    step_size: Optional[int] = None,
    horizon: int = 5,
    threshold: float = 0.01,
    use_ta: bool = True,
    ta_datapoints: Optional[Sequence[Mapping[str, Any]]] = None,
    include_basic: bool = True,
    feature_columns: Optional[Sequence[str]] = None,
    freq: str = "1h",
    comission: float = 0.01,
    random_state: int = 42,
    baselines: Sequence[str] = ("buy_hold", "rsi", "random"),
) -> WalkForwardReport:
    """Run rolling walk-forward evaluation with optional baselines.

    Parameters
    ----------
    train_size / test_size / step_size:
        Bar counts for rolling windows. ``step_size`` defaults to ``test_size``.
    horizon / threshold:
        Forward-return label: 1 when return over ``horizon`` bars > ``threshold``.
    use_ta:
        When True, append ``DEFAULT_TA_DATAPOINTS`` (or ``ta_datapoints``).
    baselines:
        Any of ``buy_hold``, ``rsi``, ``random``.
    """
    baseline_set = set(baselines)
    unknown = baseline_set - {"buy_hold", "rsi", "random"}
    if unknown:
        raise ValueError(f"Unknown baselines: {sorted(unknown)}")

    features, cols = build_feature_matrix(
        df,
        use_ta=use_ta,
        ta_datapoints=ta_datapoints,
        include_basic=include_basic,
        feature_columns=feature_columns,
    )
    labels = label_forward_return(df["close"], horizon=horizon, threshold=threshold)

    # Align to rows with complete features; labels may still be NaN near the end.
    usable_feat = features.dropna()
    if usable_feat.empty:
        raise ValueError("No usable feature rows after dropping NaNs")

    folds = iter_rolling_folds(
        usable_feat.index,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
    )

    fold_metrics: List[FoldMetrics] = []
    for window in folds:
        # Drop train rows whose label looks past the train boundary into test.
        train_label_ok = window.train_index[:-horizon] if horizon > 0 else window.train_index
        train_idx = train_label_ok.intersection(usable_feat.index)
        test_idx = window.test_index.intersection(usable_feat.index)

        y_train_full = labels.reindex(train_idx)
        train_mask = y_train_full.notna()
        train_idx = train_idx[train_mask.to_numpy()]
        if len(train_idx) < 20:
            raise ValueError(f"Fold {window.fold}: too few labeled train rows ({len(train_idx)})")

        x_train = usable_feat.loc[train_idx, cols]
        y_train = labels.loc[train_idx].astype(int)
        if y_train.nunique() < 2:
            raise ValueError(
                f"Fold {window.fold}: training labels must include both classes; loosen threshold"
            )

        x_test = usable_feat.loc[test_idx, cols]
        y_test = labels.reindex(test_idx)

        model = HistGradientBoostingClassifier(random_state=random_state + window.fold)
        model.fit(x_train, y_train)
        pred = predict_ml_signal(model, x_test, cols)

        test_acc: Optional[float] = None
        test_auc: Optional[float] = None
        labeled_test = y_test.dropna()
        if not labeled_test.empty:
            pred_labeled = pred.reindex(labeled_test.index)
            test_acc = float(accuracy_score(labeled_test.astype(int), pred_labeled))
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(usable_feat.loc[labeled_test.index, cols])[:, 1]
                test_auc = _safe_auc(labeled_test.astype(int).to_numpy(), proba)

        ohlcv_test = df.loc[test_idx, ["open", "high", "low", "close", "volume"]]
        ml_summary = _run_signal_backtest(
            ohlcv_test, pred, freq=freq, comission=comission
        )
        ml_ret, ml_trades, ml_sharpe = _summary_metrics(ml_summary)

        bh_ret = (
            buy_hold_return_perc(ohlcv_test["close"])
            if "buy_hold" in baseline_set
            else 0.0
        )

        if "rsi" in baseline_set:
            rsi_summary = _rsi_baseline_summary(
                ohlcv_test, freq=freq, comission=comission
            )
            rsi_ret, rsi_trades, _ = _summary_metrics(rsi_summary)
        else:
            rsi_ret, rsi_trades = 0.0, 0

        if "random" in baseline_set:
            pos_rate = float(pred.mean()) if len(pred) else 0.0
            rand_sig = _random_signal(test_idx, pos_rate, seed=random_state + 1000 + window.fold)
            rand_summary = _run_signal_backtest(
                ohlcv_test, rand_sig, freq=freq, comission=comission
            )
            rand_ret, rand_trades, _ = _summary_metrics(rand_summary)
        else:
            rand_ret, rand_trades = 0.0, 0

        fold_metrics.append(
            FoldMetrics(
                fold=window.fold,
                train_rows=len(train_idx),
                test_rows=len(test_idx),
                train_start=str(window.train_start),
                train_end=str(window.train_end),
                test_start=str(window.test_start),
                test_end=str(window.test_end),
                test_accuracy=test_acc,
                test_roc_auc=test_auc,
                ml_return_perc=ml_ret,
                ml_num_trades=ml_trades,
                ml_sharpe_ratio=ml_sharpe,
                buy_hold_return_perc=bh_ret,
                rsi_return_perc=rsi_ret,
                rsi_num_trades=rsi_trades,
                random_return_perc=rand_ret,
                random_num_trades=rand_trades,
                beats_buy_hold=ml_ret > bh_ret,
                beats_rsi=ml_ret > rsi_ret,
                beats_random=ml_ret > rand_ret,
            )
        )

    ml_returns = [f.ml_return_perc for f in fold_metrics]
    aucs = [f.test_roc_auc for f in fold_metrics if f.test_roc_auc is not None]
    aggregate = {
        "n_folds": len(fold_metrics),
        "median_ml_return_perc": float(np.median(ml_returns)) if ml_returns else 0.0,
        "mean_ml_return_perc": float(np.mean(ml_returns)) if ml_returns else 0.0,
        "median_buy_hold_return_perc": float(
            np.median([f.buy_hold_return_perc for f in fold_metrics])
        ),
        "median_rsi_return_perc": float(np.median([f.rsi_return_perc for f in fold_metrics])),
        "median_random_return_perc": float(
            np.median([f.random_return_perc for f in fold_metrics])
        ),
        "median_test_roc_auc": float(np.median(aucs)) if aucs else None,
        "pct_folds_beat_buy_hold": float(
            np.mean([f.beats_buy_hold for f in fold_metrics]) * 100.0
        ),
        "pct_folds_beat_rsi": float(np.mean([f.beats_rsi for f in fold_metrics]) * 100.0),
        "pct_folds_beat_random": float(
            np.mean([f.beats_random for f in fold_metrics]) * 100.0
        ),
        "total_ml_trades": int(sum(f.ml_num_trades for f in fold_metrics)),
    }

    return WalkForwardReport(
        folds=fold_metrics,
        feature_columns=cols,
        label_horizon=horizon,
        label_threshold=threshold,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size if step_size is not None else test_size,
        aggregate=aggregate,
        extras={"baselines": sorted(baseline_set), "freq": freq, "comission": comission},
    )


def report_to_frame(report: WalkForwardReport) -> pd.DataFrame:
    """Convert fold metrics to a flat DataFrame for printing or CSV."""
    rows = []
    for f in report.folds:
        rows.append(
            {
                "fold": f.fold,
                "test_start": f.test_start,
                "test_end": f.test_end,
                "test_rows": f.test_rows,
                "test_accuracy": f.test_accuracy,
                "test_roc_auc": f.test_roc_auc,
                "ml_return_perc": f.ml_return_perc,
                "ml_num_trades": f.ml_num_trades,
                "buy_hold_return_perc": f.buy_hold_return_perc,
                "rsi_return_perc": f.rsi_return_perc,
                "random_return_perc": f.random_return_perc,
                "beats_buy_hold": f.beats_buy_hold,
                "beats_rsi": f.beats_rsi,
                "beats_random": f.beats_random,
            }
        )
    return pd.DataFrame(rows)
