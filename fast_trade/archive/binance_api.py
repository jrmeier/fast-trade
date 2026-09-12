import datetime
import math
import os
import random
import time

import polars as pl
import requests
from rich.console import Console

from ..utils import DATE_COL

API_DELAY = float(os.getenv("API_DELAY", 0.3))
console = Console()

BINANCE_KLINE_REST_SCHEMA = {
    "date": pl.Int64,  # Open time
    "open": pl.Float64,  # Open
    "high": pl.Float64,  # High
    "low": pl.Float64,  # Low
    "close": pl.Float64,  # Close
    "volume": pl.Float64,  # Volume
    "close_time": pl.Int64,  # Close time
    "quote_asset_volume": pl.Float64,  # Quote asset volume
    "number_of_trades": pl.Int64,  # Number of trades
    "taker_buy_base_asset_volume": pl.Float64,  # Taker buy base asset volume
    "taker_buy_base_a_volume": pl.Float64,  # Taker buy quote
    "ignore": pl.Utf8,  # literally ignore this
}

BINANCE_KLINE_REST_HEADER_MATCH = list(BINANCE_KLINE_REST_SCHEMA.keys())


def get_exchange_info(tld="us"):
    url = f"https://api.binance.{tld}/api/v3"
    req = requests.get(f"{url}/exchangeInfo")
    # attempt to sort any keys that are lists
    data = req.json()

    def sort_data(data):
        if isinstance(data, dict):
            return {k: sort_data(v) for k, v in sorted(data.items())}
        elif isinstance(data, list):
            new_list = []
            for x in data:
                if isinstance(x, (dict, list)):
                    new_list.append(sort_data(x))
                else:
                    new_list.append(x)
            return (
                sorted(new_list, key=str)
                if all(isinstance(i, dict) for i in new_list)
                else sorted(new_list)
            )
        else:
            return data

    # print(data)
    data = sort_data(data)

    return data


def get_available_symbols(tld="us"):
    exchange_info = get_exchange_info(tld)
    symbols = []

    for symbol in exchange_info.get("symbols", []):
        if symbol["status"] == "TRADING":
            symbols.append(symbol["symbol"])

    symbols.sort()
    return symbols


def get_oldest_date_available(symbol, tld="us"):
    endTime = int(datetime.datetime.utcnow().timestamp() * 1000)
    # TODO: make this accept a tld
    url = f"https://api.binance.{tld}/api/v3/klines?symbol={symbol}&interval=1m&startTime=0&endTime={endTime}&limit=1"

    data = requests.get(url).json()
    try:
        oldest_date = datetime.datetime.fromtimestamp(data[0][0] / 1000)
        return oldest_date
    except Exception:
        console.print(f"[red]Error fetching oldest date for {symbol}[/red]")
        return datetime.datetime.utcnow() - datetime.timedelta(days=1)


def get_binance_klines(
    symbol,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    tld="us",
    status_update=lambda x: None,
    store_func=lambda x, y: None,
):
    start_date = start_date.replace(tzinfo=datetime.timezone.utc)
    end_date = end_date.replace(tzinfo=datetime.timezone.utc)

    curr_date = start_date

    HOURS_TO_INCREMENT = 15

    end_date = end_date.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now().replace(tzinfo=datetime.timezone.utc)
    if end_date > now:
        end_date = now.replace(second=0, microsecond=0)

    # calculate the estimated number of calls
    total_duration_hours = (end_date - curr_date).total_seconds() / 3600
    num_calls = math.ceil(total_duration_hours / HOURS_TO_INCREMENT)
    total_api_calls = 0
    error_count = 0
    klines = []
    start_time = time.time()
    while curr_date < end_date:
        next_end_date = curr_date + datetime.timedelta(hours=HOURS_TO_INCREMENT)
        startTime = int(curr_date.timestamp()) * 1000
        endTime = int(next_end_date.timestamp()) * 1000

        url = (
            f"https://api.binance.{tld}/api/v3/klines"
            f"?symbol={symbol}&interval=1m"
            f"&startTime={startTime}&endTime={endTime}&limit=1000"
        )

        req = requests.get(url)
        total_api_calls += 1
        if req.status_code == 200:
            curr_date = next_end_date
            klines.extend(req.json())
            error_count = 0
        else:
            console.print(f"[red]Binance error {symbol}: {req.text}[/red]")
            error_count += 1
            if error_count > 3:
                raise Exception(
                    f"Download failed for {symbol} after 3 errors. Error: {req.text}"
                )
            if req.status_code == 429:
                # sleeep for some time
                time.sleep(10)
                continue
        sleeper = random.random() * API_DELAY
        if sleeper < 0.1:
            sleeper += 0.1

        if total_api_calls % 30 == 0:
            sleeper += random.randint(1, 3)
            kline_df = binance_kline_to_df(klines)
            store_func(kline_df, symbol, "binanceus")

        status_obj = {
            "symbol": symbol,
            "perc_complete": round(total_api_calls / num_calls * 100, 2),
            "call_count": total_api_calls,
            "total_calls": num_calls,
            "total_time": round(time.time() - start_time, 2),
            # "sleep_time": sleeper,
            "est_time_remaining": round(
                (time.time() - start_time)
                / total_api_calls
                * (num_calls - total_api_calls),
                2,
            ),
        }
        status_update(status_obj)
        time.sleep(sleeper)
        curr_date = next_end_date

    status_obj = {
        "symbol": symbol,
        "perc_complete": 100,
        "call_count": total_api_calls,
        "total_calls": total_api_calls,
        "total_time": time.time() - start_time,
        "est_time_remaining": 0,
    }
    status_update(status_obj)
    klines_df = binance_kline_to_df(klines)
    return klines_df, status_obj


def binance_kline_to_df(klines) -> pl.DataFrame:
    """Turn the REST kline rows into a frame with a datetime "date" column."""
    schema = dict(BINANCE_KLINE_REST_SCHEMA)

    if not klines:
        schema[DATE_COL] = pl.Datetime
        del schema["ignore"]
        return pl.DataFrame(schema=schema)

    new_df = pl.DataFrame(klines, schema=schema, orient="row")

    new_df = new_df.unique(maintain_order=True).drop("ignore")

    new_df = new_df.with_columns(pl.from_epoch(DATE_COL, time_unit="ms"))

    return new_df.sort(DATE_COL)
