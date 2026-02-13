import datetime
import pickle
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from hmmlearn.hmm import GaussianHMM
except Exception:  # pragma: no cover
    GaussianHMM = None


@dataclass
class RegimeModel:
    model: object
    state_stats: pd.DataFrame
    config: dict


def _ensure_freq(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    if freq:
        df = df.resample(freq).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        df = df.dropna()
    return df


def _compute_features(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    window = int(cfg.get("vol_window", 20))
    trend_window = int(cfg.get("trend_window", 20))
    volume_window = int(cfg.get("volume_window", 20))

    out = pd.DataFrame(index=df.index)
    out["ret"] = df["close"].pct_change().fillna(0.0)
    out["vol"] = out["ret"].rolling(window).std().fillna(0.0)
    out["range"] = (df["high"] - df["low"]) / df["close"]
    out["trend"] = (
        df["close"].rolling(trend_window).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0], raw=False)
    ).fillna(0.0)
    out["volume_z"] = (
        (df["volume"] - df["volume"].rolling(volume_window).mean())
        / df["volume"].rolling(volume_window).std()
    ).fillna(0.0)
    out = out.replace([np.inf, -np.inf], 0.0)
    return out


def _label_state(stats: pd.Series, cfg: dict) -> str:
    trend_hi = float(cfg.get("trend_up", 0.0))
    trend_lo = float(cfg.get("trend_down", 0.0))
    vol_hi = float(cfg.get("vol_high", 0.0))
    vol_lo = float(cfg.get("vol_low", 0.0))
    liq_hi = float(cfg.get("liq_stress", 0.0))

    trend = stats["trend"]
    vol = stats["vol"]
    range_ = stats["range"]
    volume_z = stats["volume_z"]

    scores = {}
    scores["Trending up"] = max(0.0, trend - trend_hi)
    scores["Trending down"] = max(0.0, trend_lo - trend)
    scores["Mean reverting"] = max(0.0, vol_lo - vol)
    scores["High volatility"] = max(0.0, vol - vol_hi)
    scores["Low volatility"] = max(0.0, vol_lo - vol)
    scores["Liquidity stress"] = max(0.0, range_ + volume_z - liq_hi)
    scores["Expansion"] = max(0.0, vol + range_)
    scores["Contraction"] = max(0.0, vol_lo - vol)
    scores["Risk-on"] = max(0.0, trend + vol)
    scores["Risk-off"] = max(0.0, -trend + vol)

    # pick max score label, default to Mean reverting
    best = max(scores.items(), key=lambda x: x[1])
    if best[1] == 0.0:
        return "Mean reverting"
    return best[0]


def train_regime_model(df: pd.DataFrame, config: dict) -> RegimeModel:
    if GaussianHMM is None:
        raise RuntimeError("hmmlearn is required for regime training")

    cfg = config.get("settings", {})
    freq = cfg.get("freq", "1H")
    n_states = int(cfg.get("n_states", 6))

    df = _ensure_freq(df.copy(), freq)
    features = _compute_features(df, cfg)
    X = features.values

    model = GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=cfg.get("n_iter", 100))
    model.fit(X)

    states = model.predict(X)
    features["state"] = states
    state_stats = features.groupby("state").mean()
    state_stats["label"] = state_stats.apply(lambda row: _label_state(row, cfg), axis=1)

    return RegimeModel(model=model, state_stats=state_stats, config=config)


def apply_regime_model(df: pd.DataFrame, model: RegimeModel) -> pd.DataFrame:
    cfg = model.config.get("settings", {})
    freq = cfg.get("freq", "1H")
    df = _ensure_freq(df.copy(), freq)
    features = _compute_features(df, cfg)
    X = features.values

    states = model.model.predict(X)
    probs = model.model.predict_proba(X)
    labels = []
    confs = []
    for i, state in enumerate(states):
        label = model.state_stats.loc[state, "label"]
        conf = float(np.max(probs[i]))
        labels.append(label)
        confs.append(conf)

    df["regime_label"] = labels
    df["regime_conf"] = confs
    return df


def save_regime_model(model: RegimeModel, path: str) -> None:
    payload = {
        "model": model.model,
        "state_stats": model.state_stats,
        "config": model.config,
    }
    with open(path, "wb") as fh:
        pickle.dump(payload, fh)


def load_regime_model(path: str) -> RegimeModel:
    with open(path, "rb") as fh:
        payload = pickle.load(fh)
    return RegimeModel(
        model=payload["model"],
        state_stats=payload["state_stats"],
        config=payload["config"],
    )
