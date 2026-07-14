"""Execute archive module __main__ blocks under coverage."""

from __future__ import annotations

import datetime
import runpy
import sys
from unittest import mock

import pandas as pd


def _chunk_df():
    ts = int(datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
    return pd.DataFrame(
        {"low": [90], "high": [110], "open": [100], "close": [105], "volume": [1]},
        index=pd.to_datetime([ts], unit="s"),
    )


def run_coinbase_main() -> None:
    sys.modules.pop("fast_trade.archive.coinbase_api", None)
    fixed_now = datetime.datetime(2024, 2, 7, 0, 30, tzinfo=datetime.timezone.utc)
    real_datetime = datetime.datetime
    with mock.patch(
        "fast_trade.archive.coinbase_api.get_single_candle", return_value=_chunk_df()
    ), mock.patch("fast_trade.archive.coinbase_api.time.sleep"), mock.patch(
        "fast_trade.archive.coinbase_api.time.time", side_effect=lambda: 1.0
    ), mock.patch(
        "fast_trade.archive.coinbase_api.random.random", return_value=0.1
    ), mock.patch(
        "fast_trade.archive.coinbase_api.datetime.datetime"
    ) as dt_mock:
        dt_mock.utcnow.return_value = fixed_now.replace(tzinfo=None)
        dt_mock.side_effect = lambda *args, **kwargs: real_datetime(*args, **kwargs)
        dt_mock.timedelta = datetime.timedelta
        dt_mock.timezone = datetime.timezone
        runpy.run_module("fast_trade.archive.coinbase_api", run_name="__main__")


if __name__ == "__main__":
    run_coinbase_main()


def run_db_helpers_main(archive_path: str) -> None:
    sys.modules.pop("fast_trade.archive.db_helpers", None)
    import os

    import fast_trade.archive.db_helpers as db_helpers

    os.environ["ARCHIVE_PATH"] = archive_path
    exchange_dir = os.path.join(archive_path, "binanceus")
    os.makedirs(exchange_dir, exist_ok=True)
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [110.0, 111.0],
            "low": [90.0, 91.0],
            "close": [105.0, 106.0],
            "volume": [1000.0, 1100.0],
        },
        index=pd.to_datetime(["2024-12-12", "2024-12-20"]),
    )
    df.to_parquet(os.path.join(exchange_dir, "BTCUSDT.parquet"))
    runpy.run_module("fast_trade.archive.db_helpers", run_name="__main__")


def run_update_kline_main() -> None:
    sys.modules.pop("fast_trade.archive.update_kline", None)
    import fast_trade.archive.coinbase_api as coinbase_api

    with mock.patch.object(
        coinbase_api, "get_product_candles", return_value=(pd.DataFrame(), {})
    ), mock.patch(
        "fast_trade.archive.db_helpers.update_klines_to_db",
        return_value="/tmp/BTC-USD.parquet",
    ):
        runpy.run_module("fast_trade.archive.update_kline", run_name="__main__")


def run_update_archive_main(archive_path: str) -> None:
    sys.modules.pop("fast_trade.archive.update_archive", None)
    import os

    os.makedirs(archive_path, exist_ok=True)
    os.environ["ARCHIVE_PATH"] = archive_path
    runpy.run_module("fast_trade.archive.update_archive", run_name="__main__")
