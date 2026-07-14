"""Data loaders for HMM screening (archive-first, optional live fetch)."""

from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd
import requests

from fast_trade.archive.db_helpers import ARCHIVE_PATH, _safe_read_parquet
from fast_trade.ml.hmm_screen import normalize_config


COINBASE_BASE_URL = "https://api.exchange.coinbase.com"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], utc=True)
        out = out.set_index("date")
    out.index = pd.to_datetime(out.index, utc=True)
    out = out.sort_index()
    required = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    return out[required].astype(float)


def load_archive_candles(
    symbol: str,
    exchange: str,
    lookback_days: int = 260,
    freq: str = "1D",
) -> pd.DataFrame:
    """Load local archive candles without auto-downloading."""
    parquet_path = os.path.join(ARCHIVE_PATH, exchange, f"{symbol}.parquet")
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(
            f"No archive data for {exchange}/{symbol} at {parquet_path}. "
            "Run `ft download` first or pass live=True."
        )
    df = _safe_read_parquet(parquet_path)
    if df is None or df.empty:
        raise RuntimeError(f"Archive parquet unreadable or empty: {parquet_path}")
    df = _ensure_ohlcv(df)
    if lookback_days:
        start = utc_now() - dt.timedelta(days=int(lookback_days))
        df = df[df.index >= start]
    if freq:
        df = (
            df.resample(freq)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )
    return df


def _coinbase_request(path: str, params: Optional[dict] = None, timeout: int = 30) -> Any:
    response = requests.get(f"{COINBASE_BASE_URL}{path}", params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_coinbase_ticker(product_id: str) -> Dict[str, float]:
    ticker = _coinbase_request(f"/products/{product_id}/ticker")
    price = float(ticker.get("price") or 0.0)
    base_volume = float(ticker.get("volume") or 0.0)
    return {
        "price": price,
        "base_volume_24h": base_volume,
        "quote_volume_24h": price * base_volume,
    }


def fetch_coinbase_products() -> List[str]:
    products = _coinbase_request("/products")
    return [
        p["id"]
        for p in products
        if p.get("quote_currency") == "USD" and p.get("status") == "online"
    ]


def _candle_cache_path(cache_dir: Path, symbol: str, suffix: str) -> Path:
    safe = symbol.replace("-", "_").replace("/", "_")
    return cache_dir / f"{safe}_{suffix}.parquet"


def fetch_coinbase_candles(
    product_id: str,
    lookback_days: int = 260,
    granularity: int = 86400,
    cache_dir: Optional[Path] = None,
    cache_max_age_hours: float = 6.0,
) -> pd.DataFrame:
    cache_dir = Path(cache_dir or "ft_archive/screen_cache/coinbase")
    cache_path = _candle_cache_path(
        cache_dir, product_id, "1d" if granularity == 86400 else f"{granularity}s"
    )
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= cache_max_age_hours:
            cached = pd.read_parquet(cache_path)
            return _ensure_ohlcv(cached)

    cache_dir.mkdir(parents=True, exist_ok=True)
    end = utc_now().replace(minute=0, second=0, microsecond=0)
    start = end - dt.timedelta(days=lookback_days)
    candles: List[list] = []
    current = start
    max_points = 290
    step = dt.timedelta(seconds=granularity * max_points)
    while current < end:
        chunk_end = min(current + step, end)
        chunk = _coinbase_request(
            f"/products/{product_id}/candles",
            params={
                "granularity": granularity,
                "start": current.isoformat(),
                "end": chunk_end.isoformat(),
            },
        )
        candles.extend(chunk)
        current = chunk_end
        time.sleep(0.12)

    if not candles:
        raise RuntimeError(f"No candles returned for {product_id}")

    df = pd.DataFrame(candles, columns=["date", "low", "high", "open", "close", "volume"])
    df = df.drop_duplicates(subset=["date"]).sort_values("date")
    df["date"] = pd.to_datetime(df["date"], unit="s", utc=True)
    df = df.set_index("date").astype(float)
    df.to_parquet(cache_path)
    return df


def _hyperliquid_post(payload: dict, timeout: int = 30) -> Any:
    response = requests.post(HYPERLIQUID_INFO_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_hyperliquid_markets() -> List[Dict[str, Any]]:
    meta, contexts = _hyperliquid_post({"type": "metaAndAssetCtxs"})
    rows = []
    for asset, context in zip(meta["universe"], contexts):
        if asset.get("isDelisted"):
            continue
        rows.append(
            {
                "coin": asset["name"],
                "max_leverage": int(asset.get("maxLeverage") or 0),
                "mark_price": float(context.get("markPx") or 0.0),
                "day_ntl_volume": float(context.get("dayNtlVlm") or 0.0),
                "open_interest": float(context.get("openInterest") or 0.0),
                "funding": float(context.get("funding") or 0.0),
            }
        )
    rows.sort(key=lambda row: row["day_ntl_volume"], reverse=True)
    return rows


def fetch_hyperliquid_candles(
    coin: str,
    lookback_days: int = 260,
    interval: str = "1d",
    cache_dir: Optional[Path] = None,
    cache_max_age_hours: float = 6.0,
) -> pd.DataFrame:
    cache_dir = Path(cache_dir or "ft_archive/screen_cache/hyperliquid")
    cache_path = _candle_cache_path(cache_dir, coin, interval)
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= cache_max_age_hours:
            return _ensure_ohlcv(pd.read_parquet(cache_path))

    cache_dir.mkdir(parents=True, exist_ok=True)
    end_ms = int(utc_now().timestamp() * 1000)
    start_ms = int((utc_now() - dt.timedelta(days=lookback_days)).timestamp() * 1000)
    candles = _hyperliquid_post(
        {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
            },
        }
    )
    if not candles:
        raise RuntimeError(f"No candles returned for {coin}")

    df = pd.DataFrame(candles).rename(
        columns={
            "t": "date",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "n": "trades",
        }
    )
    df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True)
    df = df.set_index("date").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df.to_parquet(cache_path)
    return df[["open", "high", "low", "close", "volume"]]


