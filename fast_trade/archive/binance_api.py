import requests
import datetime
import time
import random
import pandas as pd
from .constants import BINANCE_KLINE_REST_HEADER_MATCH


def get_base_url(tld="us"):
    return f"https://api.binance.{tld}/api/v3"


def get_exchange_info(tld="us"):
    url = get_base_url(tld)
    req = requests.get(f"{url}/exchangeInfo")
    # attempt to sort any keys that are lists
    data = req.json()

    # data["symbols"] = sorted(data["symbols"], key=lambda x: x["symbol"])
    # recursively sort any lists in any nested dictionaries
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

    for symbol in exchange_info["symbols"]:
        if symbol["status"] == "TRADING":
            symbols.append(symbol["symbol"])

    symbols.sort()
    return symbols


def get_oldest_date_available(symbol, tld="us"):
    endTime = int(datetime.datetime.utcnow().timestamp() * 1000)
    # TODO: make this accept a tld
    url = f"{get_base_url(tld)}/klines?symbol={symbol}&interval=1m&startTime=0&endTime={endTime}&limit=1"

    data = requests.get(url).json()
    try:
        oldest_date = datetime.datetime.fromtimestamp(data[0][0] / 1000)
        # print(f"{symbol} oldest date: {oldest_date}")
        return oldest_date
    except Exception as e:
        print(f"error with {symbol}")
        return datetime.datetime.utcnow() - datetime.timedelta(days=1)


def load_historical_klines_as_df(
    symbol,
    start_date=datetime.datetime.utcnow() - datetime.timedelta(days=7),
    end_date=datetime.datetime.utcnow(),
    tld="us",
):
    klines, status_obj = get_historical_klines_binance(
        symbol, start_date, end_date, tld
    )

    klines_df = binance_kline_to_df(klines)
    return klines_df, status_obj


def get_historical_klines_binance(symbol, start_date, end_date, tld="us"):

    curr_date = start_date

    HOURS_TO_INCREMENT = 15

    end_date = end_date.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    if end_date > now:
        end_date = now.replace(second=0, microsecond=0)

    total_api_calls = 0
    klines = []
    while curr_date < end_date:
        next_end_date = curr_date + datetime.timedelta(hours=HOURS_TO_INCREMENT)
        startTime = int(curr_date.timestamp()) * 1000
        endTime = int(next_end_date.timestamp()) * 1000

        url = f"{get_base_url(tld)}/klines?symbol={symbol}&interval=1m&startTime={startTime}&endTime={endTime}&limit=1000"

        req = requests.get(url)
        total_api_calls += 1
        if req.status_code == 200:
            curr_date = next_end_date
            klines.extend(req.json())
        else:
            # print(req)
            # raise Exception(f"Error with {symbol}")
            print(f"Error: {symbol} {req.text}")

        sleeper = random.random() * 0.3
        if sleeper < 0.1:
            sleeper += 0.1

        if total_api_calls % 100 == 0:
            sleeper += random.randint(1, 3)

        time.sleep(sleeper)
        curr_date = next_end_date

    status_obj = {"num_calls": total_api_calls}

    return klines, status_obj


def load_last_day_klines_as_df(pair, tld="us"):
    start_date = datetime.datetime.utcnow() - datetime.timedelta(hours=30)
    end_date = datetime.datetime.utcnow()
    klines, status_obj = get_historical_klines_binance(pair, start_date, end_date, tld)
    klines_df = binance_kline_to_df(klines)

    return klines_df, status_obj


def binance_kline_to_df(klines):
    new_df = pd.DataFrame(klines, columns=BINANCE_KLINE_REST_HEADER_MATCH)

    new_df = new_df.drop_duplicates()
    new_df.index = pd.to_datetime(new_df.date, unit="ms")

    columns_to_drop = []
    if new_df.ignore.any():
        columns_to_drop.append("ignore")

    if new_df.date.any():
        columns_to_drop.append("date")

    new_df = new_df.drop(columns=columns_to_drop)

    return new_df


def get_depth_snapshot(pair, tld="us"):
    url = f"{get_base_url(tld)}/depth?symbol={pair}&limit=1000"
    req = requests.get(url)
    return req.json()
