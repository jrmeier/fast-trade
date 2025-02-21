import datetime
import math
import os
import random
import time
import typing
from pprint import pprint

import pandas as pd
import requests

API_DELAY = os.getenv("API_DELAY", 0.3)
BASE_URL = "https://api.exchange.coinbase.com"
CB_REST_HEADER_MATCH = [
    "date",
    "low",
    "high",
    "open",
    "close",
    "volume",
]


def get_products() -> typing.List[dict]:
    """Returns a list of all tradable assets on Coinbase Pro"""
    try:
        res = requests.get(f"{BASE_URL}/products")
        if res.status_code > 399:
            print("unauthorized")
            return []
        return res.json()
    except Exception as e:
        print(e.status_code)
        print("Error fetching products: e")
        return []


def get_asset_ids() -> typing.List[str]:
    """Returns a list of all tradable assets on Coinbase Pro"""
    ids = [asset["id"] for asset in get_products()]
    ids.sort()
    return ids


def get_product_candles(
    product_id: str,
    start: datetime = None,
    end: datetime = None,
    update_status: callable = lambda x: None,
    store_func: callable = lambda x: None,
):
    """Returns the candle data for a given product"""

    # print("Fetching data for: ", product_id, start, end)
    if not start:
        # fetch the oldest date for this symbol
        start = get_oldest_day(product_id)

    # can't be more than 1 hour in the past
    end = end or datetime.datetime.utcnow()
    start = start or (end - datetime.timedelta(hours=3))

    # end = end + datetime.timedelta(days=1)

    start = start.replace(tzinfo=datetime.timezone.utc)
    end = end.replace(tzinfo=datetime.timezone.utc)

    # print("start", start, "end", end)
    # return
    # while datetime.datetime.fromisoformat(
    currentDate = start
    df = pd.DataFrame()

    # calculate the estimated number of calls
    total_duration_hours = (end - start).total_seconds() / 3600
    num_calls = math.ceil(total_duration_hours / 3)
    # print("estimated number of calls: ", num_calls)
    call_count = 0
    # print("start", start, "end", end)
    status_obj = {}
    bad_errors = 0
    start_time = time.time()
    while currentDate < end:
        # print("currentDate", currentDate, "end", end)
        currentDate = currentDate.replace(tzinfo=datetime.timezone.utc)
        next_end = currentDate + datetime.timedelta(hours=3)
        now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        next_end = next_end.replace(tzinfo=datetime.timezone.utc)
        if next_end > now:
            next_end = now

        params = {
            "granularity": 60,
            "start": str(int(currentDate.timestamp())),
            "end": str(int(next_end.timestamp())),
        }

        df = get_single_candle(product_id, params, df)
        if df.empty:
            print(f"Error Downloading {product_id}")
            bad_errors += 1
            if bad_errors > 4:
                raise Exception(
                    f"Error Downloading: for {product_id} from {start} to {end}"
                )
            time.sleep(2 * bad_errors)
            continue
        call_count += 1
        if call_count % 10 == 0:

            store_func(df, product_id, "coinbase")

        status_obj = {
            "symbol": product_id,
            "perc_complete": round(call_count / num_calls * 100, 2),
            "call_count": call_count,
            "total_calls": num_calls,
            "total_time": round(time.time() - start_time, 2),
            # "sleep_time": sleeper,
            "est_time_remaining": round(
                (time.time() - start_time) / call_count * (num_calls - call_count), 2
            ),
        }
        update_status(status_obj)
        currentDate = next_end
    if not df.empty:
        df.sort_index(inplace=True, ascending=False)

    return df, status_obj


def get_single_candle(product_id: str, params: dict = {}, df=pd.DataFrame()):
    url = f"{BASE_URL}/products/{product_id}/candles"
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.get(url, params=params, headers=headers)
        bad_errors = 0
        if res.status_code > 399:
            bad_errors += 1
            # skip this call
            print("Error ", res.status_code, res.text)
            # bad_errors += 1
            if bad_errors > 1:
                time.sleep(bad_errors * bad_errors * bad_errors)

            if bad_errors > 5:
                raise Exception(f"Api Error: {res.status_code} {res.text}")
            # Warning("skipping call ", res.status_code, res.text)
        # print("res", res.status_code, res.text)
        res = res.json()
        new_df = df_from_candles(res)
        if new_df.empty:
            bad_errors += 1
            if bad_errors > 1:
                raise Exception(f"Error Downloading: for {product_id}")
            return pd.DataFrame()
        sleep_time = random.random() * 0.5 + 0.1
        time.sleep(sleep_time)
        df = pd.concat([df, new_df])
        df.drop_duplicates(inplace=True)
        return df
    except Exception as e:
        print("error", e)
        return pd.DataFrame()


def df_from_candles(klines):
    new_df = pd.DataFrame(klines, columns=CB_REST_HEADER_MATCH)
    new_df = new_df.drop_duplicates()
    new_df.index = pd.to_datetime(new_df.date, unit="s")

    if "date" in new_df.columns:
        new_df = new_df.drop(columns=["date"])

    return new_df


def get_oldest_day(
    product_id, start_date=datetime.datetime(2015, 7, 21)
) -> datetime.datetime:
    """Find the oldest day with data for a given product_id."""

    url = f"{BASE_URL}/products/{product_id}/candles"
    end_date = datetime.datetime.now()
    call_count = 0
    while start_date <= end_date:
        middle_date = start_date + (end_date - start_date) // 2
        params = {
            "granularity": 60,
            "start": int(middle_date.timestamp()),
            "end": int((middle_date + datetime.timedelta(minutes=1)).timestamp()),
        }

        response = requests.get(url, params=params)
        call_count += 1
        time.sleep(random.random() * 0.2 + 0.1)
        if response.status_code != 200:
            time.sleep(2)
            raise Exception(f"API request failed: {response.text}")

        data = response.json()
        if data:
            # Data found, search in earlier half
            end_date = middle_date - datetime.timedelta(days=1)
        else:
            # No data, search in later half
            start_date = middle_date + datetime.timedelta(days=1)

    print(f"API calls: {call_count}")
    return end_date


if __name__ == "__main__":
    start = datetime.datetime(2024, 2, 7)
    res = get_product_candles("BTC-USD", start=start)
    # res = find_oldest_date("DOGE-USD")
    # res = get_products()
    pprint(res)

    # res.to_csv("btc.csv")
    # print(res)
    # print(res[0], res[1])
