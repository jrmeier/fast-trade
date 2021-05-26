"""
This file can be used out side of the fast-trade library or from the command line.

This script is to help download and update a local version of kline data from Binance.

See the README in this repository for more details.


How to use

1. Set an archive path
    - this is where the data will be store. Everything in here will be managed by this script.

2. Set the other settings
    - these are pretty self-explanatory

3. Run the script

    ft download --symbol=BTCUSDT --start=2017-01-01

The data takes a while to download, but once its downloaded the first time, you can just run the script and it will
get the since the most recent download.


Troubleshooting
If something isn't updating correctly, delete the SYMBOL_meta.json file.

If you originally want to load the file from an earlier date, delete the "first_date" property in the meta file
and then pass in --start=YYYY-m-d

"""

import pandas as pd
import datetime
import os
import re
import csv
import json
from collections import deque
from json.decoder import JSONDecodeError
import time
import random

import requests  # requires python-binance, not included in fast-trade package

# ARCHIVE_PATH = "/Users/jedmeier/Desktop"  # where to store the downloaded csv
# SYMBOL = "ETHBTC"
# tmp_start_date = '2017-01-01' # the date which it start asking for the data you want

# START_DATE = int(datetime.datetime.fromisoformat(tmp_start_date).timestamp())
# EXCHANGE = "binance.com"  # binance.com or binance.us


def update_symbol_data(
    symbol, start_date, end_date="", arc_path="./archive", exchange="binance.us"
):
    print(f"updating: {symbol}")

    global ARCHIVE_PATH
    ARCHIVE_PATH = arc_path  # where to store the downloaded csv
    global SYMBOL
    SYMBOL = symbol
    global START_DATE
    START_DATE = int(datetime.datetime.fromisoformat(start_date).timestamp())

    global EXCHANGE
    EXCHANGE = exchange  # binance.com or binance.us
    update_symbol_meta(symbol)
    meta_obj = get_symbol_meta_obj(symbol)
    last_date = meta_obj.get("last_date")

    if not isinstance(last_date, datetime.datetime):
        start_date_dt = datetime.datetime.fromtimestamp(last_date).replace(
            second=0, microsecond=0
        )
    else:
        start_date_dt = last_date.replace(second=0, microsecond=0)

    if not end_date:
        end_date_dt = datetime.datetime.utcnow().replace(second=0, microsecond=0)
    else:
        end_date_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").replace(
            second=0, microsecond=0
        )

    # this is so we can skip an unnessesary request
    if end_date_dt > datetime.datetime.utcnow():
        end_date_dt = datetime.datetime.utcnow().replace(second=0, microsecond=0)

    DAYS_TO_INCREMENT = 30
    curr_date = start_date_dt

    while curr_date < end_date_dt:
        next_end_date = curr_date + datetime.timedelta(days=DAYS_TO_INCREMENT)
        print(f"fetching klines for dates between {curr_date} and {next_end_date}")

        try:
            klines_df = load_historical_klines_as_df(symbol, curr_date, next_end_date)

            if not klines_df.empty:
                years_in_klines = klines_df.index.strftime("%Y").unique().tolist()
                year_df = klines_df[klines_df.index.year == int(years_in_klines[0])]

                for year in years_in_klines:
                    year_df = klines_df[klines_df.index.year == int(year)]
                    archive_csv_filename = f"{symbol}_{year}.csv"

                    update_symbol_meta(symbol, {"updating": True})
                    update_archive_csv_by_df(archive_csv_filename, year_df)

            else:
                print(
                    f"No data from {curr_date} to {next_end_date} for symbol {symbol} "
                )
                time.sleep(random.uniform(0.5, 1.3))

        except Exception as e:
            print(f"Error updating symbol {symbol}\nError: ", e)
            time.sleep(5)

        curr_date += datetime.timedelta(days=DAYS_TO_INCREMENT)

    update_symbol_meta(symbol, {"updating": False})
    # keep it slow to avoid rate limiting
    time.sleep(random.uniform(0.5, 1.3))


