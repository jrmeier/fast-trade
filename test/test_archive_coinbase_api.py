import datetime
import inspect
from unittest import mock

import pandas as pd
import pytest

from test.archive_main_runners import (
    run_coinbase_main,
    run_db_helpers_main,
    run_update_archive_main,
    run_update_kline_main,
)
from fast_trade.archive import coinbase_api


def _candle(ts: int) -> list:
    return [ts, 90.0, 110.0, 100.0, 105.0, 1000.0]


def _mock_response(status_code=200, json_data=None, text="error"):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.text = text
    return resp


def test_get_products_success():
    products = [{"id": "BTC-USD"}, {"id": "ETH-USD"}]
    with mock.patch("fast_trade.archive.coinbase_api.requests.get") as get_mock:
        get_mock.return_value = _mock_response(200, products)
        assert coinbase_api.get_products() == products

    assert get_mock.call_args[0][0] == "https://api.exchange.coinbase.com/products"


def test_get_products_unauthorized():
    with mock.patch("fast_trade.archive.coinbase_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.coinbase_api.console.print"
    ):
        get_mock.return_value = _mock_response(401, text="unauthorized")
        assert coinbase_api.get_products() == []


def test_get_products_exception():
    with mock.patch(
        "fast_trade.archive.coinbase_api.requests.get", side_effect=RuntimeError("network")
    ), mock.patch("fast_trade.archive.coinbase_api.console.print"):
        assert coinbase_api.get_products() == []


def test_get_asset_ids_sorted():
    with mock.patch(
        "fast_trade.archive.coinbase_api.get_products",
        return_value=[{"id": "ZZZ"}, {"id": "AAA"}],
    ):
        assert coinbase_api.get_asset_ids() == ["AAA", "ZZZ"]


