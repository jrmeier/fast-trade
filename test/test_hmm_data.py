import datetime as dt
import os
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from fast_trade.ml import hmm_data


def _ohlcv(rows: int = 120, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=rows, freq="D")
    close = 100 * np.cumprod(1.0 + rng.normal(0.001, 0.02, size=rows))
    high = close * 1.01
    low = close * 0.99
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(1000, 5000, size=rows)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_utc_now():
    assert hmm_data.utc_now().tzinfo is not None


def test_ensure_ohlcv_branches():
    assert hmm_data._ensure_ohlcv(None).empty
    assert hmm_data._ensure_ohlcv(pd.DataFrame()).empty

    dated = _ohlcv(5).reset_index().rename(columns={"index": "date"})
    out = hmm_data._ensure_ohlcv(dated)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]

    with pytest.raises(ValueError, match="missing columns"):
        hmm_data._ensure_ohlcv(pd.DataFrame({"close": [1.0]}))


def test_load_archive_candles(tmp_path, monkeypatch):
    exchange = "coinbase"
    symbol = "BTC-USD"
    archive = tmp_path / "archive"
    exchange_dir = archive / exchange
    exchange_dir.mkdir(parents=True)
    df = _ohlcv(30)
    df.to_parquet(exchange_dir / f"{symbol}.parquet")

    monkeypatch.setattr(hmm_data, "ARCHIVE_PATH", str(archive))
    loaded = hmm_data.load_archive_candles(symbol, exchange, lookback_days=365, freq="1D")
    assert len(loaded) == 30

    with pytest.raises(FileNotFoundError):
        hmm_data.load_archive_candles("MISSING", exchange)

    monkeypatch.setattr(hmm_data, "_safe_read_parquet", lambda _path: None)
    with pytest.raises(RuntimeError, match="unreadable"):
        hmm_data.load_archive_candles(symbol, exchange)


def test_coinbase_request_and_ticker(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"price": "10.5", "volume": "2.0"}

    monkeypatch.setattr(hmm_data.requests, "get", lambda *a, **k: FakeResponse())
    ticker = hmm_data.fetch_coinbase_ticker("BTC-USD")
    assert ticker["price"] == 10.5
    assert ticker["quote_volume_24h"] == 21.0


def test_fetch_coinbase_products(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"id": "BTC-USD", "quote_currency": "USD", "status": "online"},
                {"id": "BTC-EUR", "quote_currency": "EUR", "status": "online"},
                {"id": "ETH-USD", "quote_currency": "USD", "status": "offline"},
            ]

    monkeypatch.setattr(hmm_data.requests, "get", lambda *a, **k: FakeResponse())
    assert hmm_data.fetch_coinbase_products() == ["BTC-USD"]


def test_candle_cache_path():
    path = hmm_data._candle_cache_path(Path("/cache"), "BTC-USD", "1d")
    assert path.name == "BTC_USD_1d.parquet"


def test_fetch_coinbase_candles_cache_hit(tmp_path, monkeypatch):
    df = _ohlcv(10)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_path = hmm_data._candle_cache_path(cache_dir, "BTC-USD", "1d")
    df.to_parquet(cache_path)

    monkeypatch.setattr(hmm_data.time, "time", lambda: cache_path.stat().st_mtime)
    loaded = hmm_data.fetch_coinbase_candles(
        "BTC-USD", cache_dir=cache_dir, cache_max_age_hours=24.0
    )
    assert len(loaded) == 10


def test_fetch_coinbase_candles_live_fetch(tmp_path, monkeypatch):
    now = dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(hmm_data, "utc_now", lambda: now)
    monkeypatch.setattr(hmm_data.time, "sleep", lambda _s: None)

    ts = int(now.timestamp()) - 86400

    def fake_request(path, params=None, timeout=30):
        return [[ts, 99.0, 101.0, 100.0, 100.5, 1000.0]]

    monkeypatch.setattr(hmm_data, "_coinbase_request", fake_request)
    df = hmm_data.fetch_coinbase_candles("BTC-USD", lookback_days=1, cache_dir=tmp_path / "cb")
    assert not df.empty

    monkeypatch.setattr(hmm_data, "_coinbase_request", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="No candles"):
        hmm_data.fetch_coinbase_candles("BTC-USD", lookback_days=1, cache_dir=tmp_path / "cb2")


