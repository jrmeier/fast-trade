# update archive, fetches all all the symbols, downloads the latest data and updates the archive

from calendar import c
import requests
import datetime
import os
import zipfile

from .update_symbol_data import get_symbol_meta_obj, update_symbol_data

# from ftc.constants import BINANCE_KLINE_REST_HEADER_MATCH
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


def get_base_url(tld="us"):
    return f"https://api.binance.{tld}/api/v3"


def get_exchange_info(tld="us"):
    url = get_base_url(tld)
    req = requests.get(f"{url}/exchangeInfo")
    return req.json()


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


def update_archive(exchange="binance.us"):
    """ Fetches and dowloads all the trading symbols from the exchange 
    
    Warning: This could take days to complete the first time and hours daily to update.
    """
    tld = exchange.split(".")[1]
    symbols = get_available_symbols(tld=tld)
    # symbols = ["1000SATSFDUSD"]
    print(f"Found {len(symbols)} symbols")
    for symbol in symbols:
        now = datetime.datetime.utcnow()
        # get check the metadata for the symbol
        meta = get_symbol_meta_obj(symbol=symbol)
        last_date = meta.get("last_date")

        if last_date > now - datetime.timedelta(hours=2):
            print(f"Skipping {symbol} because it was updated recently (last update: {last_date.isoformat()})")
            continue

        if last_date == meta.get("start_date"):
            start_date = get_oldest_date_available(symbol, tld).isoformat()
        else:
            start_date = last_date.isoformat()

        update_symbol_data(symbol=symbol, exchange=exchange, start_date=start_date, end_date=now.isoformat())


def zip_data(symbol=None, years_to_zip=[], ARCHIVE_PATH="./archive"):
    """ Zip the data for the symbol """
    if not symbol:
        # get all the symbols in the archive
        symbols = []
        for file in os.listdir(ARCHIVE_PATH):
            if file.endswith(".json"):
                symbols.append(file.split("_")[0])

    print(f"Zipping {len(symbols)} symbols")
    for symbol in symbols:
        zip_symbol(symbol=symbol, years_to_zip=years_to_zip, ARCHIVE_PATH=ARCHIVE_PATH)
    # get all the files that start with the symbol


def zip_symbol(symbol, years_to_zip, ARCHIVE_PATH):
    files_to_zip = []
    for file in os.listdir(ARCHIVE_PATH):
        if not file.startswith(symbol):
            continue

        if not file.endswith(".csv"):
            continue
        # print(file)
        if not len(file.split("_")) != 1:
            continue
        if not file.split("_")[1].endswith(".csv"):
            continue
        # print("doing it")

        year = file.split("_")[1].split(".")[0]
        print(year, years_to_zip, year in years_to_zip)
        if year in years_to_zip:
            print("doing it")
            files_to_zip.append(file)

    print(f"Zipping {len(files_to_zip)} files for {symbol}")
    # print(files_to_zip)
    # final_files_to_zip = []
    # # get the years to zip
    # for files in files_to_zip:
    #     year = files.split("_")[1]
    #     if year in years_to_zip:
    #         final_files_to_zip.append(year)

    # # zip the files
    # for file in final_files_to_zip:
    #     # use ZipFile to zip the files
    #     with zipfile.ZipFile(f"{file}.zip", 'w') as zipf:
    #         for file in files:
    #             zipf.write(file)

    # print(f"Zipped {len(final_files_to_zip)} files for {symbol}")



if __name__ == "__main__":
    zip_data(years_to_zip=[2017, 2018, 2019, 2020, 2021, 2022, 2023])