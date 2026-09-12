import datetime
import math
import os
import random
import time
import typing

import polars as pl
import requests
from rich.console import Console

from ..utils import DATE_COL

API_DELAY = os.getenv("API_DELAY", 0.3)
BASE_URL = "https://api.exchange.coinbase.com"
console = Console()
CB_REST_SCHEMA = {
    "date": pl.Int64,
    "low": pl.Float64,
    "high": pl.Float64,
    "open": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
}

CB_REST_HEADER_MATCH = list(CB_REST_SCHEMA.keys())


def get_products() -> typing.List[dict]:
    """Returns a list of all tradable assets on Coinbase Pro"""
    try:
        res = requests.get(f"{BASE_URL}/products")
        if res.status_code > 399:
            console.print("[red]Unauthorized Coinbase response[/red]")
            return []
        return res.json()
    except Exception as e:
        console.print(f"[red]Error fetching Coinbase products: {e}[/red]")
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
    df = pl.DataFrame()

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
        if df.is_empty():
            console.print(f"[red]Error downloading {product_id}[/red]")
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
    if not df.is_empty():
        df = df.sort(DATE_COL)

    return df, status_obj


def get_single_candle(
    product_id: str, params: dict = {}, df: typing.Optional[pl.DataFrame] = None
) -> pl.DataFrame:
    url = f"{BASE_URL}/products/{product_id}/candles"
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.get(url, params=params, headers=headers)
        bad_errors = 0
        if res.status_code > 399:
            bad_errors += 1
            console.print(f"[red]Coinbase error {res.status_code}: {res.text}[/red]")
            time.sleep(bad_errors * bad_errors * bad_errors)
            if bad_errors > 5:
                raise Exception(f"Api Error: {res.status_code} {res.text}")
        res = res.json()
        new_df = df_from_candles(res)
        if new_df.is_empty():
            bad_errors += 1
            if bad_errors > 0:
                raise Exception(f"Error Downloading: for {product_id}")
            return pl.DataFrame()
        sleep_time = random.random() * 0.5 + 0.1
        time.sleep(sleep_time)
        if df is None or df.width == 0:
            return new_df.unique(maintain_order=True)
        return pl.concat([df, new_df]).unique(maintain_order=True)
    except Exception as e:
        console.print(f"[red]Coinbase candle error: {e}[/red]")
        return pl.DataFrame()


def df_from_candles(klines) -> pl.DataFrame:
    """Turn the REST candle rows into a frame with a datetime "date" column."""
    if not klines:
        return pl.DataFrame(schema={**CB_REST_SCHEMA, DATE_COL: pl.Datetime})

    new_df = pl.DataFrame(klines, schema=CB_REST_SCHEMA, orient="row")
    new_df = new_df.unique(maintain_order=True)

    return new_df.with_columns(pl.from_epoch(DATE_COL, time_unit="s"))


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

    return end_date


if __name__ == "__main__":
    start = datetime.datetime(2024, 2, 7)
    get_product_candles("BTC-USD", start=start)

    # res.to_csv("btc.csv")
    # print(res)
    # print(res[0], res[1])
