"""Data loaders for HMM screening (archive-first, optional live fetch)."""

from __future__ import annotations

import datetime as dt
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import polars as pl
import requests

from fast_trade.archive.db_helpers import ARCHIVE_PATH
from fast_trade.ml.hmm_screen import normalize_config


COINBASE_BASE_URL = "https://api.exchange.coinbase.com"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _empty_ohlcv() -> pl.DataFrame:
    return pl.DataFrame(
        schema={"date": pl.Datetime(time_zone="UTC"), **{name: pl.Float64 for name in OHLCV_COLUMNS}}
    )


def _safe_read_parquet(path: str) -> Optional[pl.DataFrame]:
    try:
        return pl.read_parquet(path)
    except Exception:
        return None


def _date_expression(df: pl.DataFrame) -> pl.Expr:
    dtype = df.schema["date"]
    column = pl.col("date")
    if dtype.is_integer():
        values = df["date"].drop_nulls()
        maximum = abs(float(values.max() or 0))
        unit = "ms" if maximum >= 100_000_000_000 else "s"
        return pl.from_epoch(column.cast(pl.Int64), time_unit=unit).dt.replace_time_zone("UTC")
    if dtype == pl.Date:
        return column.cast(pl.Datetime).dt.replace_time_zone("UTC")
    if isinstance(dtype, pl.Datetime):
        if dtype.time_zone:
            return column.dt.convert_time_zone("UTC")
        return column.dt.replace_time_zone("UTC")
    return column.cast(pl.String).str.to_datetime(strict=False, time_zone="UTC")


def _ensure_ohlcv(df: pl.DataFrame) -> pl.DataFrame:
    if df is None or not isinstance(df, pl.DataFrame) or df.is_empty():
        return _empty_ohlcv()
    if "date" not in df.columns:
        raise ValueError("OHLCV requires an explicit date column")
    missing = [col for col in OHLCV_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    return (
        df.with_columns(_date_expression(df).alias("date"))
        .with_columns([pl.col(name).cast(pl.Float64, strict=False).alias(name) for name in OHLCV_COLUMNS])
        .drop_nulls(["date", *OHLCV_COLUMNS])
        .unique(subset=["date"], keep="last")
        .sort("date")
        .select("date", *OHLCV_COLUMNS)
    )


def _polars_duration(freq: str) -> str:
    value = str(freq).strip()
    match = re.fullmatch(r"(\d+)\s*([A-Za-z]+)", value)
    if not match:
        return value.lower()
    amount, unit = match.groups()
    units = {
        "s": "s",
        "sec": "s",
        "second": "s",
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


def load_archive_candles(
    symbol: str,
    exchange: str,
    lookback_days: int = 260,
    freq: str = "1D",
) -> pl.DataFrame:
    """Load local archive candles without auto-downloading."""
    parquet_path = os.path.join(ARCHIVE_PATH, exchange, f"{symbol}.parquet")
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(
            f"No archive data for {exchange}/{symbol} at {parquet_path}. "
            "Run `ft download` first or pass live=True."
        )
    df = _safe_read_parquet(parquet_path)
    if df is None or df.is_empty():
        raise RuntimeError(f"Archive parquet unreadable or empty: {parquet_path}")
    df = _ensure_ohlcv(df)
    if lookback_days:
        start = utc_now() - dt.timedelta(days=int(lookback_days))
        df = df.filter(pl.col("date") >= start)
    if freq:
        df = (
            df.group_by_dynamic("date", every=_polars_duration(freq))
            .agg(
                pl.col("open").first(),
                pl.col("high").max(),
                pl.col("low").min(),
                pl.col("close").last(),
                pl.col("volume").sum(),
            )
            .drop_nulls(OHLCV_COLUMNS)
            .sort("date")
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
) -> pl.DataFrame:
    cache_dir = Path(cache_dir or "ft_archive/screen_cache/coinbase")
    cache_path = _candle_cache_path(
        cache_dir, product_id, "1d" if granularity == 86400 else f"{granularity}s"
    )
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= cache_max_age_hours:
            cached = _safe_read_parquet(str(cache_path))
            if cached is not None:
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

    df = pl.DataFrame(
        candles,
        schema=["date", "low", "high", "open", "close", "volume"],
        orient="row",
    ).with_columns(pl.from_epoch(pl.col("date").cast(pl.Int64), time_unit="s").dt.replace_time_zone("UTC"))
    df = _ensure_ohlcv(df)
    df.write_parquet(cache_path)
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
) -> pl.DataFrame:
    cache_dir = Path(cache_dir or "ft_archive/screen_cache/hyperliquid")
    cache_path = _candle_cache_path(cache_dir, coin, interval)
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= cache_max_age_hours:
            cached = _safe_read_parquet(str(cache_path))
            if cached is not None:
                return _ensure_ohlcv(cached)

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

    df = pl.DataFrame(candles).rename(
        {
            "t": "date",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "n": "trades",
        }
    )
    df = df.with_columns(
        pl.from_epoch(pl.col("date").cast(pl.Int64), time_unit="ms").dt.replace_time_zone("UTC")
    )
    df = _ensure_ohlcv(df)
    df.write_parquet(cache_path)
    return df


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
                    if "price" not in meta and not df.is_empty():
                        meta["price"] = float(df["close"][-1])
            except Exception as exc:
                series.append(
                    {
                        "symbol": symbol,
                        "exchange": exchange,
                        "df": _empty_ohlcv(),
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
                if "price" not in meta and not df.is_empty():
                    meta["price"] = float(df["close"][-1])
                    meta["quote_volume_24h"] = float(df["close"][-1] * df["volume"][-1])
        except Exception as exc:
            series.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "df": _empty_ohlcv(),
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
