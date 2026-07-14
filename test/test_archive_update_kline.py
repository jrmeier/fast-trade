import datetime
from unittest import mock

import pandas as pd
import pytest

from test.archive_main_runners import run_update_kline_main
from fast_trade.archive import update_kline


def _sample_df():
    return pd.DataFrame(
        {
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [105.0],
            "volume": [1000.0],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )


def test_update_kline_unsupported_exchange():
    with pytest.raises(ValueError, match="not supported"):
        update_kline.update_kline("BTCUSDT", "kraken")


def test_update_kline_binanceus_success():
    status = {"perc_complete": 100}
    with mock.patch(
        "fast_trade.archive.update_kline.get_binance_klines",
        return_value=(_sample_df(), status),
    ) as binance_mock, mock.patch(
        "fast_trade.archive.update_kline.update_klines_to_db", return_value="/tmp/BTCUSDT.parquet"
    ) as store_mock, mock.patch("fast_trade.archive.update_kline.time.sleep"):
        path = update_kline.update_kline("BTCUSDT", "binanceus")

    binance_mock.assert_called_once()
    assert binance_mock.call_args[0][3] == "us"
    store_mock.assert_called_once()
    assert path == "/tmp/BTCUSDT.parquet"


def test_update_kline_binancecom_success():
    with mock.patch(
        "fast_trade.archive.update_kline.get_binance_klines",
        return_value=(_sample_df(), {}),
    ) as binance_mock, mock.patch(
        "fast_trade.archive.update_kline.update_klines_to_db", return_value="/tmp/BTCUSDT.parquet"
    ), mock.patch("fast_trade.archive.update_kline.time.sleep"):
        update_kline.update_kline("BTCUSDT", "binancecom")

    assert binance_mock.call_args[0][3] == "com"


def test_update_kline_coinbase_success():
    with mock.patch(
        "fast_trade.archive.update_kline.get_product_candles",
        return_value=(_sample_df(), {}),
    ) as coinbase_mock, mock.patch(
        "fast_trade.archive.update_kline.update_klines_to_db", return_value="/tmp/BTC-USD.parquet"
    ), mock.patch("fast_trade.archive.update_kline.time.sleep"):
        path = update_kline.update_kline("BTC-USD", "coinbase")

    coinbase_mock.assert_called_once()
    assert path.endswith(".parquet")


def test_update_kline_default_dates_and_caps_end_to_now():
    captured = {}

    def capture(symbol, start, end, tld, status_update, store_func):
        captured["start"] = start
        captured["end"] = end
        return _sample_df(), {}

    with mock.patch(
        "fast_trade.archive.update_kline.get_binance_klines", side_effect=capture
    ), mock.patch(
        "fast_trade.archive.update_kline.update_klines_to_db", return_value="/tmp/x.parquet"
    ), mock.patch("fast_trade.archive.update_kline.time.sleep"):
        update_kline.update_kline("BTCUSDT", "binanceus")

    assert captured["start"].tzinfo == datetime.timezone.utc
    assert captured["end"].tzinfo == datetime.timezone.utc
    assert captured["end"] <= datetime.datetime.now(datetime.timezone.utc)


def test_update_kline_progress_callback():
    updates = []

    def fake_binance(symbol, window_start, window_end, tld, status_update, store_func):
        status_update({"perc_complete": 50})
        return _sample_df(), {"perc_complete": 50}

    with mock.patch(
        "fast_trade.archive.update_kline.get_binance_klines",
        side_effect=fake_binance,
    ), mock.patch(
        "fast_trade.archive.update_kline.update_klines_to_db", return_value="/tmp/x.parquet"
    ), mock.patch("fast_trade.archive.update_kline.time.sleep"):
        update_kline.update_kline(
            "BTCUSDT",
            "binanceus",
            progress_callback=updates.append,
        )

    assert updates


def test_update_kline_raises_without_recorded_exception():
    real_range = range

    def patched_range(*args, **kwargs):
        if args == (1, 6):
            return real_range(1, 1)
        return real_range(*args, **kwargs)

    with mock.patch("fast_trade.archive.update_kline.range", side_effect=patched_range), mock.patch(
        "fast_trade.archive.update_kline.time.sleep"
    ):
        with pytest.raises(Exception, match="no recorded exception"):
            update_kline.update_kline("BTCUSDT", "binanceus")


def test_update_kline_retries_then_raises_last_exception():
    with mock.patch(
        "fast_trade.archive.update_kline.get_binance_klines",
        side_effect=RuntimeError("download failed"),
    ), mock.patch("fast_trade.archive.update_kline.time.sleep"):
        with pytest.raises(RuntimeError, match="download failed"):
            update_kline.update_kline("BTCUSDT", "binanceus")


def test_update_kline_unsupported_in_loop_branch():
    original = list(update_kline.supported_exchanges)
    try:
        update_kline.supported_exchanges.append("phantom")
        with mock.patch("fast_trade.archive.update_kline.time.sleep"):
            with pytest.raises(ValueError, match="not supported"):
                update_kline.update_kline("BTCUSDT", "phantom")
    finally:
        update_kline.supported_exchanges[:] = original


def test_update_kline_download_failed_after_store_errors():
    with mock.patch(
        "fast_trade.archive.update_kline.get_binance_klines", return_value=(_sample_df(), {})
    ), mock.patch(
        "fast_trade.archive.update_kline.update_klines_to_db",
        side_effect=RuntimeError("store failed"),
    ), mock.patch("fast_trade.archive.update_kline.time.sleep"):
        with pytest.raises(RuntimeError, match="store failed"):
            update_kline.update_kline("BTCUSDT", "binanceus")


def test_update_kline_caps_future_end_date():
    future_end = datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    captured = {}

    def capture(symbol, window_start, window_end, tld, status_update, store_func):
        captured["end"] = window_end
        return _sample_df(), {}

    with mock.patch("fast_trade.archive.update_kline.get_binance_klines", side_effect=capture), mock.patch(
        "fast_trade.archive.update_kline.update_klines_to_db", return_value="/tmp/x.parquet"
    ), mock.patch("fast_trade.archive.update_kline.time.sleep"):
        update_kline.update_kline("BTCUSDT", "binanceus", start_date=start, end_date=future_end)

    assert captured["end"] <= datetime.datetime.now(datetime.timezone.utc)


def test_main_block_runs():
    run_update_kline_main()
