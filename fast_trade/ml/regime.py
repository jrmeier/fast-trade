import pickle
import re
from dataclasses import dataclass
from typing import Mapping

import numpy as np
import polars as pl

try:
    from hmmlearn.hmm import GaussianHMM
except Exception:  # pragma: no cover
    GaussianHMM = None


@dataclass
class RegimeModel:
    model: object
    state_stats: pl.DataFrame
    config: dict


def _polars_duration(freq: str) -> str:
    value = str(freq).strip()
    match = re.fullmatch(r"(\d+)\s*([A-Za-z]+)", value)
    if not match:
        return value.lower()
    amount, unit = match.groups()
    units = {
        "s": "s",
        "sec": "s",
        "min": "m",
        "t": "m",
        "m": "m",
        "h": "h",
        "hour": "h",
        "d": "d",
        "day": "d",
        "w": "w",
        "week": "w",
        "mo": "mo",
        "month": "mo",
    }
    return f"{amount}{units.get(unit.lower(), unit.lower())}"


def _ensure_freq(df: pl.DataFrame, freq: str) -> pl.DataFrame:
    if "date" not in df.columns:
        raise ValueError("Regime data requires an explicit date column")
    df = df.sort("date")
    if freq:
        df = df.group_by_dynamic("date", every=_polars_duration(freq)).agg(
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
        )
        df = df.drop_nulls(["open", "high", "low", "close", "volume"])
    return df


def _finite(expr: pl.Expr) -> pl.Expr:
    return pl.when(expr.is_finite()).then(expr).otherwise(0.0).fill_null(0.0)


def _compute_features(df: pl.DataFrame, cfg: dict) -> pl.DataFrame:
    window = int(cfg.get("vol_window", 20))
    trend_window = int(cfg.get("trend_window", 20))
    volume_window = int(cfg.get("volume_window", 20))
    working = df.with_row_index("_row").with_columns(
        pl.col("_row").cast(pl.Float64),
        pl.col("close").pct_change().alias("_ret"),
    )
    rolling_x = pl.col("_row").rolling_sum(trend_window)
    rolling_y = pl.col("close").rolling_sum(trend_window)
    rolling_xy = (pl.col("_row") * pl.col("close")).rolling_sum(trend_window)
    rolling_x2 = (pl.col("_row") ** 2).rolling_sum(trend_window)
    numerator = trend_window * rolling_xy - rolling_x * rolling_y
    denominator = trend_window * rolling_x2 - rolling_x**2
    trend = numerator / denominator
    volume_mean = pl.col("volume").rolling_mean(volume_window)
    volume_std = pl.col("volume").rolling_std(volume_window)
    return working.select(
        _finite(pl.col("_ret")).alias("ret"),
        _finite(pl.col("_ret").rolling_std(window)).alias("vol"),
        _finite((pl.col("high") - pl.col("low")) / pl.col("close")).alias("range"),
        _finite(trend).alias("trend"),
        _finite((pl.col("volume") - volume_mean) / volume_std).alias("volume_z"),
    )


def _label_state(stats: Mapping[str, float], cfg: dict) -> str:
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


def train_regime_model(df: pl.DataFrame, config: dict) -> RegimeModel:
    if GaussianHMM is None:
        raise RuntimeError("hmmlearn is required for regime training")

    cfg = config.get("settings", {})
    freq = cfg.get("freq", "1H")
    n_states = int(cfg.get("n_states", 6))

    df = _ensure_freq(df.clone(), freq)
    features = _compute_features(df, cfg)
    x = features.to_numpy()

    model = GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=cfg.get("n_iter", 100))
    model.fit(x)

    states = model.predict(x)
    state_stats = (
        features.with_columns(pl.Series("state", states))
        .group_by("state")
        .mean()
        .sort("state")
    )
    state_stats = state_stats.with_columns(
        pl.Series("label", [_label_state(row, cfg) for row in state_stats.iter_rows(named=True)])
    )

    return RegimeModel(model=model, state_stats=state_stats, config=config)


def apply_regime_model(df: pl.DataFrame, model: RegimeModel) -> pl.DataFrame:
    cfg = model.config.get("settings", {})
    freq = cfg.get("freq", "1H")
    df = _ensure_freq(df.clone(), freq)
    features = _compute_features(df, cfg)
    x = features.to_numpy()

    states = model.model.predict(x)
    probs = model.model.predict_proba(x)
    labels_by_state = dict(
        zip(model.state_stats["state"].to_list(), model.state_stats["label"].to_list())
    )
    labels = []
    confs = []
    for i, state in enumerate(states):
        label = labels_by_state[int(state)]
        conf = float(np.max(probs[i]))
        labels.append(label)
        confs.append(conf)

    return df.with_columns(
        pl.Series("regime_label", labels),
        pl.Series("regime_conf", confs),
    )


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
