"""HMM multi-asset forecast screening core."""

from __future__ import annotations

import datetime as dt
import json
import math
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler


DEFAULT_HORIZONS = (7, 30, 60)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def normalize_config(config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    cfg = dict(config or {})
    settings = dict(cfg.get("settings") or {})
    filters = dict(cfg.get("filters") or {})
    outputs = dict(cfg.get("outputs") or {})

    horizons = settings.get("horizons", list(DEFAULT_HORIZONS))
    if isinstance(horizons, (list, tuple)):
        horizons = tuple(int(h) for h in horizons)
    else:
        horizons = DEFAULT_HORIZONS

    return {
        "exchange": str(cfg.get("exchange") or settings.get("exchange") or "coinbase").lower(),
        "symbols": list(cfg.get("symbols") or settings.get("symbols") or []),
        "settings": {
            "lookback_days": int(settings.get("lookback_days", 260)),
            "freq": str(settings.get("freq", "1D")),
            "horizons": tuple(sorted(set(horizons))),
            "states": int(settings.get("states", 3)),
            "simulations": int(settings.get("simulations", 5000)),
            "seed": int(settings.get("seed", 42)),
            "max_products": int(settings.get("max_products", 40)),
            "cache_dir": settings.get("cache_dir"),
            "cache_max_age_hours": float(settings.get("cache_max_age_hours", 6.0)),
        },
        "filters": {
            "min_candles": int(filters.get("min_candles", 180)),
            "min_quote_volume_24h": float(filters.get("min_quote_volume_24h", 0.0)),
            "min_avg_quote_volume_30d": float(filters.get("min_avg_quote_volume_30d", 0.0)),
            "max_drawdown_60d": float(filters.get("max_drawdown_60d", -1.0)),
        },
        "outputs": {
            "json_out": outputs.get("json_out"),
            "md_out": outputs.get("md_out"),
            "title": outputs.get("title") or "HMM Screener",
        },
        "live": bool(cfg.get("live", False)),
    }


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    features = pd.DataFrame(index=df.index)
    features["ret"] = close.pct_change().fillna(0.0)
    features["vol"] = features["ret"].rolling(20).std().fillna(0.0)
    features["range"] = (
        ((df["high"] - df["low"]) / close).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    )
    features["trend"] = close.pct_change(20).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    running_high = close.cummax()
    features["drawdown"] = (
        ((close / running_high) - 1.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    )
    return features.replace([np.inf, -np.inf], 0.0).fillna(0.0)


def max_drawdown(df: pd.DataFrame, lookback: int) -> float:
    close = df["close"].tail(lookback)
    if close.empty:
        return 0.0
    return float((close / close.cummax() - 1.0).min())


def avg_quote_volume(df: pd.DataFrame, lookback: int) -> float:
    recent = df.tail(lookback)
    if recent.empty:
        return 0.0
    return float((recent["close"] * recent["volume"]).mean())


def simulate_returns(
    model: GaussianHMM,
    states: np.ndarray,
    returns: pd.Series,
    horizons: Sequence[int],
    simulations: int,
    rng: np.random.Generator,
) -> Dict[int, Dict[str, float]]:
    state_returns = {
        state: returns.iloc[np.where(states == state)[0]].dropna().to_numpy()
        for state in range(model.n_components)
    }
    all_returns = returns.dropna().to_numpy()
    current_state = int(states[-1])
    max_horizon = max(horizons)
    horizon_values = {int(h): [] for h in horizons}

    for _ in range(simulations):
        state = current_state
        compounded = 1.0
        for day in range(1, max_horizon + 1):
            probs = np.asarray(model.transmat_[state], dtype=float)
            if probs.sum() <= 0 or np.isnan(probs).any():
                probs = np.ones(model.n_components) / model.n_components
            state = int(rng.choice(model.n_components, p=probs / probs.sum()))
            samples = state_returns.get(state)
            if samples is None or len(samples) == 0:
                samples = all_returns
            sampled_ret = float(rng.choice(samples)) if len(samples) else 0.0
            compounded *= 1.0 + sampled_ret
            if day in horizon_values:
                horizon_values[day].append(compounded - 1.0)

    results: Dict[int, Dict[str, float]] = {}
    for horizon, values in horizon_values.items():
        arr = np.asarray(values)
        results[horizon] = {
            "p10": float(np.quantile(arr, 0.10)),
            "p25": float(np.quantile(arr, 0.25)),
            "p50": float(np.quantile(arr, 0.50)),
            "p75": float(np.quantile(arr, 0.75)),
            "p90": float(np.quantile(arr, 0.90)),
        }
    return results


def score_forecasts(forecasts: Mapping[int, Mapping[str, float]]) -> float:
    score = forecasts.get(30, {}).get("p50", 0.0) * 100
    score += forecasts.get(60, {}).get("p50", 0.0) * 50
    score += forecasts.get(30, {}).get("p25", 0.0) * 100
    return float(score)


def fit_hmm_forecast(
    symbol: str,
    df: pd.DataFrame,
    meta: Optional[Mapping[str, Any]] = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    n_states: int = 3,
    simulations: int = 5000,
    seed: int = 42,
) -> Dict[str, Any]:
    if len(df) < 90:
        raise RuntimeError(f"{symbol} has too little candle history: {len(df)} rows")

    meta = dict(meta or {})
    features = make_features(df)
    returns = features["ret"]
    scaler = StandardScaler()
    x = scaler.fit_transform(features.to_numpy())
    model = GaussianHMM(
        n_components=n_states,
        covariance_type="diag",
        n_iter=500,
        tol=1e-4,
        random_state=seed,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(x)
    states = model.predict(x)
    rng = np.random.default_rng(seed)
    forecasts = simulate_returns(model, states, returns, horizons, simulations, rng)
    expected_daily = float(
        np.average(model.means_[:, 0], weights=model.predict_proba(x)[-1])
    )
    price = float(meta.get("price") or df["close"].iloc[-1])
    quote_volume_24h = float(
        meta.get("quote_volume_24h")
        or meta.get("day_notional_volume")
        or (df["close"].iloc[-1] * df["volume"].iloc[-1])
    )

    result = {
        "symbol": symbol,
        "exchange": meta.get("exchange"),
        "price": price,
        "quote_volume_24h": quote_volume_24h,
        "avg_quote_volume_30d": avg_quote_volume(df, 30),
        "candles": int(len(df)),
        "current_state": int(states[-1]),
        "expected_daily_return": expected_daily,
        "max_drawdown_60d": max_drawdown(df, 60),
        "forecasts": {str(k): v for k, v in forecasts.items()},
        "score": score_forecasts(forecasts),
        "warnings": sorted({str(w.message) for w in caught}),
    }
    for key in (
        "product_id",
        "coin",
        "open_interest",
        "funding",
        "max_leverage",
        "day_notional_volume",
    ):
        if key in meta:
            result[key] = meta[key]
    if "product_id" not in result and "-" in symbol:
        result["product_id"] = symbol
    if "coin" not in result and "-" not in symbol:
        result["coin"] = symbol
    return result


def evaluate_filters(
    df: pd.DataFrame,
    meta: Mapping[str, Any],
    filters: Mapping[str, Any],
) -> Tuple[bool, str]:
    min_candles = int(filters.get("min_candles", 0))
    if len(df) < min_candles:
        return False, f"only {len(df)} candles"

    min_quote_24h = float(filters.get("min_quote_volume_24h", 0.0))
    quote_24h = float(
        meta.get("quote_volume_24h")
        or meta.get("day_notional_volume")
        or 0.0
    )
    if min_quote_24h and quote_24h < min_quote_24h:
        return False, "below 24h quote volume threshold"

    min_avg_30d = float(filters.get("min_avg_quote_volume_30d", 0.0))
    avg_30d = avg_quote_volume(df, 30)
    if min_avg_30d and avg_30d < min_avg_30d:
        return False, "below 30d average quote volume threshold"

    max_dd = float(filters.get("max_drawdown_60d", -1.0))
    dd60 = max_drawdown(df, 60)
    if dd60 < max_dd:
        return False, f"60d drawdown {pct(dd60)}"

    return True, ""


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.2f}"


def forecast_cell(item: Mapping[str, Any], horizon: int) -> str:
    forecast = item["forecasts"][str(horizon)]
    return f"{pct(forecast['p25'])} / {pct(forecast['p50'])} / {pct(forecast['p75'])}"


def run_hmm_screen(
    config: Mapping[str, Any],
    series: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    cfg = normalize_config(config)
    settings = cfg["settings"]
    filters = cfg["filters"]
    results: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for index, item in enumerate(series, 1):
        symbol = str(item.get("symbol") or item.get("product_id") or item.get("coin") or "")
        df = item.get("df")
        meta = dict(item.get("meta") or {})
        meta.setdefault("exchange", item.get("exchange") or cfg["exchange"])
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            reason = meta.get("load_error") or "missing OHLCV data"
            skipped.append({"symbol": symbol, "reason": str(reason)})
            continue
        ok, reason = evaluate_filters(df, meta, filters)
        if not ok:
            skipped.append({"symbol": symbol, "reason": reason})
            continue
        try:
            result = fit_hmm_forecast(
                symbol=symbol,
                df=df,
                meta=meta,
                horizons=settings["horizons"],
                n_states=settings["states"],
                simulations=settings["simulations"],
                seed=settings["seed"] + index,
            )
            if math.isnan(result["score"]):
                skipped.append({"symbol": symbol, "reason": "model produced NaN score"})
                continue
            results.append(result)
        except Exception as exc:
            skipped.append({"symbol": symbol, "reason": str(exc)})

    results.sort(key=lambda row: row["score"], reverse=True)
    return {
        "generated_at": utc_now().isoformat(),
        "settings": {
            "exchange": cfg["exchange"],
            "live": cfg["live"],
            "lookback_days": settings["lookback_days"],
            "freq": settings["freq"],
            "horizons": list(settings["horizons"]),
            "states": settings["states"],
            "simulations": settings["simulations"],
            "filters": filters,
        },
        "results": results,
        "skipped": skipped,
    }


def format_markdown(payload: Mapping[str, Any], title: Optional[str] = None) -> str:
    title = title or "HMM Screener"
    horizons = payload.get("settings", {}).get("horizons") or list(DEFAULT_HORIZONS)
    lines = [
        f"# {title}",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        "Ranges are p25 / p50 / p75 simulated returns from the current HMM state.",
        "This is a probabilistic regime screen, not financial advice or a guarantee.",
        "",
        "| Rank | Symbol | Price | 24h Vol | Avg 30d Vol | "
        + " | ".join(f"{h}d" for h in horizons)
        + " | 60d DD | Score |",
        "| ---: | --- | ---: | ---: | ---: | "
        + " | ".join(["---:"] * len(horizons))
        + " | ---: | ---: |",
    ]
    for rank, item in enumerate(payload.get("results") or [], 1):
        cells = " | ".join(forecast_cell(item, int(h)) for h in horizons)
        lines.append(
            "| "
            f"{rank} | `{item.get('symbol')}` | ${float(item.get('price') or 0):.6g} | "
            f"{money(float(item.get('quote_volume_24h') or 0))} | "
            f"{money(float(item.get('avg_quote_volume_30d') or 0))} | "
            f"{cells} | {pct(float(item.get('max_drawdown_60d') or 0))} | "
            f"{float(item.get('score') or 0):.2f} |"
        )

    lines.extend(
        [
            "",
            "## Practical Read",
            "",
            "- Favor names with positive near-term medians, tolerable p25 downside, and enough volume.",
            "- Treat very high upside as regime instability; size carefully.",
            "- Re-run before trading. A daily-candle HMM can change after one large candle.",
        ]
    )
    warning_count = sum(1 for item in payload.get("results") or [] if item.get("warnings"))
    if warning_count:
        lines.extend(
            [
                "",
                "## Model Warnings",
                "",
                f"{warning_count} result(s) emitted HMM fit warnings. Check the JSON for details.",
            ]
        )
    skipped = payload.get("skipped") or []
    if skipped:
        lines.extend(["", "## Skipped", ""])
        for item in skipped[:25]:
            symbol = item.get("symbol") or item.get("product_id") or item.get("coin")
            lines.append(f"- `{symbol}`: {item.get('reason')}")
    return "\n".join(lines) + "\n"


def write_screen_reports(
    payload: Mapping[str, Any],
    json_out: Optional[str] = None,
    md_out: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    written = {"json_out": None, "md_out": None}
    if json_out:
        path = Path(json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written["json_out"] = str(path)
    if md_out:
        path = Path(md_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_markdown(payload, title=title), encoding="utf-8")
        written["md_out"] = str(path)
    return written
