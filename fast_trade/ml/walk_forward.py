"""Chronological, purged classifier evaluation with comparable baselines.

Signals observed at a bar close execute at a later bar close (one bar later
by default). Each test window starts with fresh cash and ends flat. Returns
are relative to initial cash, include entry/exit commission, and are not an
annualized or stitched portfolio result. Inputs must have regular, real bars.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from fast_trade.build_data_frame import apply_transformers_to_dataframe
from fast_trade.finta import TA
from fast_trade.frames import freq_to_timedelta
from fast_trade.ml.classifier import (
    attach_ml_signal,
    build_classifier_features,
    default_classifier_strategy,
    label_forward_return,
    predict_ml_signal,
    resolve_backtest_freq,
)
from fast_trade.run_backtest import run_backtest


DEFAULT_TA_DATAPOINTS = [
    {"name": "rsi", "transformer": "rsi", "args": [14]},
    {"name": "ema_fast", "transformer": "ema", "args": [12]},
    {"name": "ema_slow", "transformer": "ema", "args": [26]},
    {"name": "atr", "transformer": "atr", "args": [14]},
]


@dataclass(frozen=True)
class FoldWindow:
    fold: int
    train_index: pl.Series
    test_index: pl.Series
    train_start_row: int
    test_start_row: int

    @property
    def train_start(self):
        return self.train_index[0]

    @property
    def train_end(self):
        return self.train_index[-1]

    @property
    def test_start(self):
        return self.test_index[0]

    @property
    def test_end(self):
        return self.test_index[-1]


@dataclass
class FoldMetrics:
    fold: int
    train_rows: int
    purged_train_rows: int
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
    buy_hold_return_perc: Optional[float]
    rsi_return_perc: Optional[float]
    rsi_num_trades: Optional[int]
    random_return_perc: Optional[float]
    random_num_trades: Optional[int]
    beats_buy_hold: Optional[bool]
    beats_rsi: Optional[bool]
    beats_random: Optional[bool]


@dataclass
class WalkForwardReport:
    folds: list[FoldMetrics]
    feature_columns: list[str]
    label_horizon: int
    label_threshold: float
    train_size: int
    test_size: int
    step_size: int
    aggregate: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)


def iter_rolling_folds(
    index: pl.Series, *, train_size: int, test_size: int, step_size: Optional[int] = None,
) -> list[FoldWindow]:
    """Return rolling folds with nonoverlapping test windows."""
    if train_size < 20 or test_size < 5:
        raise ValueError("train_size must be >= 20 and test_size >= 5")
    step = test_size if step_size is None else step_size
    if step < test_size:
        raise ValueError("step_size must be >= test_size to avoid overlapping test windows")
    if len(index) < train_size + test_size:
        raise ValueError("Not enough rows for one train/test fold")
    return [
        FoldWindow(i, index[start:start + train_size], index[start + train_size:start + train_size + test_size],
                   start, start + train_size)
        for i, start in enumerate(range(0, len(index) - train_size - test_size + 1, step))
    ]


def build_feature_matrix(
    df: pl.DataFrame, *, use_ta: bool = True,
    ta_datapoints: Optional[Sequence[Mapping[str, Any]]] = None,
    include_basic: bool = True, feature_columns: Optional[Sequence[str]] = None,
) -> tuple[pl.DataFrame, list[str]]:
    """Build date-keyed features once. Custom datapoints must be causal."""
    if not use_ta and not include_basic:
        raise ValueError("No features selected")
    features = build_classifier_features(df) if include_basic else df.select("date")
    if use_ta:
        dps = DEFAULT_TA_DATAPOINTS if ta_datapoints is None else ta_datapoints
        if any(dp.get("freq") for dp in dps):
            raise ValueError("Feature datapoints must use the input bar frequency")
        ta = apply_transformers_to_dataframe(df, [dict(dp) for dp in dps])
        extra = [name for name in ta.columns if name not in df.columns and name not in features.columns]
        features = features.join(ta.select("date", *extra), on="date", how="left", validate="1:1")
    available = [name for name, dtype in features.schema.items() if name != "date" and dtype.is_numeric()]
    cols = available if feature_columns is None else list(feature_columns)
    if not cols or set(cols) - set(available):
        raise ValueError("Select nonempty, known numeric feature columns")
    features = features.select("date", *cols).with_columns(
        pl.when(pl.col(name).is_finite()).then(pl.col(name)).otherwise(None).alias(name) for name in cols
    )
    return features, cols


def _run_signal_backtest(
    ohlcv: pl.DataFrame, signal: np.ndarray, *, freq: str, comission: float,
    signal_lag: int, base_balance: float,
) -> tuple[float, int, float]:
    values = pl.Series("ml_signal", signal, dtype=pl.Int64).shift(signal_lag).fill_null(0)
    frame = attach_ml_signal(ohlcv, ohlcv.select("date").with_columns(values))
    strategy = default_classifier_strategy(freq=freq, comission=comission, base_balance=base_balance)
    result = run_backtest(strategy, df=frame)
    simulated = result["df"]
    equity = simulated["adj_account_value"].to_numpy()
    net_return = float((equity[-1] / base_balance - 1.0) * 100.0)
    holding = simulated["in_trade"]
    closed = int((holding.shift(1).fill_null(False) & ~holding).sum())
    # The engine appends a synthetic row for a forced exit. Charge its fee on
    # the final real bar so Sharpe uses the same observation grid in every fold.
    bar_equity = equity[:ohlcv.height].copy()
    bar_equity[-1] = equity[-1]
    returns = bar_equity / np.r_[base_balance, bar_equity[:-1]] - 1.0
    std = float(np.std(returns, ddof=1))
    sharpe = float(np.sqrt(len(returns)) * np.mean(returns) / std) if std else 0.0
    return net_return, closed, sharpe


def _rsi_signal(values: np.ndarray) -> np.ndarray:
    signal = np.zeros(len(values), dtype=np.int64)
    holding = False
    for i, value in enumerate(values):
        if value < 30:
            holding = True
        elif value > 70:
            holding = False
        signal[i] = holding
    return signal


def walk_forward_evaluate(
    df: pl.DataFrame, *, train_size: int = 400, test_size: int = 100,
    step_size: Optional[int] = None, horizon: int = 5, threshold: float = 0.01,
    use_ta: bool = True, ta_datapoints: Optional[Sequence[Mapping[str, Any]]] = None,
    include_basic: bool = True, feature_columns: Optional[Sequence[str]] = None,
    freq: Optional[str] = None, comission: float = 0.01, random_state: int = 42,
    baselines: Sequence[str] = ("buy_hold", "rsi", "random"),
    signal_lag: int = 1, base_balance: float = 1000.0,
    test_start_row: Optional[int] = None,
) -> WalkForwardReport:
    """Fit each fold using only labels realized before its first test bar.

    All strategies use identical test bars, commission, signal delay and forced
    end-of-window exits. RSI has pre-test indicator history, but starts flat.
    Random exposure is calibrated from training labels only. Classification
    metrics exclude labels whose horizon extends past the test window.
    ``test_start_row`` anchors the first test bar in the sorted input, allowing
    different training window sizes to share identical test dates.
    """
    baseline_set = set(baselines)
    if baseline_set - {"buy_hold", "rsi", "random"}:
        raise ValueError("Unknown baselines")
    if horizon < 1 or horizon >= test_size or train_size - horizon < 20:
        raise ValueError("horizon must be positive, smaller than test_size, and leave 20 training rows")
    if signal_lag < 1 or not np.isfinite(base_balance) or base_balance <= 0:
        raise ValueError("signal_lag must be >= 1 and base_balance must be positive and finite")
    if test_start_row is not None and type(test_start_row) is not int:
        raise ValueError("test_start_row must be an integer row position")
    if not np.isfinite(comission) or not 0 <= comission < 100 or not np.isfinite(threshold):
        raise ValueError("comission must be between 0 and 100; threshold must be finite")
    required = {"date", "open", "high", "low", "close", "volume"}
    if required - set(df.columns) or df.is_empty():
        raise ValueError("Nonempty OHLCV with a date column is required")
    if not isinstance(df.schema["date"], pl.Datetime) or df["date"].null_count() or df["date"].n_unique() != df.height:
        raise ValueError("date must contain unique, non-null datetimes")
    df = df.sort("date")
    for name in required - {"date"}:
        if not df.schema[name].is_numeric() or not df[name].is_finite().fill_null(False).all():
            raise ValueError("OHLCV values must be finite numbers")
    if (df["close"] <= 0).any():
        raise ValueError("close prices must be positive")
    resolved_freq = resolve_backtest_freq(df, {"freq": freq})
    if not (df["date"].diff().drop_nulls() == freq_to_timedelta(resolved_freq)).all():
        raise ValueError("Input contains missing or irregular bars; select a contiguous period")
    features, cols = build_feature_matrix(
        df, use_ta=use_ta, ta_datapoints=ta_datapoints,
        include_basic=include_basic, feature_columns=feature_columns,
    )
    valid = features.select(pl.all_horizontal(pl.col(name).is_finite() for name in cols)).to_series().fill_null(False)
    usable = np.flatnonzero(valid.to_numpy())
    if not len(usable):
        raise ValueError("No usable feature rows after warmup")
    warmup = int(usable[0])
    first_train = warmup if test_start_row is None else test_start_row - train_size
    if first_train < warmup:
        raise ValueError("test_start_row must leave a full training window after feature warmup")
    windows = iter_rolling_folds(
        df["date"][first_train:], train_size=train_size, test_size=test_size, step_size=step_size,
    )
    labels = label_forward_return(df["close"], horizon=horizon, threshold=threshold).to_numpy()
    x = features.select(cols).to_numpy()
    valid_values = valid.to_numpy()
    rsi = TA.RSI(df, 14).to_numpy() if "rsi" in baseline_set else None
    folds = []
    for window in windows:
        train_start = first_train + window.train_start_row
        test_start = first_train + window.test_start_row
        # Purge by original bar position, before filtering invalid features.
        train_end = test_start - horizon
        good = valid_values[train_start:train_end] & np.isfinite(labels[train_start:train_end])
        x_train = x[train_start:train_end][good]
        y_train = labels[train_start:train_end][good].astype(int)
        if len(y_train) < 20 or len(np.unique(y_train)) < 2:
            raise ValueError(f"Fold {window.fold}: need 20 usable training rows and both label classes")
        model = HistGradientBoostingClassifier(random_state=random_state + window.fold)
        model.fit(x_train, y_train)
        test_features = features.slice(test_start, test_size)
        test_good = valid.slice(test_start, test_size)
        ohlcv_test = df.slice(test_start, test_size)
        signal = np.zeros(test_size, dtype=np.int64)
        if test_good.any():
            predictions = predict_ml_signal(model, test_features.filter(test_good), cols)
            signal[test_good.to_numpy()] = predictions["ml_signal"].to_numpy()
        test_y = labels[test_start:test_start + test_size - horizon]
        labeled = test_good.to_numpy()[:-horizon] & np.isfinite(test_y)
        accuracy = auc = None
        if labeled.any():
            y_true = test_y[labeled].astype(int)
            accuracy = float(accuracy_score(y_true, signal[:-horizon][labeled]))
            if len(np.unique(y_true)) > 1:
                proba = model.predict_proba(x[test_start:test_start + test_size - horizon][labeled])[:, 1]
                auc = float(roc_auc_score(y_true, proba))
        options = dict(freq=resolved_freq, comission=comission, signal_lag=signal_lag, base_balance=base_balance)
        ml_ret, ml_trades, ml_sharpe = _run_signal_backtest(ohlcv_test, signal, **options)
        baseline_metrics = {}
        for name in sorted(baseline_set):
            if name == "buy_hold":
                values = np.ones(test_size, dtype=np.int64)
            elif name == "rsi":
                values = _rsi_signal(rsi[test_start:test_start + test_size])
            else:
                rng = np.random.default_rng(random_state + 1000 + window.fold)
                values = (rng.random(test_size) < y_train.mean()).astype(np.int64)
            baseline_metrics[name] = _run_signal_backtest(ohlcv_test, values, **options)
        bh, rs, rand = [baseline_metrics.get(name, (None, None, None)) for name in ("buy_hold", "rsi", "random")]
        folds.append(FoldMetrics(
            window.fold, len(y_train), horizon, test_size,
            str(df["date"][train_start]), str(df["date"][train_end - 1]),
            str(window.test_start), str(window.test_end), accuracy, auc,
            ml_ret, ml_trades, ml_sharpe, bh[0], rs[0], rs[1], rand[0], rand[1],
            ml_ret > bh[0] if bh[0] is not None else None,
            ml_ret > rs[0] if rs[0] is not None else None,
            ml_ret > rand[0] if rand[0] is not None else None,
        ))
    aggregate = {
        "n_folds": len(folds),
        "median_ml_return_perc": float(np.median([f.ml_return_perc for f in folds])),
        "mean_ml_return_perc": float(np.mean([f.ml_return_perc for f in folds])),
        "total_ml_trades": sum(f.ml_num_trades for f in folds),
    }
    aucs = [f.test_roc_auc for f in folds if f.test_roc_auc is not None]
    aggregate["median_test_roc_auc"] = float(np.median(aucs)) if aucs else None
    for name in sorted(baseline_set):
        aggregate[f"median_{name}_return_perc"] = float(np.median([getattr(f, f"{name}_return_perc") for f in folds]))
        aggregate[f"pct_folds_beat_{name}"] = float(np.mean([getattr(f, f"beats_{name}") for f in folds]) * 100)
    return WalkForwardReport(
        folds, cols, horizon, threshold, train_size, test_size, test_size if step_size is None else step_size,
        aggregate, {"baselines": sorted(baseline_set), "freq": resolved_freq, "comission": comission,
                    "random_state": random_state, "signal_lag": signal_lag, "base_balance": base_balance,
                    "execution": "signal at close; fill at a later close; force exit on last test close",
                    "costs": "commission on entry and exit; slippage and financing are not modeled",
                    "aggregation": "independent folds reset cash; returns are not stitched or annualized"},
    )


def report_to_frame(report: WalkForwardReport) -> pl.DataFrame:
    """Return a Polars fold table suitable for CSV or Parquet export."""
    return pl.DataFrame([asdict(fold) for fold in report.folds])


def evaluate_fixed_split(
    df: pl.DataFrame, train_index: pl.Series, test_index: pl.Series, **options: Any,
) -> FoldMetrics:
    """Fit once before a fixed holdout, reusing the rolling engine's contract.

    Indices are explicit date Series for adjacent chronological raw-bar ranges.
    Earlier input history warms features but cannot supply extra training rows.
    The training range's final horizon is purged, and no holdout refit occurs.
    Input after the final test date is ignored.
    """
    if train_index.is_empty() or test_index.is_empty():
        raise ValueError("Training and test dates must be nonempty")
    # Compare physical instants, not Python wall-clock equality: fold=0 and
    # fold=1 of a repeated DST hour may otherwise compare equal.
    dates = df.sort("date")["date"].dt.epoch("ns").to_list()
    test_dates = test_index.dt.epoch("ns").to_list()
    train_dates = train_index.dt.epoch("ns").to_list()
    if test_dates[0] not in dates:
        raise ValueError("Test dates must exist in the input")
    start = dates.index(test_dates[0])
    if (start < len(train_dates) or dates[start - len(train_dates):start] != train_dates
            or dates[start:start + len(test_dates)] != test_dates):
        raise ValueError("Training/test dates must be adjacent, ordered, disjoint raw-bar ranges")
    frame = df.sort("date").head(start + len(test_dates))
    report = walk_forward_evaluate(
        frame, train_size=len(train_dates), test_size=len(test_dates),
        test_start_row=start, **options,
    )
    return report.folds[0]
