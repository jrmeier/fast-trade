import math
import requests
import datetime
import time
import random
import pandas as pd
from pprint import pprint

BASE_URL = "https://api.exchange.coinbase.com"


def get_products():
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


def get_asset_ids():
    """Returns a list of all tradable assets on Coinbase Pro"""
    ids = [asset["id"] for asset in get_products()]
    ids.sort()
    return ids


def get_product_candles(
    product_id: str,
    start: datetime = None,
    end: datetime = None,
    granularity: int = 60,
    update_status: callable = lambda x: None,
    store_func: callable = lambda x: None,
):
    """Returns the candle data for a given product"""

    if not start:
        # fetch the oldest date for this symbol
        start = get_oldest_day(product_id)

    # can't be more than 1 hour in the past
    end = end or datetime.datetime.utcnow()
    end = start + datetime.timedelta(days=1)
    start = start or (end - datetime.timedelta(hours=3))
    start = start.replace(tzinfo=datetime.timezone.utc)
    end = end.replace(tzinfo=datetime.timezone.utc)

    # while datetime.datetime.fromisoformat(
    currentDate = start
    df = pd.DataFrame()

    # calculate the estimated number of calls
    total_duration_hours = (end - start).total_seconds() / 3600
    num_calls = math.ceil(total_duration_hours / 3)
    # print("estimated number of calls: ", num_calls)
    call_count = 0
    while currentDate < end:
        # print("currentDate: ", currentDate)
        next_end = currentDate + datetime.timedelta(hours=3)
        if next_end > end:
            next_end = end - datetime.timedelta(minutes=1)

        if currentDate > next_end:
            break
        params = {
            "granularity": 60,
            "start": str(int(currentDate.timestamp())),
            "end": str(int(next_end.timestamp())),
        }
        # os.system("clear")
        perc_complete = round(call_count / num_calls * 100, 2)
        # print(f"Fetching data for {product_id}... {perc_complete:.2f}% complete")

        # update_status({"prodcuproduct_id, perc_complete, call_count, num_calls})
        update_status(
            {
                "product_id": product_id,
                "perc_complete": perc_complete,
                "call_count": call_count,
                "num_calls": num_calls,
            }
        )

        # https://api.coinbase.com/api/v3/brokerage/products/:product_id/candles
        # print("fetching: ", currentDate, "to", currentDate + datetime.timedelta(hours=3), "for", product_id)
        url = f"{BASE_URL}/products/{product_id}/candles"
        headers = {"Content-Type": "application/json"}
        try:
            res = requests.get(url, params=params, headers=headers)
            if res.status_code > 399:
                # skip this call
                continue
            res = res.json()
            call_count += 1
            new_df = df_from_candles(res)
            # do the new version of concat
            if new_df.empty:
                continue
            df = pd.concat([df, new_df])
            df.drop_duplicates(inplace=True)
            # df =
            time.sleep(random.random() * 0.5 + 0.2)
        except Exception as e:
            print("error", e)
            raise e
        currentDate = currentDate + datetime.timedelta(hours=3)
    df.sort_index(inplace=True, ascending=False)
    return df


CB_REST_HEADER_MATCH = [
    "date",
    "low",
    "high",
    "open",
    "close",
    "volume",
]


def df_from_candles(klines):
    new_df = pd.DataFrame(klines, columns=CB_REST_HEADER_MATCH)
    new_df = new_df.drop_duplicates()
    new_df.index = pd.to_datetime(new_df.date, unit="s")

    if "date" in new_df.columns:
        new_df = new_df.drop(columns=["date"])

    return new_df


def store_df_to_sql(df, table_name, conn):
    return df.to_sql(table_name, conn, if_exists="append", index=True, unique=True)


def get_oldest_day(product_id, start_date=datetime.datetime(2015, 7, 21)):
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
        time.sleep(random.random() * 0.2 + 0.2)
        if response.status_code != 200:
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
    res = get_product_candles("BTC-USD")
    # res = find_oldest_date("DOGE-USD")
    # res = get_products()
    pprint(res)

    # res.to_csv("btc.csv")
    # print(res)
    # print(res[0], res[1])
