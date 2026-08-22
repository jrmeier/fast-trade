"""Tests for walk-forward classifier evaluation."""

import numpy as np
import pandas as pd
import pytest

from fast_trade.ml.walk_forward import (
    build_feature_matrix,
    buy_hold_return_perc,
    iter_rolling_folds,
    report_to_frame,
    walk_forward_evaluate,
)


def _synthetic_ohlcv(rows: int = 800, seed: int = 3, freq: str = "1h") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq=freq, tz="UTC")
    rets = rng.normal(0.0004, 0.012, size=rows)
    close = 80 * np.cumprod(1.0 + rets)
    high = close * (1.0 + rng.uniform(0.0, 0.01, size=rows))
    low = close * (1.0 - rng.uniform(0.0, 0.01, size=rows))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(50.0, 400.0, size=rows)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_iter_rolling_folds_shapes():
    idx = pd.date_range("2024-01-01", periods=100, freq="h")
    folds = iter_rolling_folds(idx, train_size=40, test_size=10, step_size=10)
    assert len(folds) == 6
    assert len(folds[0].train_index) == 40
    assert len(folds[0].test_index) == 10
    assert folds[0].train_start == idx[0]
    assert folds[0].test_end == idx[49]


def test_iter_rolling_folds_validation():
    idx = pd.date_range("2024-01-01", periods=30, freq="h")
    with pytest.raises(ValueError, match="train_size"):
        iter_rolling_folds(idx, train_size=10, test_size=5)
    with pytest.raises(ValueError, match="test_size"):
        iter_rolling_folds(idx, train_size=20, test_size=2)
    with pytest.raises(ValueError, match="step_size"):
        iter_rolling_folds(idx, train_size=20, test_size=5, step_size=0)
    with pytest.raises(ValueError, match="Need at least"):
        iter_rolling_folds(idx, train_size=20, test_size=20)


def test_build_feature_matrix_basic_and_ta():
    df = _synthetic_ohlcv(rows=120)
    features, cols = build_feature_matrix(df, use_ta=True, include_basic=True)
    assert "ret_1" in cols
    assert "rsi" in cols
    assert "ema_fast" in cols
    assert len(features) == len(df)

    with pytest.raises(ValueError, match="missing required"):
        build_feature_matrix(df.drop(columns=["volume"]))
    with pytest.raises(ValueError, match="Unknown feature"):
        build_feature_matrix(df, feature_columns=["nope"])
    with pytest.raises(ValueError, match="No features selected"):
        build_feature_matrix(df, use_ta=False, include_basic=False)


def test_buy_hold_return_perc():
    s = pd.Series([100.0, 110.0])
    assert buy_hold_return_perc(s) == pytest.approx(10.0)
    assert buy_hold_return_perc(pd.Series(dtype=float)) == 0.0
    assert buy_hold_return_perc(pd.Series([0.0, 1.0])) == 0.0


def test_walk_forward_evaluate_synthetic():
    df = _synthetic_ohlcv(rows=900)
    report = walk_forward_evaluate(
        df,
        train_size=300,
        test_size=80,
        step_size=80,
        horizon=5,
        threshold=0.0,
        use_ta=True,
        comission=0.0,
        random_state=1,
    )
    assert report.aggregate["n_folds"] >= 2
    assert len(report.folds) == report.aggregate["n_folds"]
    assert report.folds[0].test_rows == 80
    assert "median_ml_return_perc" in report.aggregate
    frame = report_to_frame(report)
    assert list(frame["fold"]) == list(range(len(report.folds)))
    assert "beats_buy_hold" in frame.columns


def test_walk_forward_unknown_baseline_and_no_ta():
    df = _synthetic_ohlcv(rows=700)
    with pytest.raises(ValueError, match="Unknown baselines"):
        walk_forward_evaluate(df, baselines=("buy_hold", "magic"), train_size=300, test_size=80)

    report = walk_forward_evaluate(
        df,
        train_size=300,
        test_size=80,
        step_size=200,
        horizon=5,
        threshold=0.0,
        use_ta=False,
        include_basic=True,
        baselines=("buy_hold",),
        comission=0.0,
        random_state=2,
    )
    assert report.aggregate["n_folds"] >= 1
    assert report.extras["baselines"] == ["buy_hold"]
    # RSI/random skipped → zeros
    assert report.folds[0].rsi_num_trades == 0
    assert report.folds[0].random_num_trades == 0


def test_walk_forward_rejects_single_class_labels():
    df = _synthetic_ohlcv(rows=600)
    with pytest.raises(ValueError, match="both classes"):
        walk_forward_evaluate(
            df,
            train_size=300,
            test_size=80,
            step_size=80,
            horizon=5,
            threshold=50.0,
            use_ta=False,
            comission=0.0,
        )


def test_numeric_feature_skip_and_empty(monkeypatch):
    from fast_trade.ml import walk_forward as wf

    mixed = pd.DataFrame(
        {
            "a": [1.0, 2.0],
            "b": ["x", "y"],
            "ml_signal": [0, 1],
        }
    )
    cols = wf._numeric_feature_columns(mixed, exclude={"ml_signal"})
    assert cols == ["a"]

    df = _synthetic_ohlcv(rows=120)
    monkeypatch.setattr(wf, "_numeric_feature_columns", lambda *a, **k: [])
    with pytest.raises(ValueError, match="No numeric feature"):
        wf.build_feature_matrix(df, use_ta=False, include_basic=True)


def test_safe_auc_single_class():
    from fast_trade.ml.walk_forward import _safe_auc

    assert _safe_auc(np.array([1, 1, 1]), np.array([0.1, 0.2, 0.3])) is None
    assert _safe_auc(np.array([0, 1]), np.array([0.1, 0.9])) == pytest.approx(1.0)


def test_walk_forward_empty_features_and_short_train(monkeypatch):
    from fast_trade.ml import walk_forward as wf

    df = _synthetic_ohlcv(rows=500)

    class _Empty:
        def dropna(self):
            return pd.DataFrame()

        @property
        def columns(self):
            return pd.Index(["ret_1"])

    monkeypatch.setattr(
        wf,
        "build_feature_matrix",
        lambda *a, **k: (_Empty(), ["ret_1"]),
    )
    with pytest.raises(ValueError, match="No usable feature"):
        wf.walk_forward_evaluate(df, train_size=200, test_size=50, use_ta=False)

    monkeypatch.undo()
    # Huge horizon vs train window → too few labeled train rows
    with pytest.raises(ValueError, match="too few labeled train"):
        walk_forward_evaluate(
            df,
            train_size=40,
            test_size=20,
            step_size=20,
            horizon=30,
            threshold=0.0,
            use_ta=False,
            comission=0.0,
        )
