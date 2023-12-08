import math
import requests
import json
import datetime
import time
import random
import pandas as pd
import os

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
    return [asset["id"] for asset in get_products()]


def get_product_candles(product_id: str,
                        start: datetime = datetime.datetime.utcnow() - datetime.timedelta(hours=3),
                        end: datetime = datetime.datetime.utcnow(),
                        granularity: int = 60,
                        update_status: callable = lambda x: None
                        ):
    """Returns the candle data for a given product"""
    # can't be more than 1 hour in the past
    end = end or datetime.datetime.utcnow()
    start = start or (end - datetime.timedelta(hours=3))
    start = start.replace(tzinfo=datetime.timezone.utc)
    end = end.replace(tzinfo=datetime.timezone.utc)
    
    print("start: ", start)
    print("end: ", end)
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
        update_status({"product_id": product_id, "perc_complete": perc_complete, "call_count": call_count, "num_calls": num_calls})

        # https://api.coinbase.com/api/v3/brokerage/products/:product_id/candles
        # print("fetching: ", currentDate, "to", currentDate + datetime.timedelta(hours=3), "for", product_id)
        url = f"{BASE_URL}/products/{product_id}/candles"
        headers = {
            "Content-Type": "application/json"
        }
        try:
            res = requests.get(url, params=params, headers=headers)
            if res.status_code > 399:
                print(res.text)
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
            continue
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
    print("Storing data to SQL: ",df)
    return df.to_sql(table_name, conn, if_exists="append")


if __name__ == "__main__":
    # print(json.dumps(res, indent=4))
    start = datetime.datetime.fromisoformat("2023-12-02T19:00:00")
    end = datetime.datetime.fromisoformat("2023-12-02T20:40:00")
    print(start.tzinfo)
    start = start.replace(tzinfo=datetime.timezone.utc)
    end = end.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.utcnow()

    # print("start: ", start)
    # print("end: ", end)
    # print("now: ", now)
    res = get_product_candles("BTC-USD", start=start, end=end)
    # res = get_products()
    print(res)

    # res.to_csv("btc.csv")
    # print(res)
    # print(res[0], res[1])