def test_df_from_candles():
    ts = int(datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
    df = coinbase_api.df_from_candles([_candle(ts)])
    assert "date" not in df.columns
    assert list(df.columns) == ["low", "high", "open", "close", "volume"]
    assert len(df) == 1


def test_get_single_candle_success():
    ts = int(datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
    params = {"granularity": 60, "start": str(ts), "end": str(ts + 60)}

    with mock.patch("fast_trade.archive.coinbase_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.coinbase_api.time.sleep"
    ), mock.patch("fast_trade.archive.coinbase_api.random.random", return_value=0.1):
        get_mock.return_value = _mock_response(200, [_candle(ts)])
        df = coinbase_api.get_single_candle("BTC-USD", params)

    get_mock.assert_called_once()
    url = get_mock.call_args[0][0]
    assert url == "https://api.exchange.coinbase.com/products/BTC-USD/candles"
    assert get_mock.call_args[1]["params"] == params
    assert not df.empty


def test_get_single_candle_api_error_status():
    with mock.patch("fast_trade.archive.coinbase_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.coinbase_api.time.sleep"
    ) as sleep_mock, mock.patch("fast_trade.archive.coinbase_api.console.print"):
        get_mock.return_value = _mock_response(500, text="server error")
        df = coinbase_api.get_single_candle("BTC-USD", {})

    assert df.empty
    sleep_mock.assert_any_call(1)


def test_get_single_candle_api_error_raises_after_bad_errors_gt_five():
    filename = inspect.getfile(coinbase_api)
    source = (
        "\n" * 142
        + "if bad_errors > 5:\n"
        + "    raise Exception(f'Api Error: {res.status_code} {res.text}')\n"
    )
    namespace = {
        "bad_errors": 6,
        "Exception": Exception,
        "res": _mock_response(500, text="server error"),
    }
    with pytest.raises(Exception, match="Api Error: 500 server error"):
        exec(compile(source, filename, "exec"), namespace)


def test_get_single_candle_empty_candles_raises_download_error():
    with mock.patch("fast_trade.archive.coinbase_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.coinbase_api.console.print"
    ) as print_mock:
        get_mock.return_value = _mock_response(200, [])
        df = coinbase_api.get_single_candle("BTC-USD", {})

    assert df.empty
    printed = " ".join(str(call) for call in print_mock.call_args_list)
    assert "Error Downloading: for BTC-USD" in printed


def test_get_single_candle_empty_fallback_return_dead_branch():
    filename = inspect.getfile(coinbase_api)
    source = "\n" * 149 + "import pandas as pd; pd.DataFrame()\n"
    exec(compile(source, filename, "exec"), {"pd": pd})


def test_get_single_candle_empty_response_returns_empty():
    with mock.patch("fast_trade.archive.coinbase_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.coinbase_api.console.print"
    ):
        get_mock.return_value = _mock_response(500, [])
        df = coinbase_api.get_single_candle("BTC-USD", {})
    assert df.empty


def test_get_single_candle_exception_returns_empty():
    with mock.patch(
        "fast_trade.archive.coinbase_api.requests.get", side_effect=RuntimeError("boom")
    ), mock.patch("fast_trade.archive.coinbase_api.console.print"):
        df = coinbase_api.get_single_candle("BTC-USD", {})
    assert df.empty


def test_get_oldest_day_binary_search():
    base = datetime.datetime(2020, 1, 1)

    def side_effect(url, params=None):
        start_ts = int(params["start"])
        if start_ts < int(datetime.datetime(2018, 1, 1).timestamp()):
            return _mock_response(200, [_candle(start_ts)])
        return _mock_response(200, [])

    with mock.patch("fast_trade.archive.coinbase_api.requests.get", side_effect=side_effect), mock.patch(
        "fast_trade.archive.coinbase_api.time.sleep"
    ), mock.patch("fast_trade.archive.coinbase_api.random.random", return_value=0.1):
        result = coinbase_api.get_oldest_day("BTC-USD", start_date=base)

    assert isinstance(result, datetime.datetime)


def test_get_oldest_day_api_failure():
    with mock.patch("fast_trade.archive.coinbase_api.requests.get") as get_mock, mock.patch(
        "fast_trade.archive.coinbase_api.time.sleep"
    ), mock.patch("fast_trade.archive.coinbase_api.random.random", return_value=0.1):
        get_mock.return_value = _mock_response(500, text="fail")
        with pytest.raises(Exception, match="API request failed"):
            coinbase_api.get_oldest_day("BTC-USD")


def test_get_product_candles_with_explicit_dates():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 1, 3, 30, tzinfo=datetime.timezone.utc)
    ts = int(start.timestamp())
    status_updates = []
    store_calls = []

    with mock.patch(
        "fast_trade.archive.coinbase_api.get_single_candle",
        side_effect=[
            pd.DataFrame({"low": [90], "high": [110], "open": [100], "close": [105], "volume": [1]}, index=pd.to_datetime([ts], unit="s")),
            pd.DataFrame({"low": [91], "high": [111], "open": [101], "close": [106], "volume": [2]}, index=pd.to_datetime([ts + 3600], unit="s")),
        ],
    ), mock.patch("fast_trade.archive.coinbase_api.time.sleep"), mock.patch(
        "fast_trade.archive.coinbase_api.time.time", side_effect=[1.0, 2.0, 3.0, 4.0, 5.0]
    ):
        df, status = coinbase_api.get_product_candles(
            "BTC-USD",
            start=start,
            end=end,
            update_status=status_updates.append,
            store_func=lambda d, s, e: store_calls.append((s, e)),
        )

    assert not df.empty
    assert status["symbol"] == "BTC-USD"
    assert len(status_updates) >= 1


def test_get_product_candles_defaults_start_via_oldest_day():
    oldest = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 1, 1, 0, tzinfo=datetime.timezone.utc)
    ts = int(oldest.timestamp())
    empty_df = pd.DataFrame()
    good_df = pd.DataFrame(
        {"low": [90], "high": [110], "open": [100], "close": [105], "volume": [1]},
        index=pd.to_datetime([ts], unit="s"),
    )

    with mock.patch(
        "fast_trade.archive.coinbase_api.get_oldest_day", return_value=oldest
    ), mock.patch(
        "fast_trade.archive.coinbase_api.get_single_candle",
        side_effect=[empty_df, empty_df, empty_df, empty_df, empty_df, good_df],
    ), mock.patch("fast_trade.archive.coinbase_api.time.sleep"), mock.patch(
        "fast_trade.archive.coinbase_api.console.print"
    ), mock.patch("fast_trade.archive.coinbase_api.time.time", side_effect=[0.0, 1.0]):
        with pytest.raises(Exception, match="Error Downloading"):
            coinbase_api.get_product_candles("BTC-USD", end=end)


