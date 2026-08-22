"""Train a simple return classifier and wire its signal into a backtest.

Pattern:
  OHLCV → features → forward-return labels → sklearn classifier → ``ml_signal``
  → existing enter/exit engine via the ``column`` datapoint transformer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from fast_trade.run_backtest import run_backtest


DEFAULT_FEATURE_COLUMNS = (
    "ret_1",
    "ret_5",
    "ret_10",
    "vol_20",
    "range_pct",
    "sma_ratio",
    "volume_z",
)


@dataclass
class ClassifierFitResult:
    model: Any
    feature_columns: List[str]
    train_rows: int
    test_rows: int
    train_accuracy: float
    test_accuracy: float
    test_roc_auc: Optional[float]
    label_horizon: int
    label_threshold: float


@dataclass
class ClassifierBacktestResult:
    summary: Dict[str, Any]
    df: pd.DataFrame
    trade_df: pd.DataFrame
    fit: ClassifierFitResult
    strategy: Dict[str, Any]
    extras: Dict[str, Any] = field(default_factory=dict)


def build_classifier_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build a small tabular feature set from OHLCV columns."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataframe missing required columns: {sorted(missing)}")

    out = pd.DataFrame(index=df.index)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_10"] = close.pct_change(10)
    out["vol_20"] = out["ret_1"].rolling(20).std()
    out["range_pct"] = (high - low) / close.replace(0, np.nan)
    sma_20 = close.rolling(20).mean()
    out["sma_ratio"] = close / sma_20 - 1.0
    vol_mean = volume.rolling(20).mean()
    vol_std = volume.rolling(20).std()
    out["volume_z"] = (volume - vol_mean) / vol_std.replace(0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan)


def label_forward_return(
    close: pd.Series,
    horizon: int = 5,
    threshold: float = 0.01,
) -> pd.Series:
    """Label 1 when forward return over ``horizon`` bars exceeds ``threshold``."""
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    forward = close.shift(-horizon) / close - 1.0
    labels = (forward > threshold).astype("float")
    labels[forward.isna()] = np.nan
    return labels


def _time_split_index(index: pd.Index, train_frac: float) -> Tuple[pd.Index, pd.Index]:
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be between 0 and 1")
    if len(index) < 40:
        raise ValueError("Need at least 40 rows with valid features/labels")
    cut = int(len(index) * train_frac)
    cut = max(20, min(cut, len(index) - 10))
    return index[:cut], index[cut:]


def fit_return_classifier(
    df: pd.DataFrame,
    *,
    horizon: int = 5,
    threshold: float = 0.01,
    train_frac: float = 0.7,
    feature_columns: Optional[Sequence[str]] = None,
    random_state: int = 42,
) -> Tuple[ClassifierFitResult, pd.DataFrame, pd.Series]:
    """Fit a classifier on time-ordered features/labels.

    Returns the fit result plus aligned feature matrix and labels for the full
    usable index (train + test rows with no NaNs).
    """
    features = build_classifier_features(df)
    labels = label_forward_return(df["close"], horizon=horizon, threshold=threshold)
    cols = list(feature_columns or DEFAULT_FEATURE_COLUMNS)
    missing = [c for c in cols if c not in features.columns]
    if missing:
        raise ValueError(f"Unknown feature columns: {missing}")

    frame = features[cols].copy()
    frame["y"] = labels
    usable = frame.dropna()
    if usable.empty:
        raise ValueError("No usable rows after dropping NaN features/labels")

    train_idx, test_idx = _time_split_index(usable.index, train_frac)
    x_train = usable.loc[train_idx, cols]
    y_train = usable.loc[train_idx, "y"].astype(int)
    x_test = usable.loc[test_idx, cols]
    y_test = usable.loc[test_idx, "y"].astype(int)

    if y_train.nunique() < 2:
        raise ValueError("Training labels must include both classes; loosen threshold")

    model = HistGradientBoostingClassifier(random_state=random_state)
    model.fit(x_train, y_train)

    train_pred = model.predict(x_train)
    test_pred = model.predict(x_test)
    test_proba = None
    test_auc: Optional[float] = None
    if hasattr(model, "predict_proba") and y_test.nunique() > 1:
        test_proba = model.predict_proba(x_test)[:, 1]
        test_auc = float(roc_auc_score(y_test, test_proba))

    fit = ClassifierFitResult(
        model=model,
        feature_columns=cols,
        train_rows=len(train_idx),
        test_rows=len(test_idx),
        train_accuracy=float(accuracy_score(y_train, train_pred)),
        test_accuracy=float(accuracy_score(y_test, test_pred)),
        test_roc_auc=test_auc,
        label_horizon=horizon,
        label_threshold=threshold,
    )
    return fit, usable[cols], usable["y"].astype(int)


def predict_ml_signal(
    model: Any,
    features: pd.DataFrame,
    feature_columns: Sequence[str],
) -> pd.Series:
    """Return a 0/1 signal series aligned to ``features`` index."""
    cols = list(feature_columns)
    x = features[cols]
    pred = model.predict(x)
    return pd.Series(pred.astype(int), index=features.index, name="ml_signal")


def ml_signal_datapoint(column: str = "ml_signal") -> Dict[str, Any]:
    """Datapoint that exposes a precomputed column to enter/exit logic."""
    return {"name": column, "transformer": "column", "args": [column]}


def default_classifier_strategy(
    *,
    symbol: str = "BTCUSDT",
    exchange: str = "binanceus",
    freq: str = "1H",
    signal_column: str = "ml_signal",
    comission: float = 0.01,
    **overrides: Any,
) -> Dict[str, Any]:
    """YAML-shaped strategy that enters when the classifier predicts 1."""
    strategy: Dict[str, Any] = {
        "name": "ml_classifier_example",
        "symbol": symbol,
        "exchange": exchange,
        "freq": freq,
        "comission": comission,
        "any_enter": [],
        "any_exit": [],
        "datapoints": [ml_signal_datapoint(signal_column)],
        "enter": [[signal_column, "=", 1]],
        "exit": [[signal_column, "=", 0]],
        "exit_on_end": True,
        "base_balance": 1000,
        "lot_size": 1,
        # Required by validate_backtest; None means "use the provided dataframe as-is".
        "start": None,
        "stop": None,
    }
    strategy.update(overrides)
    return strategy


def attach_ml_signal(
    df: pd.DataFrame,
    signal: pd.Series,
    column: str = "ml_signal",
) -> pd.DataFrame:
    """Copy OHLCV frame and attach a classifier signal column."""
    out = df.copy()
    out[column] = signal.reindex(out.index)
    # Holding flat when the model has no prediction keeps the sim deterministic.
    out[column] = out[column].fillna(0).astype(int)
    return out


def run_classifier_backtest(
    df: pd.DataFrame,
    *,
    horizon: int = 5,
    threshold: float = 0.01,
    train_frac: float = 0.7,
    feature_columns: Optional[Sequence[str]] = None,
    random_state: int = 42,
    backtest_on: str = "test",
    strategy: Optional[Mapping[str, Any]] = None,
    strategy_overrides: Optional[Mapping[str, Any]] = None,
) -> ClassifierBacktestResult:
    """Fit a classifier, attach ``ml_signal``, and run ``run_backtest``.

    Parameters
    ----------
    backtest_on:
        ``test`` (default) backtests only the holdout window;
        ``all`` scores the whole usable history (leaky; for demos only).
    """
    if backtest_on not in {"test", "all"}:
        raise ValueError("backtest_on must be 'test' or 'all'")

    fit, features, _labels = fit_return_classifier(
        df,
        horizon=horizon,
        threshold=threshold,
        train_frac=train_frac,
        feature_columns=feature_columns,
        random_state=random_state,
    )
    signal = predict_ml_signal(fit.model, features, fit.feature_columns)
    signaled = attach_ml_signal(df.reindex(features.index), signal)

    train_idx, test_idx = _time_split_index(features.index, train_frac)
    if backtest_on == "test":
        backtest_df = signaled.loc[test_idx]
    else:
        backtest_df = signaled

    strat = default_classifier_strategy()
    if strategy:
        strat.update(dict(strategy))
    if strategy_overrides:
        strat.update(dict(strategy_overrides))

    # Avoid re-slicing away the already-chosen window inside prepare_df.
    # ``start`` must still be present for validate_backtest.
    strat["start"] = None
    strat["stop"] = None
    strat.pop("chart_start", None)
    strat.pop("chart_stop", None)

    result = run_backtest(strat, df=backtest_df)
    return ClassifierBacktestResult(
        summary=result["summary"],
        df=result["df"],
        trade_df=result["trade_df"],
        fit=fit,
        strategy=result["backtest"],
        extras={
            "backtest_on": backtest_on,
            "train_start": str(train_idx[0]),
            "train_end": str(train_idx[-1]),
            "test_start": str(test_idx[0]),
            "test_end": str(test_idx[-1]),
        },
    )
