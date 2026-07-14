import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fast_trade.ml import regime


def _ohlcv(rows: int = 300, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq="h", tz="UTC")
    close = 100 * np.cumprod(1.0 + rng.normal(0.0005, 0.01, size=rows))
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": rng.uniform(1000, 5000, size=rows),
        },
        index=idx,
    )


def test_label_state_branches():
    cfg = {
        "trend_up": 0.01,
        "trend_down": -0.01,
        "vol_high": 0.05,
        "vol_low": 0.01,
        "liq_stress": 1.0,
    }
    assert regime._label_state(pd.Series({"trend": 0.02, "vol": 0.0, "range": 0.01, "volume_z": 0.0}), cfg) == "Risk-on"
    assert regime._label_state(pd.Series({"trend": -0.02, "vol": 0.0, "range": 0.01, "volume_z": 0.0}), cfg) == "Risk-off"
    assert regime._label_state(pd.Series({"trend": 0.0, "vol": 0.005, "range": 0.0, "volume_z": 0.0}), cfg) == "Mean reverting"
    assert regime._label_state(pd.Series({"trend": 0.0, "vol": 0.06, "range": 0.0, "volume_z": 0.0}), cfg) == "Expansion"
    assert regime._label_state(pd.Series({"trend": 0.0, "vol": 0.0, "range": 2.0, "volume_z": 2.0}), cfg) == "Liquidity stress"


def test_label_state_defaults_when_all_scores_zero():
    cfg = {
        "trend_up": 0.01,
        "trend_down": -0.01,
        "vol_high": 0.05,
        "vol_low": 0.0,
        "liq_stress": 1.0,
    }
    stats = pd.Series({"trend": 0.0, "vol": 0.0, "range": 0.0, "volume_z": 0.0})
    assert regime._label_state(stats, cfg) == "Mean reverting"


def test_train_apply_save_load(tmp_path):
    df = _ohlcv()
    config = {"settings": {"freq": "1D", "n_states": 3, "n_iter": 20}}
    model = regime.train_regime_model(df, config)
    assert isinstance(model.state_stats, pd.DataFrame)
    assert "label" in model.state_stats.columns

    applied = regime.apply_regime_model(df, model)
    assert "regime_label" in applied.columns
    assert "regime_conf" in applied.columns

    path = tmp_path / "regime.pkl"
    regime.save_regime_model(model, str(path))
    loaded = regime.load_regime_model(str(path))
    assert loaded.config == model.config
    assert list(loaded.state_stats.index) == list(model.state_stats.index)


def test_train_regime_model_requires_hmmlearn(monkeypatch):
    monkeypatch.setattr(regime, "GaussianHMM", None)
    with pytest.raises(RuntimeError, match="hmmlearn is required"):
        regime.train_regime_model(_ohlcv(), {"settings": {}})


def test_ensure_freq_and_compute_features():
    df = _ohlcv(100)
    cfg = {"vol_window": 5, "trend_window": 5, "volume_window": 5}
    features = regime._compute_features(df, cfg)
    assert list(features.columns) == ["ret", "vol", "range", "trend", "volume_z"]
    resampled = regime._ensure_freq(df, "1D")
    assert len(resampled) < len(df)
