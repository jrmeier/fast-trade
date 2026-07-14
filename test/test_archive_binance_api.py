import datetime
from unittest import mock

import pandas as pd
import pytest

from fast_trade.archive import binance_api


def _sample_kline(open_time_ms: int) -> list:
    return [
        open_time_ms,
        "100",
        "110",
        "90",
        "105",
        "1000",
        open_time_ms + 59999,
        "100000",
        10,
        "500",
        "50000",
        "0",
    ]


def _mock_response(status_code=200, json_data=None, text="error"):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.text = text
    return resp


def test_get_exchange_info_sorts_nested_structures():
    unsorted = {
        "z": [{"b": 2}, {"a": 1}],
        "a": {"y": 2, "x": 1},
        "m": [3, 1, 2],
    }
    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock:
        get_mock.return_value.json.return_value = unsorted
        result = binance_api.get_exchange_info(tld="com")

    get_mock.assert_called_once_with("https://api.binance.com/api/v3/exchangeInfo")
    assert result["a"] == {"x": 1, "y": 2}
    assert result["m"] == [1, 2, 3]
    assert result["z"] == [{"a": 1}, {"b": 2}]


def test_get_available_symbols_filters_trading():
    exchange_info = {
        "symbols": [
            {"symbol": "ZZZ", "status": "BREAK"},
            {"symbol": "AAA", "status": "TRADING"},
            {"symbol": "BBB", "status": "TRADING"},
        ]
    }
    with mock.patch(
        "fast_trade.archive.binance_api.get_exchange_info", return_value=exchange_info
    ):
        assert binance_api.get_available_symbols() == ["AAA", "BBB"]


def test_get_oldest_date_available_success():
    ts_ms = int(datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock:
        get_mock.return_value.json.return_value = [[ts_ms]]
        result = binance_api.get_oldest_date_available("BTCUSDT", tld="us")

    url = get_mock.call_args[0][0]
    assert "api.binance.us" in url
    assert "symbol=BTCUSDT" in url
    assert result == datetime.datetime.fromtimestamp(ts_ms / 1000)


def test_get_oldest_date_available_fallback_on_error():
    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock:
        get_mock.return_value.json.return_value = {}
        with mock.patch("fast_trade.archive.binance_api.console.print"):
            result = binance_api.get_oldest_date_available("BAD")

    assert isinstance(result, datetime.datetime)
    assert result < datetime.datetime.utcnow()


def test_binance_kline_to_df_drops_ignore_and_date():
    kline = _sample_kline(1_600_000_000_000)
    kline[-1] = "1"
    df = binance_api.binance_kline_to_df([kline])
    assert "ignore" not in df.columns
    assert "date" not in df.columns
    assert isinstance(df.index, pd.DatetimeIndex)


def test_get_binance_klines_success_with_status_and_store():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 1, 1, 0, tzinfo=datetime.timezone.utc)
    kline = _sample_kline(int(start.timestamp() * 1000))

    status_updates = []
    store_calls = []

    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.binance_api.time.sleep"
    ), mock.patch("fast_trade.archive.binance_api.random.random", return_value=0.5), mock.patch(
        "fast_trade.archive.binance_api.random.randint", return_value=2
    ), mock.patch(
        "fast_trade.archive.binance_api.time.time", side_effect=[100.0, 101.0, 102.0, 103.0]
    ):
        get_mock.return_value = _mock_response(200, [kline])
        df, status = binance_api.get_binance_klines(
            "BTCUSDT",
            start,
            end,
            tld="us",
            status_update=status_updates.append,
            store_func=lambda d, s, e: store_calls.append((s, e)),
        )

    url = get_mock.call_args[0][0]
    assert "api.binance.us/api/v3/klines" in url
    assert "symbol=BTCUSDT" in url
    assert "interval=1m" in url
    assert not df.empty
    assert status["perc_complete"] == 100
    assert len(status_updates) >= 1


def test_get_binance_klines_caps_end_date_to_now():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    future_end = datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)
    capped_now = datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc)

    real_datetime = datetime.datetime
    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.binance_api.time.sleep"
    ), mock.patch("fast_trade.archive.binance_api.random.random", return_value=0.2), mock.patch(
        "fast_trade.archive.binance_api.datetime.datetime"
    ) as dt_mock:
        dt_mock.now.return_value = capped_now
        dt_mock.side_effect = lambda *args, **kwargs: real_datetime(*args, **kwargs)
        dt_mock.timedelta = datetime.timedelta
        dt_mock.timezone = datetime.timezone
        get_mock.return_value = _mock_response(200, [])
        binance_api.get_binance_klines("BTCUSDT", start, future_end)

    assert get_mock.called
    assert get_mock.call_count <= 2


def test_get_binance_klines_handles_non_200_error():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 1, 0, 30, tzinfo=datetime.timezone.utc)

    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.binance_api.time.sleep"
    ), mock.patch("fast_trade.archive.binance_api.random.random", return_value=0.2), mock.patch(
        "fast_trade.archive.binance_api.console.print"
    ):
        get_mock.return_value = _mock_response(500, text="server error")
        df, _ = binance_api.get_binance_klines("BTCUSDT", start, end)

    assert df.empty


def test_get_binance_klines_handles_429_rate_limit():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 1, 2, 0, tzinfo=datetime.timezone.utc)
    kline = _sample_kline(int(start.timestamp() * 1000))

    responses = [_mock_response(429, text="rate limit"), _mock_response(200, [kline])]

    with mock.patch("fast_trade.archive.binance_api.requests.get", side_effect=responses), mock.patch(
        "fast_trade.archive.binance_api.time.sleep"
    ) as sleep_mock, mock.patch("fast_trade.archive.binance_api.random.random", return_value=0.2), mock.patch(
        "fast_trade.archive.binance_api.console.print"
    ):
        df, status = binance_api.get_binance_klines("BTCUSDT", start, end)

    assert sleep_mock.called
    assert not df.empty
    assert status["perc_complete"] == 100


def test_get_binance_klines_raises_after_four_consecutive_errors():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 6, tzinfo=datetime.timezone.utc)

    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.binance_api.time.sleep"
    ), mock.patch("fast_trade.archive.binance_api.random.random", return_value=0.2), mock.patch(
        "fast_trade.archive.binance_api.console.print"
    ):
        get_mock.return_value = _mock_response(500, text="server error")
        with pytest.raises(Exception, match="Download failed for BTCUSDT after 3 errors"):
            binance_api.get_binance_klines("BTCUSDT", start, end)

    assert get_mock.call_count == 4


def test_get_binance_klines_periodic_store_on_thirtieth_call():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 20, tzinfo=datetime.timezone.utc)
    kline = _sample_kline(int(start.timestamp() * 1000))
    store_calls = []

    with mock.patch("fast_trade.archive.binance_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.binance_api.time.sleep"
    ), mock.patch("fast_trade.archive.binance_api.random.random", return_value=0.2), mock.patch(
        "fast_trade.archive.binance_api.random.randint", return_value=1
    ):
        get_mock.return_value = _mock_response(200, [kline])
        binance_api.get_binance_klines(
            "BTCUSDT",
            start,
            end,
            store_func=lambda d, s, e: store_calls.append((s, e)),
        )

    assert len(store_calls) >= 1
    assert store_calls[0] == ("BTCUSDT", "binanceus")