def update_archive_csv_by_df(archive_csv_filename, new_df):
    """Parameters:
        archive_csv_filename: file name to open and add data to
        new_df: dataframe to verify and add to existing file
    Purpose:
        To have clean, de-duplicated data store in this file
        based on this dataframe
    """
    archive_csv_path = f"{ARCHIVE_PATH}/{archive_csv_filename}"

    # load the csv, if exists
    if os.path.exists(archive_csv_path):
        exisiting_df = pd.read_csv(
            archive_csv_path,
            usecols=CSV_HEADER,
        )
        exisiting_df.index = exisiting_df.date
    else:  # create something to combine
        exisiting_df = pd.DataFrame()

    # print(exisiting_df, new_df)

    # combine the data frames
    combined_df = pd.concat([exisiting_df, new_df])

    # de duplicate the dataframe
    combined_df.drop_duplicates(inplace=True)

    # There's BUG here. After ts 1608444000,  the date isnt formated and breaks.
    # I think its to do with the large file sizes.
    # If the below worked, we wouldn't need to go futher.
    # combined_df.to_csv(archive_csv_path, date_format="%s")

    # this is because the to_csv() function doesnt work with these large files
    def process_row(row):
        # print(row)
        if type(row[0]) is int or type(row[0]) is float:
            date_ts = row[0]
        else:
            date_ts = int(row[0].timestamp())
        return [
            date_ts,
            float(row.open),
            float(row.high),
            float(row.low),
            float(row.close),
            float(row.volume),
        ]

    # get the rows in a usuable format
    rows_to_write = [process_row(row) for row in combined_df.itertuples()]

    # write the new rows to a CSV
    with open(archive_csv_path, "w") as archive_file:
        writer = csv.writer(archive_file)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows_to_write)

    # done updating the csv


def standardize_df(df):
    new_df = df.copy()

    if "date" in new_df.columns:
        new_df = new_df.set_index("date")
    elif "time" in new_df.columns:
        new_df = new_df.set_index("time")

    new_df.index = pd.to_datetime(new_df.index, unit="s")
    new_df = new_df[~new_df.index.duplicated(keep="first")]
    new_df = new_df.sort_index()
    columns_to_drop = [
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_base_a_volume",
        "ignore",
        "date",
    ]

    new_df = new_df.drop(columns=columns_to_drop, errors="ignore")

    new_df.open = pd.to_numeric(new_df.open)
    new_df.close = pd.to_numeric(new_df.close)
    new_df.high = pd.to_numeric(new_df.high)
    new_df.low = pd.to_numeric(new_df.low)
    new_df.volume = pd.to_numeric(new_df.volume)

    return new_df


def get_symbol_meta_obj(symbol, key=None):
    meta_data_filename = f"{ARCHIVE_PATH}/{symbol}_meta.json"

    default_meta_obj = {
        "last_date": START_DATE,
        "first_date": START_DATE,
        "updating": False,
        "years": [],
    }

    # check to see if the meta object file exists
    try:
        if os.path.exists(meta_data_filename):
            with open(meta_data_filename, "r") as meta_file:
                meta_obj = json.load(meta_file)
        else:
            meta_obj = default_meta_obj

        # validate it has default keys
        for default_key in default_meta_obj.keys():
            if default_key not in meta_obj.keys():
                meta_obj[default_key] = default_meta_obj[default_key]

        if key:
            return meta_obj.get(key)
        return meta_obj

    except (JSONDecodeError, FileNotFoundError):
        if key:
            return default_meta_obj.get(key)
        return default_meta_obj


def update_symbol_meta(symbol, new_object={}):
    # now open the lowest year file
    symbol_meta_file_path = f"{ARCHIVE_PATH}/{symbol}_meta.json"

    if not os.path.exists(ARCHIVE_PATH):
        print("creating new archive directory: ", ARCHIVE_PATH)
        os.mkdir(ARCHIVE_PATH)

    # open the existing archive
    meta_obj = get_symbol_meta_obj(symbol)
    meta_obj.update(new_object)

    # if the years don't exist, look for them in the archive folder
    years = []
    for f in os.listdir(ARCHIVE_PATH):
        file_reg = r"^([A-Z]{3,}\_2\d{3,})"
        file_str = re.search(file_reg, f)

        if file_str:
            symbol_with_year = file_str.group()
            curr_symbol = symbol_with_year.split("_")[0]
            year = symbol_with_year.split("_")[1]
            if symbol == curr_symbol:
                years.append(year)

    meta_obj["years"] = years

    if len(years):
        years = [int(y) for y in years]
        years.sort()
        earliest_year = years[0]
        latest_year = years[-1]

        if os.path.exists(f"{ARCHIVE_PATH}/{symbol}_{earliest_year}.csv"):
            with open(
                f"{ARCHIVE_PATH}/{symbol}_{earliest_year}.csv", "r"
            ) as earliest_file:
                earliest_file.readline()
                line2 = earliest_file.readline().split(",")
            meta_obj["first_date"] = int(line2[0])

        # now open the newest file and get the last row
        with open(f"{ARCHIVE_PATH}/{symbol}_{latest_year}.csv", "r") as latest_file:
            last_line = deque(latest_file, 1)[0].split(",")
            meta_obj["last_date"] = int(last_line[0])
    else:
        # this means we have nothing, so we should set these manually
        meta_obj["first_date"] = START_DATE
        meta_obj["last_date"] = START_DATE

    meta_obj["last_modified"] = int(datetime.datetime.utcnow().timestamp())
    with open(symbol_meta_file_path, "w") as symbol_meta_file:
        symbol_meta_file.write(json.dumps(meta_obj, indent=2))

    return meta_obj


