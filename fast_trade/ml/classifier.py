"""Train a simple return classifier and wire its signal into a backtest.

Pattern:
  OHLCV → features → forward-return labels → sklearn classifier → ``ml_signal``
  → existing enter/exit engine via the ``column`` datapoint transformer.

Execution assumption
--------------------
Features use the bar's close (and other OHLCV fields). Enter/exit logic is
evaluated on that same bar, so fills are assumed at the close *after* the
close is known. Shift the signal forward one bar if you need next-open fills.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from fast_trade.build_data_frame import infer_frequency
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

# Sentinel: strategy dict omitted freq → infer from the dataframe.
_FREQ_UNSET = object()


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
    purged_train_rows: int = 0
    signal_threshold: float = 0.5


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


def _time_split_index(
    index: pd.Index,
    train_frac: float,
    *,
    purge_bars: int = 0,
) -> Tuple[pd.Index, pd.Index, int]:
    """Chronological train/test split with an optional purge gap.

    Forward-return labels at time ``t`` depend on prices through ``t + horizon``.
    Without a purge, the last ``horizon`` training labels leak into the holdout
    window. When ``purge_bars > 0``, those boundary rows are dropped from train
    (test is unchanged).
    """
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be between 0 and 1")
    if purge_bars < 0:
        raise ValueError("purge_bars must be >= 0")
    if len(index) < 40:
        raise ValueError("Need at least 40 rows with valid features/labels")
    cut = int(len(index) * train_frac)
    cut = max(20, min(cut, len(index) - 10))
    train_idx = index[:cut]
    test_idx = index[cut:]
    purged = 0
    if purge_bars > 0:
        if len(train_idx) <= purge_bars + 10:
            raise ValueError(
                "Not enough training rows after purge; "
                "lower horizon/train_frac or use more data"
            )
        purged = purge_bars
        train_idx = train_idx[:-purge_bars]
    return train_idx, test_idx, purged


def _canonical_freq_str(freq: Any) -> str:
    """Normalize freq to a validate_backtest-friendly string (e.g. ``h`` → ``1h``)."""
    if freq is not None and not isinstance(freq, str):
        freq = getattr(freq, "freqstr", None) or str(freq)
    s = str(freq).strip()
    if s and not s[0].isdigit():
        s = f"1{s}"
    return s


def _freqs_compatible(a: Any, b: Any) -> bool:
    """True when two pandas freq-like values represent the same offset.

    Handles aliases such as ``1h`` vs ``h`` / ``1H``.
    """
    try:
        from pandas.tseries.frequencies import to_offset

        return to_offset(a) == to_offset(b)
    except (ValueError, TypeError):
        return _canonical_freq_str(a).lower() == _canonical_freq_str(b).lower()


def resolve_backtest_freq(
    df: pd.DataFrame,
    strategy: Mapping[str, Any],
    *,
    allow_resample: bool = False,
) -> str:
    """Pick strategy freq from the frame when unset; guard silent resamples.

    Parameters
    ----------
    allow_resample:
        When False (default), raise if the strategy freq differs from the
        dataframe's native spacing. ``prepare_df`` resamples with ``.first()``,
        which silently regrids a precomputed ``ml_signal``.
    """
    inferred = infer_frequency(df)
    if inferred is not None:
        inferred = _canonical_freq_str(inferred)

    requested = strategy.get("freq", None)
    if requested is None or requested is _FREQ_UNSET:
        if not inferred:
            raise ValueError(
                "Could not infer dataframe frequency; pass strategy freq explicitly"
            )
        return inferred

    requested_str = _canonical_freq_str(requested)
    if (
        not allow_resample
        and inferred
        and not _freqs_compatible(requested_str, inferred)
    ):
        raise ValueError(
            f"Strategy freq {requested!r} does not match dataframe freq "
            f"{inferred!r}. Pass matching freq, or allow_resample=True if you "
            "intentionally want prepare_df to resample (ml_signal uses .first())."
        )
    return requested_str


def fit_return_classifier(
    df: pd.DataFrame,
    *,
    horizon: int = 5,
    threshold: float = 0.01,
    train_frac: float = 0.7,
    feature_columns: Optional[Sequence[str]] = None,
    random_state: int = 42,
    signal_threshold: float = 0.5,
) -> Tuple[ClassifierFitResult, pd.DataFrame, pd.Series]:
    """Fit a classifier on time-ordered features/labels.

    Returns the fit result plus aligned feature matrix and labels for the full
    usable index (train + test rows with no NaNs).

    Training rows whose forward-return label window overlaps the holdout are
    purged (embargo of ``horizon`` bars) so holdout metrics stay out-of-sample.
    """
    if not 0.0 < signal_threshold < 1.0:
        raise ValueError("signal_threshold must be between 0 and 1")

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

    train_idx, test_idx, purged = _time_split_index(
        usable.index, train_frac, purge_bars=horizon
    )
    x_train = usable.loc[train_idx, cols]
    y_train = usable.loc[train_idx, "y"].astype(int)
    x_test = usable.loc[test_idx, cols]
    y_test = usable.loc[test_idx, "y"].astype(int)

    if y_train.nunique() < 2:
        raise ValueError("Training labels must include both classes; loosen threshold")

    model = HistGradientBoostingClassifier(random_state=random_state)
    model.fit(x_train, y_train)

    train_pred = _predict_with_threshold(model, x_train, signal_threshold)
    test_pred = _predict_with_threshold(model, x_test, signal_threshold)
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
        purged_train_rows=purged,
        signal_threshold=signal_threshold,
    )
    return fit, usable[cols], usable["y"].astype(int)


def _predict_with_threshold(
    model: Any,
    x: pd.DataFrame,
    threshold: float,
) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(x)[:, 1]
        return (proba >= threshold).astype(int)
    return np.asarray(model.predict(x)).astype(int)


def predict_ml_signal(
    model: Any,
    features: pd.DataFrame,
    feature_columns: Sequence[str],
    *,
    threshold: float = 0.5,
) -> pd.Series:
    """Return a 0/1 signal series aligned to ``features`` index.

    Uses ``predict_proba`` when available and marks 1 when P(class=1) >=
    ``threshold`` (default 0.5). Falls back to ``predict`` otherwise.
    """
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    cols = list(feature_columns)
    x = features[cols]
    pred = _predict_with_threshold(model, x, threshold)
    return pd.Series(pred.astype(int), index=features.index, name="ml_signal")


def ml_signal_datapoint(column: str = "ml_signal") -> Dict[str, Any]:
    """Datapoint that exposes a precomputed column to enter/exit logic."""
    return {"name": column, "transformer": "column", "args": [column]}


def default_classifier_strategy(
    *,
    symbol: str = "BTCUSDT",
    exchange: str = "binanceus",
    freq: Union[str, None] = None,
    signal_column: str = "ml_signal",
    comission: float = 0.01,
    **overrides: Any,
) -> Dict[str, Any]:
    """YAML-shaped strategy that enters when the classifier predicts 1.

    ``freq`` defaults to ``None`` so ``run_classifier_backtest`` can infer it
    from the dataframe and avoid a silent resample mismatch.
    """
    strategy: Dict[str, Any] = {
        "name": "ml_classifier_example",
        "symbol": symbol,
        "exchange": exchange,
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
    if freq is not None:
        strategy["freq"] = freq
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
    signal_threshold: float = 0.5,
    backtest_on: str = "test",
    strategy: Optional[Mapping[str, Any]] = None,
    strategy_overrides: Optional[Mapping[str, Any]] = None,
    allow_resample: bool = False,
) -> ClassifierBacktestResult:
    """Fit a classifier, attach ``ml_signal``, and run ``run_backtest``.

    Parameters
    ----------
    backtest_on:
        ``test`` (default) backtests only the holdout window;
        ``all`` scores the whole usable history (leaky; for demos only).
    signal_threshold:
        Probability cutoff for class-1 when the model exposes
        ``predict_proba`` (default 0.5).
    allow_resample:
        Permit strategy ``freq`` to differ from the dataframe's native bar
        size. Default False — mismatched freq would silently regrid
        ``ml_signal`` via ``resample(...).first()``.
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
        signal_threshold=signal_threshold,
    )
    signal = predict_ml_signal(
        fit.model,
        features,
        fit.feature_columns,
        threshold=signal_threshold,
    )
    signaled = attach_ml_signal(df.reindex(features.index), signal)

    train_idx, test_idx, _purged = _time_split_index(
        features.index, train_frac, purge_bars=horizon
    )
    if backtest_on == "test":
        backtest_df = signaled.loc[test_idx]
    else:
        backtest_df = signaled

    strat = default_classifier_strategy()
    if strategy:
        strat.update(dict(strategy))
    if strategy_overrides:
        strat.update(dict(strategy_overrides))

    strat["freq"] = resolve_backtest_freq(
        backtest_df, strat, allow_resample=allow_resample
    )

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
            "signal_threshold": signal_threshold,
            "freq": strat["freq"],
            "purged_train_rows": fit.purged_train_rows,
            "train_start": str(train_idx[0]),
            "train_end": str(train_idx[-1]),
            "test_start": str(test_idx[0]),
            "test_end": str(test_idx[-1]),
        },
    )
