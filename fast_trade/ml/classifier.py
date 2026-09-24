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
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from fast_trade.build_data_frame import infer_frequency
from fast_trade.frames import freq_to_timedelta, parse_freq
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
    df: pl.DataFrame
    trade_df: pl.DataFrame
    fit: ClassifierFitResult
    strategy: Dict[str, Any]
    extras: Dict[str, Any] = field(default_factory=dict)


def build_classifier_features(df: pl.DataFrame) -> pl.DataFrame:
    """Build OHLCV features, retaining ``date`` for prediction alignment.

    Rows remain in input order. Warmup rows and nonfinite calculations have
    null features and are excluded when fitting the classifier.
    """
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataframe missing required columns: {sorted(missing)}")

    df = df.with_columns(
        pl.when(pl.col(name).cast(pl.Float64).is_finite())
        .then(pl.col(name).cast(pl.Float64)).otherwise(None).alias(name)
        for name in ("close", "high", "low", "volume")
    )
    close = pl.col("close").cast(pl.Float64)
    high = pl.col("high").cast(pl.Float64)
    low = pl.col("low").cast(pl.Float64)
    volume = pl.col("volume").cast(pl.Float64)
    ret_1 = close / close.shift(1) - 1.0
    ret_1 = pl.when(ret_1.is_finite()).then(ret_1).otherwise(None)
    out = df.select(
        "date",
        ret_1.alias("ret_1"),
        (close / close.shift(5) - 1.0).alias("ret_5"),
        (close / close.shift(10) - 1.0).alias("ret_10"),
        ret_1.rolling_std(20, ddof=1).alias("vol_20"),
        ((high - low) / close).alias("range_pct"),
        (close / close.rolling_mean(20) - 1.0).alias("sma_ratio"),
        ((volume - volume.rolling_mean(20)) / volume.rolling_std(20, ddof=1)).alias("volume_z"),
    )
    return out.with_columns(
        pl.when(pl.col(name).is_finite()).then(pl.col(name)).otherwise(None).alias(name)
        for name in DEFAULT_FEATURE_COLUMNS
    )


def label_forward_return(
    close: pl.Series,
    horizon: int = 5,
    threshold: float = 0.01,
) -> pl.Series:
    """Label 1 when forward return over ``horizon`` bars exceeds ``threshold``."""
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    future = close.shift(-horizon)
    forward = future / close - 1.0
    valid = close.is_finite() & future.is_finite() & forward.is_finite()
    return (forward > threshold).cast(pl.Float64).set(~valid.fill_null(False), None).rename("y")


def _time_split_index(
    index: pl.Series,
    train_frac: float,
    *,
    purge_bars: int = 0,
) -> Tuple[pl.Series, pl.Series, int]:
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
    """True when two frequency aliases represent the same bar size.

    Handles aliases such as ``1h`` vs ``h`` / ``1H``.
    """
    try:
        count_a, unit_a = parse_freq(a)
        count_b, unit_b = parse_freq(b)
        # Calendar intervals must not compare equal to approximate day counts.
        if unit_a in {"mo", "y"} or unit_b in {"mo", "y"}:
            return (count_a, unit_a) == (count_b, unit_b)
        return freq_to_timedelta(a) == freq_to_timedelta(b)
    except (ValueError, TypeError):
        return _canonical_freq_str(a).lower() == _canonical_freq_str(b).lower()