def load_historical_klines_as_df(symbol, start_date, end_date):
    klines = get_historical_klines_binance(symbol, start_date, end_date)

    klines_df = binance_kline_to_df(klines)

    return klines_df


def get_historical_klines_binance(symbol, start_date, end_date, EXCHANGE="us"):
    if EXCHANGE == "us":
        tld = "us"
    else:
        tld = "com"
    base_url = f"https://api.binance.{tld}/api/v3"

    curr_date = start_date

    HOURS_TO_INCREMENT = 15

    if end_date > datetime.datetime.utcnow():
        end_date = datetime.datetime.utcnow().replace(second=0, microsecond=0)

    total_api_calls = 0
    klines = []
    while curr_date < end_date:
        next_end_date = curr_date + datetime.timedelta(hours=HOURS_TO_INCREMENT)
        startTime = int(curr_date.timestamp()) * 1000
        endTime = int(next_end_date.timestamp()) * 1000

        url = f"{base_url}/klines?symbol={symbol}&interval=1m&startTime={startTime}&endTime={endTime}&limit=1000"
        data = requests.get(url).json()
        klines.extend(data)

        total_api_calls += 1

        sleeper = random.random() * 0.9
        if sleeper < 0.3:
            sleeper += 0.3

        if total_api_calls % 25 == 0:
            sleeper += random.randint(10, 60)

        time.sleep(sleeper)
        curr_date = next_end_date

    return klines


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


def get_existing_archives(archive_path):
    """
    Returns all the existing archives as symbols
    """
    symbols = []
    for f in os.listdir(archive_path):
        regex_str = r"[A-Z]{3,}\_meta.json"
        for csv_file in re.findall(regex_str, f):
            symbol = csv_file.split("_")[0]
            symbols.append(symbol)

    return symbols


def load_archive_to_df(symbol, archive_path):
    # check if we have it in the archive
    if symbol not in get_existing_archives(archive_path):
        print(f"Nothing in archive for {symbol}")
        return pd.DataFrame()
    # load all the files we can
    files_to_load = []
    # get date now, figure out how many days
    now = datetime.datetime.utcnow()

    # open the archive meta and get the oldest year
    with open(f"{archive_path}/{symbol}_meta.json", "r") as meta_file:
        meta_file = json.load(meta_file)
        years = meta_file.get("years", [])
        years = [int(year) for year in years]
        years.sort()

    year = years[0]

    files_to_load.append(f"{symbol}_{now.year}.csv")

    for year in range(year, now.year):
        files_to_load.append(f"{symbol}_{year}.csv")

    year_dfs = []

    for file_to_load in files_to_load:
        file_to_load_path = f"{archive_path}/{file_to_load}"
        if os.path.exists(file_to_load_path):
            file_df = pd.read_csv(file_to_load_path)
            year_dfs.append(file_df)

    new_df = pd.concat(year_dfs)
    new_df = new_df.drop_duplicates()
    new_df = standardize_df(new_df)

    return new_df


CSV_HEADER = ["date", "low", "high", "open", "close", "volume"]

BINANCE_KLINE_REST_HEADER_MATCH = [
    "date",  # Open time
    "open",  # Open
    "high",  # High
    "low",  # Low
    "close",  # Close
    "volume",  # Volume
    "close_time",  # Close time
    "quote_asset_volume",  # Quote asset volume
    "number_of_trades",  # Number of trades
    "taker_buy_base_asset_volume",  # Taker buy base asset volume
    "taker_buy_base_a_volume",  # Taker buy quote
    "ignore",  # literally ignore this
]
