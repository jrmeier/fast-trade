import math
import requests
import json
import datetime
import time
import random
import pandas as pd
import os

BASE_URL = "https://api.pro.coinbase.com"


def get_products():
    """Returns a list of all tradable assets on Coinbase Pro"""
    return requests.get(f"{BASE_URL}/products").json()


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

    end = end or datetime.datetime.utcnow().isoformat()
    start = start or (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).isoformat()
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
        params = {
            "granulatiry": granularity,
            "start": int(currentDate.timestamp()),
            "end": int((currentDate + datetime.timedelta(hours=3)).timestamp()),
        }
        # os.system("clear")
        perc_complete = round(call_count / num_calls * 100, 2)
        # print(f"Fetching data for {product_id}... {perc_complete:.2f}% complete")

        # update_status({"prodcuproduct_id, perc_complete, call_count, num_calls})
        update_status({"product_id": product_id, "perc_complete": perc_complete, "call_count": call_count, "num_calls": num_calls})

        # print("fetching: ", currentDate, "to", currentDate + datetime.timedelta(hours=3), "for", product_id)
        try:
            res = requests.get(url=f"{BASE_URL}/products/{product_id}/candles", params=params).json()
            call_count += 1
            new_df = df_from_candles(res)
            df = pd.concat([df, new_df])
            # df = 
            time.sleep(random.random() * 0.5 + 0.2)
        except Exception as e:
            print("error", e)
            continue
        currentDate = currentDate + datetime.timedelta(hours=3)

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
    start = datetime.datetime.fromisoformat("2023-11-02")
    res = get_product_candles("BTC-USD", start=start)

    # res.to_csv("btc.csv")
    print(res)
    # print(res[0], res[1])