def resolve_backtest_freq(
    df: pl.DataFrame,
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
    df: pl.DataFrame,
    *,
    horizon: int = 5,
    threshold: float = 0.01,
    train_frac: float = 0.7,
    feature_columns: Optional[Sequence[str]] = None,
    random_state: int = 42,
    signal_threshold: float = 0.5,
) -> Tuple[ClassifierFitResult, pl.DataFrame, pl.Series]:
    """Fit a classifier on time-ordered features/labels.

    Returns the fit result, a feature frame retaining ``date``, and a label
    series aligned by row, for all usable rows (including the purge gap).

    Training rows whose forward-return label window overlaps the holdout are
    purged (embargo of ``horizon`` bars) so holdout metrics stay out-of-sample.
    """
    if not 0.0 < signal_threshold < 1.0:
        raise ValueError("signal_threshold must be between 0 and 1")

    df = df.sort("date")
    features = build_classifier_features(df)
    labels = label_forward_return(df["close"], horizon=horizon, threshold=threshold)
    cols = list(feature_columns or DEFAULT_FEATURE_COLUMNS)
    missing = [c for c in cols if c not in DEFAULT_FEATURE_COLUMNS]
    if missing:
        raise ValueError(f"Unknown feature columns: {missing}")

    frame = features.select("date", *cols).with_columns(labels.alias("y"))
    usable = frame.filter(pl.all_horizontal(pl.col(name).is_finite() for name in [*cols, "y"]))
    if usable.is_empty():
        raise ValueError("No usable rows after dropping NaN features/labels")

    train_idx, test_idx, purged = _time_split_index(
        usable["date"], train_frac, purge_bars=horizon
    )
    train = usable.head(len(train_idx))
    test = usable.tail(len(test_idx))
    x_train = train.select(cols).to_numpy()
    y_train = train["y"].cast(pl.Int64).to_numpy()
    x_test = test.select(cols).to_numpy()
    y_test = test["y"].cast(pl.Int64).to_numpy()

    if np.unique(y_train).size < 2:
        raise ValueError("Training labels must include both classes; loosen threshold")

    model = HistGradientBoostingClassifier(random_state=random_state)
    model.fit(x_train, y_train)

    train_pred = _predict_with_threshold(model, x_train, signal_threshold)
    test_pred = _predict_with_threshold(model, x_test, signal_threshold)
    test_auc: Optional[float] = None
    if hasattr(model, "predict_proba") and np.unique(y_test).size > 1:
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
    return fit, usable.select("date", *cols), usable["y"].cast(pl.Int64)


def _predict_with_threshold(
    model: Any,
    x: np.ndarray,
    threshold: float,
) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(x)[:, 1]
        return (proba >= threshold).astype(int)
    return np.asarray(model.predict(x)).astype(int)


def predict_ml_signal(
    model: Any,
    features: pl.DataFrame,
    feature_columns: Sequence[str],
    *,
    threshold: float = 0.5,
) -> pl.DataFrame:
    """Return a ``date`` / ``ml_signal`` frame aligned to the feature rows.

    Uses ``predict_proba`` when available and marks 1 when P(class=1) >=
    ``threshold`` (default 0.5). Falls back to ``predict`` otherwise.
    """
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    cols = list(feature_columns)
    x = features.select(cols).to_numpy()
    pred = _predict_with_threshold(model, x, threshold)
    return features.select("date").with_columns(pl.Series("ml_signal", pred, dtype=pl.Int64))


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
    df: pl.DataFrame,
    signal: pl.DataFrame,
    column: str = "ml_signal",
) -> pl.DataFrame:
    """Attach date-keyed predictions, preserving OHLCV row order.

    ``signal`` has ``date`` and ``ml_signal`` columns. ``column`` chooses the
    output name, replacing that column if it is already present.
    """
    row_order = "__signal_row_order"
    while row_order in df.columns:
        row_order = "_" + row_order
    out = df.select(pl.exclude(column)).with_row_index(row_order).join(
        signal.select("date", pl.col("ml_signal").alias(column)),
        on="date", how="left", validate="m:1",
    ).sort(row_order).drop(row_order)
    # Holding flat when the model has no prediction keeps the sim deterministic.
    return out.with_columns(pl.col(column).fill_nan(0).fill_null(0).cast(pl.Int64))


def run_classifier_backtest(
    df: pl.DataFrame,
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
    usable_df = features.select("date").join(df, on="date", how="left", validate="1:1").sort("date")
    signaled = attach_ml_signal(usable_df, signal)

    train_idx, test_idx, _purged = _time_split_index(
        features["date"], train_frac, purge_bars=horizon
    )
    if backtest_on == "test":
        backtest_df = signaled.tail(len(test_idx))
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
