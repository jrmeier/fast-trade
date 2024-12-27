import datetime
import os
from .binance_api import get_binance_klines
from .coinbase_api import get_product_candles
from .db_helpers import update_klines_to_db
import pandas as pd

supported_exchanges = ["binanceus", "binancecom", "coinbase"]


def update_kline(
    symbol, exchange, start_date: datetime.datetime, end_date: datetime.datetime
):
    if exchange not in supported_exchanges:
        raise ValueError(f"Exchange {exchange} not supported")

    start_date = start_date.replace(tzinfo=datetime.timezone.utc)
    end_date = end_date.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)

    if end_date > now:
        end_date = now.replace(second=0, microsecond=0)

    klines = pd.DataFrame()
    curr_date = start_date

    def status_update(status_obj):
        # os.system("clear")
        # print(status_obj)
        in_seconds = status_obj["est_time_remaining"]
        in_minutes = in_seconds / 60
        msg = f"Downloading {symbol} from {exchange}."
        if in_seconds > 100:
            msg += f" Remaining (in minutes): {in_minutes:.2f}"
        else:
            msg += f" Remaining (in seconds): {in_seconds:.2f}"

        msg += f" {status_obj['perc_complete']}% complete"
        print(msg)

    if exchange == "binanceus":
        klines, status_obj = get_binance_klines(
            symbol, curr_date, end_date, "us", status_update
        )
    elif exchange == "binancecom":
        klines, status_obj = get_binance_klines(
            symbol, curr_date, end_date, "com", status_update
        )
    elif exchange == "coinbase":
        klines, status_obj = get_product_candles(
            symbol, curr_date, end_date, status_update
        )
    else:
        raise ValueError(f"Exchange {exchange} not supported")

    db_path = update_klines_to_db(klines, symbol, exchange)

    return db_path


if __name__ == "__main__":
    # symbol = "BTCUSDT"
    # exchange = "binanceus"
    symbol = "BTC-USD"
    exchange = "coinbase"
    start_date = datetime.datetime(2024, 1, 1)
    end_date = datetime.datetime(2024, 1, 14)
    res = update_kline(symbol, exchange, start_date, end_date)
    print(res)