def test_hyperliquid_helpers(monkeypatch, tmp_path):
    def fake_post(payload, timeout=30):
        if payload["type"] == "metaAndAssetCtxs":
            return (
                {
                    "universe": [
                        {"name": "BTC", "maxLeverage": 20, "isDelisted": False},
                        {"name": "OLD", "isDelisted": True},
                    ]
                },
                [
                    {"markPx": "50000", "dayNtlVlm": "1000000", "openInterest": "10", "funding": "0.01"},
                    {},
                ],
            )
        return [
            {
                "t": 1_700_000_000_000,
                "o": "1",
                "h": "2",
                "l": "0.5",
                "c": "1.5",
                "v": "100",
                "n": 1,
            }
        ]

    monkeypatch.setattr(hmm_data, "_hyperliquid_post", fake_post)
    markets = hmm_data.fetch_hyperliquid_markets()
    assert markets[0]["coin"] == "BTC"
    assert len(markets) == 1

    now = dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(hmm_data, "utc_now", lambda: now)
    monkeypatch.setattr(hmm_data.time, "sleep", lambda _s: None)
    df = hmm_data.fetch_hyperliquid_candles("BTC", lookback_days=1, cache_dir=tmp_path / "hl")
    assert not df.empty

    monkeypatch.setattr(hmm_data, "_hyperliquid_post", lambda payload, timeout=30: [])
    with pytest.raises(RuntimeError, match="No candles"):
        hmm_data.fetch_hyperliquid_candles("BTC", lookback_days=1, cache_dir=tmp_path / "hl2")


def test_fetch_hyperliquid_candles_cache_hit(tmp_path, monkeypatch):
    df = _ohlcv(8)
    cache_dir = tmp_path / "hlcache"
    cache_dir.mkdir()
    cache_path = hmm_data._candle_cache_path(cache_dir, "BTC", "1d")
    df.to_parquet(cache_path)
    monkeypatch.setattr(hmm_data.time, "time", lambda: cache_path.stat().st_mtime)
    loaded = hmm_data.fetch_hyperliquid_candles("BTC", cache_dir=cache_dir, cache_max_age_hours=24.0)
    assert len(loaded) == 8


def test_local_archive_symbols(tmp_path, monkeypatch):
    exchange_dir = tmp_path / "coinbase"
    exchange_dir.mkdir()
    (exchange_dir / "BTC-USD.parquet").write_text("x", encoding="utf-8")
    (exchange_dir / "ETH-USD.sqlite").write_text("x", encoding="utf-8")
    (exchange_dir / "_meta.json").write_text("x", encoding="utf-8")
    monkeypatch.setattr(hmm_data, "ARCHIVE_PATH", str(tmp_path))
    assert hmm_data._local_archive_symbols("coinbase") == ["BTC-USD", "ETH-USD"]
    assert hmm_data._local_archive_symbols("missing") == []


def test_load_universe_coinbase_archive(tmp_path, monkeypatch):
    exchange = "coinbase"
    symbol = "BTC-USD"
    archive = tmp_path / "archive"
    exchange_dir = archive / exchange
    exchange_dir.mkdir(parents=True)
    _ohlcv(100).to_parquet(exchange_dir / f"{symbol}.parquet")
    monkeypatch.setattr(hmm_data, "ARCHIVE_PATH", str(archive))

    series = hmm_data.load_universe({"exchange": exchange, "symbols": [symbol]})
    assert len(series) == 1
    assert series[0]["symbol"] == symbol
    assert not series[0]["df"].empty
    assert "price" in series[0]["meta"]


def test_load_universe_coinbase_live(monkeypatch):
    df = _ohlcv(100)

    monkeypatch.setattr(hmm_data, "fetch_coinbase_products", lambda: ["BTC-USD", "ETH-USD"])
    monkeypatch.setattr(
        hmm_data,
        "fetch_coinbase_ticker",
        lambda product_id: {"price": 1.0, "base_volume_24h": 2.0, "quote_volume_24h": 2.0},
    )
    monkeypatch.setattr(hmm_data, "fetch_coinbase_candles", lambda *a, **k: df)

    series = hmm_data.load_universe(
        {"exchange": "coinbase", "live": True, "settings": {"max_products": 1}}
    )
    assert len(series) == 1
    assert series[0]["meta"]["quote_volume_24h"] == 2.0


def test_load_universe_coinbase_load_error(monkeypatch):
    monkeypatch.setattr(hmm_data, "fetch_coinbase_ticker", lambda product_id: {"price": 1.0})
    monkeypatch.setattr(
        hmm_data,
        "fetch_coinbase_candles",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")),
    )
    series = hmm_data.load_universe(
        {"exchange": "coinbase", "symbols": ["BTC-USD"], "live": True}
    )
    assert series[0]["df"].empty
    assert "down" in series[0]["meta"]["load_error"]


