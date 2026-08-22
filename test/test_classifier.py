"""Tests for the ML classifier → ml_signal → backtest helpers."""

import numpy as np
import pandas as pd
import pytest

from fast_trade.build_data_frame import apply_transformers_to_dataframe
from fast_trade.ml.classifier import (
    attach_ml_signal,
    build_classifier_features,
    default_classifier_strategy,
    fit_return_classifier,
    label_forward_return,
    ml_signal_datapoint,
    predict_ml_signal,
    run_classifier_backtest,
)
from fast_trade.validate_backtest import validate_backtest


def _synthetic_ohlcv(rows: int = 400, seed: int = 11, freq: str = "1h") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq=freq, tz="UTC")
    rets = rng.normal(0.0005, 0.012, size=rows)
    close = 50 * np.cumprod(1.0 + rets)
    high = close * (1.0 + rng.uniform(0.0, 0.01, size=rows))
    low = close * (1.0 - rng.uniform(0.0, 0.01, size=rows))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(10.0, 500.0, size=rows)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_build_classifier_features_and_labels():
    df = _synthetic_ohlcv()
    features = build_classifier_features(df)
    assert list(features.columns) == [
        "ret_1",
        "ret_5",
        "ret_10",
        "vol_20",
        "range_pct",
        "sma_ratio",
        "volume_z",
    ]
    labels = label_forward_return(df["close"], horizon=5, threshold=0.0)
    assert labels.notna().sum() == len(df) - 5
    assert set(labels.dropna().unique()).issubset({0.0, 1.0})


def test_column_transformer_passthrough():
    df = _synthetic_ohlcv(rows=80)
    df["ml_signal"] = 0
    df.loc[df.index[10:20], "ml_signal"] = 1
    out = apply_transformers_to_dataframe(
        df[["open", "high", "low", "close", "volume", "ml_signal"]],
        [ml_signal_datapoint()],
    )
    assert "ml_signal" in out.columns
    assert int(out["ml_signal"].sum()) == 10


def test_column_transformer_missing_raises():
    df = _synthetic_ohlcv(rows=50)
    with pytest.raises(Exception, match="ml_signal"):
        apply_transformers_to_dataframe(df, [ml_signal_datapoint()])


def test_default_strategy_validates():
    strategy = default_classifier_strategy()
    errors = validate_backtest(strategy)
    assert errors.get("has_error") is False


def test_fit_and_predict_signal_shapes():
    df = _synthetic_ohlcv()
    fit, features, labels = fit_return_classifier(
        df, horizon=5, threshold=0.0, train_frac=0.7, random_state=0
    )
    assert fit.train_rows + fit.test_rows == len(features)
    assert 0.0 <= fit.train_accuracy <= 1.0
    assert 0.0 <= fit.test_accuracy <= 1.0
    signal = predict_ml_signal(fit.model, features, fit.feature_columns)
    assert signal.index.equals(features.index)
    assert set(signal.unique()).issubset({0, 1})
    assert labels.index.equals(features.index)


def test_run_classifier_backtest_on_synthetic():
    df = _synthetic_ohlcv(rows=500)
    result = run_classifier_backtest(
        df,
        horizon=5,
        threshold=0.0,
        train_frac=0.7,
        backtest_on="test",
        strategy_overrides={"freq": "1h", "comission": 0.0},
        random_state=1,
    )
    assert result.fit.test_rows > 0
    assert "ml_signal" in result.df.columns
    assert "return_perc" in result.summary
    assert result.extras["backtest_on"] == "test"
    # Holdout backtest frame should be shorter than full usable history.
    assert len(result.df) <= result.fit.test_rows + 5


def test_attach_ml_signal_fills_missing():
    df = _synthetic_ohlcv(rows=30)
    signal = pd.Series([1, 0, 1], index=df.index[:3])
    out = attach_ml_signal(df, signal)
    assert out["ml_signal"].iloc[:3].tolist() == [1, 0, 1]
    assert (out["ml_signal"].iloc[3:] == 0).all()
