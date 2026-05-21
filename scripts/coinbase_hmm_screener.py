#!/usr/bin/env python3
"""Run a Coinbase USD-market HMM screener and write JSON/Markdown reports."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler


BASE_URL = "https://api.exchange.coinbase.com"
DEFAULT_HORIZONS = (7, 30, 60)
DEFAULT_PRODUCTS = (
    "ZEC-USD",
    "DASH-USD",
    "VVV-USD",
    "NEAR-USD",
    "INJ-USD",
    "AERO-USD",
    "TAO-USD",
    "SUI-USD",
    "ONDO-USD",
    "PENGU-USD",
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    url = f"{BASE_URL}{path}"
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_products() -> list[dict[str, Any]]:
    products = request_json("/products")
    return [p for p in products if p.get("quote_currency") == "USD" and p.get("status") == "online"]


def fetch_ticker(product_id: str) -> dict[str, float]:
    ticker = request_json(f"/products/{product_id}/ticker")
    price = float(ticker.get("price") or 0.0)
    base_volume = float(ticker.get("volume") or 0.0)
    return {
        "price": price,
        "base_volume_24h": base_volume,
        "quote_volume_24h": price * base_volume,
    }


def candle_cache_path(cache_dir: Path, product_id: str, granularity: int) -> Path:
    safe_name = product_id.replace("-", "_")
    suffix = "1d" if granularity == 86400 else f"{granularity}s"
    return cache_dir / f"{safe_name}_{suffix}.parquet"


def load_cached_candles(cache_dir: Path, product_id: str, granularity: int, max_age_hours: float) -> pd.DataFrame | None:
    path = candle_cache_path(cache_dir, product_id, granularity)
    if not path.exists():
        return None
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    if age_hours > max_age_hours:
        return None
    return pd.read_parquet(path)


def fetch_candles(product_id: str, days: int, granularity: int, cache_dir: Path, max_age_hours: float) -> pd.DataFrame:
    cached = load_cached_candles(cache_dir, product_id, granularity, max_age_hours)
    if cached is not None and len(cached) >= min(days, 30):
        return cached

    cache_dir.mkdir(parents=True, exist_ok=True)
    end = utc_now().replace(minute=0, second=0, microsecond=0)
    start = end - dt.timedelta(days=days)
    candles: list[list[float]] = []
    current = start
    max_points = 290
    step = dt.timedelta(seconds=granularity * max_points)

    while current < end:
        chunk_end = min(current + step, end)
        params = {
            "granularity": granularity,
            "start": current.isoformat(),
            "end": chunk_end.isoformat(),
        }
        chunk = request_json(f"/products/{product_id}/candles", params=params)
        candles.extend(chunk)
        current = chunk_end
        time.sleep(0.12)

    if not candles:
        raise RuntimeError(f"No candles returned for {product_id}")

    df = pd.DataFrame(candles, columns=["date", "low", "high", "open", "close", "volume"])
    df = df.drop_duplicates(subset=["date"]).sort_values("date")
    df["date"] = pd.to_datetime(df["date"], unit="s", utc=True)
    df = df.set_index("date")
    df = df.astype(float)
    df.to_parquet(candle_cache_path(cache_dir, product_id, granularity))
    return df


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    features = pd.DataFrame(index=df.index)
    features["ret"] = close.pct_change().fillna(0.0)
    features["vol"] = features["ret"].rolling(20).std().fillna(0.0)
    features["range"] = ((df["high"] - df["low"]) / close).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    features["trend"] = close.pct_change(20).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    running_high = close.cummax()
    features["drawdown"] = ((close / running_high) - 1.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)
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
    horizons: tuple[int, ...],
    simulations: int,
    rng: np.random.Generator,
) -> dict[int, dict[str, float]]:
    state_returns = {
        state: returns.iloc[np.where(states == state)[0]].dropna().to_numpy()
        for state in range(model.n_components)
    }
    all_returns = returns.dropna().to_numpy()
    current_state = int(states[-1])
    max_horizon = max(horizons)
    results: dict[int, dict[str, float]] = {}
    horizon_values = {h: [] for h in horizons}

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


def fit_hmm_forecast(
    product_id: str,
    df: pd.DataFrame,
    ticker: dict[str, float],
    horizons: tuple[int, ...],
    n_states: int,
    simulations: int,
    seed: int,
) -> dict[str, Any]:
    if len(df) < 90:
        raise RuntimeError(f"{product_id} has too little candle history: {len(df)} rows")

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
    expected_daily = float(np.average(model.means_[:, 0], weights=model.predict_proba(x)[-1]))
    score = forecasts.get(30, {}).get("p50", 0.0) * 100 + forecasts.get(60, {}).get("p50", 0.0) * 50
    score += forecasts.get(30, {}).get("p25", 0.0) * 100

    return {
        "product_id": product_id,
        "price": ticker["price"],
        "quote_volume_24h": ticker["quote_volume_24h"],
        "avg_quote_volume_30d": avg_quote_volume(df, 30),
        "candles": int(len(df)),
        "current_state": int(states[-1]),
        "expected_daily_return": expected_daily,
        "max_drawdown_60d": max_drawdown(df, 60),
        "forecasts": {str(k): v for k, v in forecasts.items()},
        "score": float(score),
        "warnings": sorted({str(w.message) for w in caught}),
    }


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


def forecast_cell(item: dict[str, Any], horizon: int) -> str:
    forecast = item["forecasts"][str(horizon)]
    return f"{pct(forecast['p25'])} / {pct(forecast['p50'])} / {pct(forecast['p75'])}"


def write_reports(results: list[dict[str, Any]], args: argparse.Namespace, skipped: list[dict[str, str]]) -> None:
    payload = {
        "generated_at": utc_now().isoformat(),
        "settings": {
            "lookback_days": args.lookback_days,
            "horizons": list(args.horizons),
            "states": args.states,
            "simulations": args.simulations,
            "min_quote_volume_24h": args.min_quote_volume_24h,
            "min_avg_quote_volume_30d": args.min_avg_quote_volume_30d,
            "max_drawdown_60d": args.max_drawdown_60d,
        },
        "results": results,
        "skipped": skipped,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Coinbase HMM Screener",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "Ranges are p25 / p50 / p75 simulated returns from the current HMM state.",
        "This is a probabilistic regime screen, not financial advice or a guarantee.",
        "",
        "| Rank | Product | Price | 24h Vol | Avg 30d Vol | 7d | 30d | 60d | 60d DD | Score |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, item in enumerate(results, 1):
        lines.append(
            "| "
            f"{rank} | `{item['product_id']}` | ${item['price']:.6g} | "
            f"{money(item['quote_volume_24h'])} | {money(item['avg_quote_volume_30d'])} | "
            f"{forecast_cell(item, 7)} | {forecast_cell(item, 30)} | {forecast_cell(item, 60)} | "
            f"{pct(item['max_drawdown_60d'])} | {item['score']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Practical Read",
            "",
            "- Favor names with positive 7d and 30d medians, tolerable p25 downside, and enough volume.",
            "- Treat very high upside as regime instability; cap position size and avoid averaging down blindly.",
            "- Re-run before trading. A daily-candle HMM can change materially after a single large candle.",
        ]
    )
    warning_count = sum(1 for item in results if item["warnings"])
    if warning_count:
        lines.extend(
            [
                "",
                "## Model Warnings",
                "",
                f"{warning_count} result(s) emitted HMM fit warnings. Check the JSON for exact warning text.",
            ]
        )
    if skipped:
        lines.extend(["", "## Skipped", ""])
        for item in skipped[:25]:
            lines.append(f"- `{item['product_id']}`: {item['reason']}")

    args.md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Coinbase USD-market HMM forecast screener.")
    parser.add_argument(
        "--product",
        action="append",
        dest="products",
        help="Coinbase product id to screen; repeatable.",
    )
    parser.add_argument(
        "--auto-universe",
        action="store_true",
        help="Screen liquid USD products instead of the default shortlist.",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=40,
        help="Maximum liquid products to model in auto-universe mode.",
    )
    parser.add_argument("--lookback-days", type=int, default=260, help="Daily candle lookback.")
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=list(DEFAULT_HORIZONS),
        help="Forecast horizons in days.",
    )
    parser.add_argument("--states", type=int, default=3, help="Hidden states in the Gaussian HMM.")
    parser.add_argument("--simulations", type=int, default=5000, help="Monte Carlo paths per product.")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed.")
    parser.add_argument("--cache-dir", type=Path, default=Path("reports/coinbase_hmm_forecast_data"))
    parser.add_argument("--cache-max-age-hours", type=float, default=6.0)
    parser.add_argument("--json-out", type=Path, default=Path("reports/coinbase_hmm_7_30_60_forecast.json"))
    parser.add_argument("--md-out", type=Path, default=Path("reports/coinbase_hmm_7_30_60_forecast.md"))
    parser.add_argument("--min-candles", type=int, default=180)
    parser.add_argument("--min-quote-volume-24h", type=float, default=3_000_000)
    parser.add_argument("--min-avg-quote-volume-30d", type=float, default=3_000_000)
    parser.add_argument("--max-drawdown-60d", type=float, default=-0.45)
    return parser.parse_args()


def choose_universe(args: argparse.Namespace) -> list[str]:
    if args.products:
        return sorted(set(args.products))
    if not args.auto_universe:
        return list(DEFAULT_PRODUCTS)

    candidates = []
    for product in fetch_products():
        product_id = product["id"]
        try:
            ticker = fetch_ticker(product_id)
        except Exception:
            continue
        if ticker["quote_volume_24h"] >= args.min_quote_volume_24h:
            candidates.append((product_id, ticker["quote_volume_24h"]))
        time.sleep(0.05)
    candidates.sort(key=lambda item: item[1], reverse=True)
    return [product_id for product_id, _ in candidates[: args.max_products]]


def main() -> int:
    args = parse_args()
    args.horizons = tuple(sorted(set(args.horizons)))
    products = choose_universe(args)
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for index, product_id in enumerate(products, 1):
        print(f"[{index}/{len(products)}] Screening {product_id}")
        try:
            ticker = fetch_ticker(product_id)
            if ticker["quote_volume_24h"] < args.min_quote_volume_24h:
                skipped.append({"product_id": product_id, "reason": "below 24h quote volume threshold"})
                continue
            df = fetch_candles(product_id, args.lookback_days, 86400, args.cache_dir, args.cache_max_age_hours)
            if len(df) < args.min_candles:
                skipped.append({"product_id": product_id, "reason": f"only {len(df)} candles"})
                continue
            avg_vol = avg_quote_volume(df, 30)
            if avg_vol < args.min_avg_quote_volume_30d:
                skipped.append({"product_id": product_id, "reason": "below 30d average quote volume threshold"})
                continue
            dd60 = max_drawdown(df, 60)
            if dd60 < args.max_drawdown_60d:
                skipped.append({"product_id": product_id, "reason": f"60d drawdown {pct(dd60)}"})
                continue
            result = fit_hmm_forecast(
                product_id,
                df,
                ticker,
                args.horizons,
                args.states,
                args.simulations,
                args.seed + index,
            )
            if math.isnan(result["score"]):
                skipped.append({"product_id": product_id, "reason": "model produced NaN score"})
                continue
            results.append(result)
        except Exception as exc:
            skipped.append({"product_id": product_id, "reason": str(exc)})

    results.sort(key=lambda item: item["score"], reverse=True)
    write_reports(results, args, skipped)
    print(f"Wrote {args.md_out}")
    print(f"Wrote {args.json_out}")
    print(f"Screened {len(results)} product(s), skipped {len(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