def test_load_universe_unsupported_live_exchange():
    series = hmm_data.load_universe({"exchange": "binanceus", "live": True, "symbols": ["BTCUSDT"]})
    assert "only supported" in series[0]["meta"]["load_error"]


def test_load_universe_hyperliquid_archive(tmp_path, monkeypatch):
    exchange = "hyperliquid"
    symbol = "BTC"
    archive = tmp_path / "archive"
    exchange_dir = archive / exchange
    exchange_dir.mkdir(parents=True)
    _ohlcv(100).to_parquet(exchange_dir / f"{symbol}.parquet")
    monkeypatch.setattr(hmm_data, "ARCHIVE_PATH", str(archive))

    series = hmm_data.load_universe({"exchange": exchange, "symbols": [symbol]})
    assert series[0]["symbol"] == symbol
    assert series[0]["meta"]["coin"] == symbol


def test_load_universe_hyperliquid_live(monkeypatch):
    df = _ohlcv(100)
    markets = [
        {
            "coin": "BTC",
            "max_leverage": 20,
            "mark_price": 50000.0,
            "day_ntl_volume": 1_000_000.0,
            "open_interest": 10.0,
            "funding": 0.01,
        }
    ]
    monkeypatch.setattr(hmm_data, "fetch_hyperliquid_markets", lambda: markets)
    monkeypatch.setattr(hmm_data, "fetch_hyperliquid_candles", lambda *a, **k: df)

    series = hmm_data.load_universe(
        {
            "exchange": "hyperliquid",
            "live": True,
            "settings": {"max_products": 5},
            "filters": {"min_quote_volume_24h": 0.0},
        }
    )
    assert series[0]["meta"]["open_interest"] == 10.0


def test_load_universe_hyperliquid_auto_symbols_live(monkeypatch):
    df = _ohlcv(100)
    markets = [
        {
            "coin": "BTC",
            "max_leverage": 20,
            "mark_price": 1.0,
            "day_ntl_volume": 100.0,
            "open_interest": 1.0,
            "funding": 0.0,
        },
        {
            "coin": "ETH",
            "max_leverage": 10,
            "mark_price": 0.0,
            "day_ntl_volume": 50.0,
            "open_interest": 1.0,
            "funding": 0.0,
        },
    ]
    monkeypatch.setattr(hmm_data, "fetch_hyperliquid_markets", lambda: markets)
    monkeypatch.setattr(hmm_data, "fetch_hyperliquid_candles", lambda *a, **k: df)

    series = hmm_data.load_universe(
        {
            "exchange": "hyperliquid",
            "live": True,
            "settings": {"max_products": 5},
            "filters": {"min_quote_volume_24h": 10.0},
        }
    )
    assert len(series) == 1
    assert series[0]["symbol"] == "BTC"


def test_hyperliquid_post_wrapper(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(hmm_data.requests, "post", lambda *a, **k: FakeResponse())
    assert hmm_data._hyperliquid_post({"type": "meta"}) == {"ok": True}


def test_load_universe_auto_symbols_from_archive(tmp_path, monkeypatch):
    exchange = "coinbase"
    archive = tmp_path / "archive"
    exchange_dir = archive / exchange
    exchange_dir.mkdir(parents=True)
    _ohlcv(50).to_parquet(exchange_dir / "BTC-USD.parquet")
    _ohlcv(50, seed=2).to_parquet(exchange_dir / "ETH-USD.parquet")
    monkeypatch.setattr(hmm_data, "ARCHIVE_PATH", str(archive))

    series = hmm_data.load_universe({"exchange": exchange, "settings": {"max_products": 1}})
    assert len(series) == 1

    hl_dir = archive / "hyperliquid"
    hl_dir.mkdir(parents=True)
    _ohlcv(50, seed=3).to_parquet(hl_dir / "BTC.parquet")
    series_hl = hmm_data.load_universe({"exchange": "hyperliquid", "settings": {"max_products": 2}})
    assert len(series_hl) == 1


def test_load_universe_hyperliquid_error(monkeypatch):
    monkeypatch.setattr(hmm_data, "fetch_hyperliquid_markets", lambda: [])
    monkeypatch.setattr(
        hmm_data,
        "load_archive_candles",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )
    series = hmm_data.load_universe({"exchange": "hyperliquid", "symbols": ["BTC"]})
    assert "missing" in series[0]["meta"]["load_error"]