def _local_archive_symbols(exchange: str) -> List[str]:
    exchange_path = os.path.join(ARCHIVE_PATH, exchange)
    if not os.path.isdir(exchange_path):
        return []
    symbols = []
    for name in os.listdir(exchange_path):
        if name.startswith("_"):
            continue
        if name.endswith(".parquet"):
            symbols.append(name[: -len(".parquet")])
        elif name.endswith(".sqlite"):
            symbols.append(name[: -len(".sqlite")])
    return sorted(symbols)


def load_universe(config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Resolve configured symbols into [{symbol, exchange, df, meta}, ...]."""
    cfg = normalize_config(config)
    exchange = cfg["exchange"]
    settings = cfg["settings"]
    symbols = [str(s) for s in cfg["symbols"]]
    live = bool(cfg["live"])
    cache_dir = settings.get("cache_dir")
    series: List[Dict[str, Any]] = []

    if exchange == "hyperliquid":
        markets = fetch_hyperliquid_markets() if live else []
        if not symbols:
            if live:
                symbols = [
                    m["coin"]
                    for m in markets
                    if m["day_ntl_volume"] >= float(cfg["filters"].get("min_quote_volume_24h") or 0)
                    and m["mark_price"] > 0
                ][: settings["max_products"]]
            else:
                symbols = _local_archive_symbols(exchange)[: settings["max_products"]]
        market_by_coin = {m["coin"].upper(): m for m in markets}
        for symbol in symbols:
            meta: Dict[str, Any] = {"exchange": exchange, "coin": symbol}
            market = market_by_coin.get(symbol.upper())
            if market:
                meta.update(
                    {
                        "price": market["mark_price"],
                        "day_notional_volume": market["day_ntl_volume"],
                        "quote_volume_24h": market["day_ntl_volume"],
                        "open_interest": market["open_interest"],
                        "funding": market["funding"],
                        "max_leverage": market["max_leverage"],
                    }
                )
            try:
                if live:
                    df = fetch_hyperliquid_candles(
                        symbol,
                        lookback_days=settings["lookback_days"],
                        cache_dir=Path(cache_dir) if cache_dir else None,
                        cache_max_age_hours=settings["cache_max_age_hours"],
                    )
                else:
                    df = load_archive_candles(
                        symbol,
                        exchange,
                        lookback_days=settings["lookback_days"],
                        freq=settings["freq"],
                    )
                    if "price" not in meta and not df.empty:
                        meta["price"] = float(df["close"].iloc[-1])
            except Exception as exc:
                series.append(
                    {
                        "symbol": symbol,
                        "exchange": exchange,
                        "df": pd.DataFrame(),
                        "meta": {**meta, "load_error": str(exc)},
                    }
                )
                continue
            series.append({"symbol": symbol, "exchange": exchange, "df": df, "meta": meta})
        return series

    # coinbase / binance* / generic archive exchanges
    if not symbols:
        if live and exchange == "coinbase":
            symbols = fetch_coinbase_products()[: settings["max_products"]]
        else:
            symbols = _local_archive_symbols(exchange)[: settings["max_products"]]

    for symbol in symbols:
        meta: Dict[str, Any] = {"exchange": exchange, "product_id": symbol}
        try:
            if live and exchange == "coinbase":
                ticker = fetch_coinbase_ticker(symbol)
                meta.update(ticker)
                df = fetch_coinbase_candles(
                    symbol,
                    lookback_days=settings["lookback_days"],
                    cache_dir=Path(cache_dir) if cache_dir else None,
                    cache_max_age_hours=settings["cache_max_age_hours"],
                )
            elif live and exchange not in ("coinbase", "hyperliquid"):
                raise ValueError(
                    f"live=True is only supported for coinbase and hyperliquid; got {exchange}"
                )
            else:
                df = load_archive_candles(
                    symbol,
                    exchange,
                    lookback_days=settings["lookback_days"],
                    freq=settings["freq"],
                )
                if "price" not in meta and not df.empty:
                    meta["price"] = float(df["close"].iloc[-1])
                    meta["quote_volume_24h"] = float(df["close"].iloc[-1] * df["volume"].iloc[-1])
        except Exception as exc:
            series.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "df": pd.DataFrame(),
                    "meta": {**meta, "load_error": str(exc)},
                }
            )
            continue
        series.append({"symbol": symbol, "exchange": exchange, "df": df, "meta": meta})
    return series


def screen_from_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Load universe from config and run the HMM screen."""
    from fast_trade.ml.hmm_screen import run_hmm_screen, write_screen_reports

    cfg = normalize_config(config)
    series = load_universe(cfg)
    payload = run_hmm_screen(cfg, series)
    outputs = cfg["outputs"]
    write_screen_reports(
        payload,
        json_out=outputs.get("json_out"),
        md_out=outputs.get("md_out"),
        title=outputs.get("title"),
    )
    return payload
