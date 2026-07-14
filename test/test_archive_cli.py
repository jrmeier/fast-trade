import datetime
from unittest import mock

import pytest

from fast_trade.archive import cli


def test_get_assets_binanceus():
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=["BBB", "AAA"],
    ):
        assert cli.get_assets("binanceus") == ["AAA", "BBB"]


def test_get_assets_binancecom():
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=["BTCUSDT"],
    ) as symbols_mock:
        assert cli.get_assets("binancecom") == ["BTCUSDT"]
    symbols_mock.assert_called_once_with(tld="com")


def test_get_assets_coinbase():
    with mock.patch(
        "fast_trade.archive.cli.coinbase_api.get_asset_ids",
        return_value=["BTC-USD"],
    ):
        assert cli.get_assets("coinbase") == ["BTC-USD"]


def test_get_assets_local():
    with mock.patch(
        "fast_trade.archive.cli.get_local_assets",
        return_value=[("binanceus", "ZZZ"), ("coinbase", "AAA")],
    ):
        assert cli.get_assets("local") == [("binanceus", "ZZZ"), ("coinbase", "AAA")]


def test_get_assets_unsupported():
    with pytest.raises(ValueError, match="not supported"):
        cli.get_assets("kraken")


def test_get_assets_reraises_exception():
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        side_effect=RuntimeError("api down"),
    ):
        with pytest.raises(RuntimeError, match="api down"):
            cli.get_assets("binanceus")


def test_download_asset_binanceus_success():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc)
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=["BTCUSDT"],
    ), mock.patch(
        "fast_trade.archive.cli.update_kline", return_value="/tmp/BTCUSDT.parquet"
    ) as update_mock:
        path = cli.download_asset("BTCUSDT", "binanceus", start, end)

    assert path == "/tmp/BTCUSDT.parquet"
    update_mock.assert_called_once_with(
        "BTCUSDT", "binanceus", start, end, progress_callback=None
    )


def test_download_asset_binancecom_success():
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=["BTCUSDT"],
    ) as symbols_mock, mock.patch(
        "fast_trade.archive.cli.update_kline", return_value="/tmp/BTCUSDT.parquet"
    ):
        cli.download_asset("BTCUSDT", "binancecom")

    symbols_mock.assert_called_once_with(tld="com")


def test_download_asset_coinbase_success():
    with mock.patch(
        "fast_trade.archive.cli.coinbase_api.get_asset_ids",
        return_value=["BTC-USD"],
    ), mock.patch("fast_trade.archive.cli.update_kline", return_value="/tmp/BTC-USD.parquet"):
        path = cli.download_asset("BTC-USD", "coinbase")
    assert path.endswith(".parquet")


def test_download_asset_parses_iso_strings():
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=["BTCUSDT"],
    ), mock.patch("fast_trade.archive.cli.update_kline", return_value="/tmp/x.parquet") as update_mock:
        cli.download_asset(
            "BTCUSDT",
            "binanceus",
            start="2024-01-01T00:00:00",
            end="2024-01-02T00:00:00",
        )

    start = update_mock.call_args[0][2]
    end = update_mock.call_args[0][3]
    assert start.tzinfo == datetime.timezone.utc
    assert end.tzinfo == datetime.timezone.utc


def test_download_asset_symbol_not_found_binanceus():
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=["ETHUSDT"],
    ):
        with pytest.raises(ValueError, match="not found on Binance US"):
            cli.download_asset("BTCUSDT", "binanceus")


def test_download_asset_symbol_not_found_binancecom():
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=[],
    ):
        with pytest.raises(ValueError, match="not found on Binance COM"):
            cli.download_asset("BTCUSDT", "binancecom")


def test_download_asset_symbol_not_found_coinbase():
    with mock.patch(
        "fast_trade.archive.cli.coinbase_api.get_asset_ids",
        return_value=["ETH-USD"],
    ):
        with pytest.raises(ValueError, match="not found on Coinbase"):
            cli.download_asset("BTC-USD", "coinbase")


def test_download_asset_unsupported_exchange():
    with pytest.raises(ValueError, match="not supported"):
        cli.download_asset("BTCUSDT", "kraken")


def test_download_asset_progress_callback():
    callback = mock.Mock()
    with mock.patch(
        "fast_trade.archive.cli.binance_api.get_available_symbols",
        return_value=["BTCUSDT"],
    ), mock.patch("fast_trade.archive.cli.update_kline", return_value="/tmp/x.parquet") as update_mock:
        cli.download_asset("BTCUSDT", "binanceus", progress_callback=callback)

    assert update_mock.call_args[1]["progress_callback"] is callback