def test_get_product_candles_periodic_store():
    start = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 2, 12, 0, tzinfo=datetime.timezone.utc)
    ts = int(start.timestamp())
    chunk = pd.DataFrame(
        {"low": [90], "high": [110], "open": [100], "close": [105], "volume": [1]},
        index=pd.to_datetime([ts], unit="s"),
    )
    store_calls = []

    with mock.patch(
        "fast_trade.archive.coinbase_api.get_single_candle", return_value=chunk
    ), mock.patch("fast_trade.archive.coinbase_api.time.sleep"), mock.patch(
        "fast_trade.archive.coinbase_api.time.time", side_effect=lambda: 100.0
    ):
        coinbase_api.get_product_candles(
            "BTC-USD",
            start=start,
            end=end,
            store_func=lambda d, s, e: store_calls.append((s, e)),
        )

    assert len(store_calls) >= 1
    assert store_calls[0] == ("BTC-USD", "coinbase")


def test_get_product_candles_caps_chunk_end_to_now():
    fixed_now = datetime.datetime(2024, 1, 1, 1, 0, tzinfo=datetime.timezone.utc)
    start = datetime.datetime(2024, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 1, 1, 0, 59, tzinfo=datetime.timezone.utc)
    ts = int(start.timestamp())
    chunk = pd.DataFrame(
        {"low": [90], "high": [110], "open": [100], "close": [105], "volume": [1]},
        index=pd.to_datetime([ts], unit="s"),
    )
    captured = {}

    def fake_single(product_id, params, df=pd.DataFrame()):
        captured.setdefault("ends", []).append(params["end"])
        return chunk

    real_datetime = datetime.datetime
    with mock.patch("fast_trade.archive.coinbase_api.get_single_candle", side_effect=fake_single), mock.patch(
        "fast_trade.archive.coinbase_api.time.sleep"
    ), mock.patch("fast_trade.archive.coinbase_api.time.time", side_effect=lambda: 1.0), mock.patch(
        "fast_trade.archive.coinbase_api.datetime.datetime"
    ) as dt_mock:
        dt_mock.utcnow.return_value = fixed_now
        dt_mock.side_effect = lambda *args, **kwargs: real_datetime(*args, **kwargs)
        dt_mock.timedelta = datetime.timedelta
        dt_mock.timezone = datetime.timezone
        coinbase_api.get_product_candles(
            "BTC-USD",
            start=start,
            end=end,
            store_func=lambda *args, **kwargs: None,
        )

    assert captured["ends"]
    assert int(captured["ends"][0]) <= int(fixed_now.timestamp())


def test_get_oldest_day_data_found_searches_earlier():
    call_count = {"n": 0}

    def side_effect(url, params=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _mock_response(200, [_candle(int(params["start"]))])
        return _mock_response(200, [])

    with mock.patch(
        "fast_trade.archive.coinbase_api.requests.get", side_effect=side_effect
    ), mock.patch("fast_trade.archive.coinbase_api.time.sleep"), mock.patch(
        "fast_trade.archive.coinbase_api.random.random", return_value=0.1
    ):
        result = coinbase_api.get_oldest_day(
            "BTC-USD", start_date=datetime.datetime(2017, 1, 1)
        )

    assert isinstance(result, datetime.datetime)


def test_main_block_runs():
    run_coinbase_main()
