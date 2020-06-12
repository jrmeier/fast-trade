import zipfile
import os
import csv
import json
import requests
import pandas as pd

# flake8: noqa
# this is a mess
def determine_ms_or_s(timestamp):
    if len(timestamp) == 10:
        return "s"

    return "ms"


def prep_ohlcv_from_zip(pair, base_csv_path=""):
    csv_filename = f"{pair}.csv"
    csv_path = f"{base_csv_path}/{csv_filename}"
    if not os.path.isfile(csv_path):
        # check for a zip
        if os.path.isfile("{}.zip".format(csv_path)):
            with zipfile.ZipFile("{}.zip".format(csv_path), "r") as zip_file:
                zip_file.extract(csv_filename, base_csv_path)

    return csv_path


def build_log_dataframe(log, symbol):
    csv_path = os.getenv("CSV_PATH")
    csv_filename = f"{csv_path}{symbol}.csv"
    csv_zipfilename = f"{csv_path}{symbol}.csv.zip"

    if os.path.isfile(csv_zipfilename):
        with zipfile.ZipFile(csv_zipfilename, "r") as zip_ref:
            zip_ref.extractall(f"{symbol}.csv")

    # print(csv_filename)


if __name__ == "__main__":
    csv_path = "/Users/jedmeier/2017_standard"
    res = prep_ohlcv_from_zip("BTCUSDT", csv_path)
    print("res: ", res)
