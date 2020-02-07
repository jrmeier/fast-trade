import os
import datetime
import json
import zipfile
import pandas as pd
import uuid
from indicator_map import indicator_map
from build_data_frame import build_data_frame

from generate_strategy import generate_strategy
from run_single_backtest import run_single_backtest
from dotenv import load_dotenv


def run_many_pairs(pairs, strategy, csv_base, log_path):
    # prep the csv files, the might be zipped
    run_start = datetime.datetime.utcnow()

    # create_log_dir(log_path)

    for pair in pairs:
        print("{} {}/{}".format(pair, pairs.index(pair) + 1, len(pairs)))

        res = run_single_backtest(csv_path, strategy)
        print(json.dumps(res, indent=4))
    run_stop = datetime.datetime.utcnow()


if __name__ == "__main__":
    load_dotenv()
    pairs = []
    strategy = None

    csv_path = os.getenv("CSV_PATH")
    log_path = os.getenv("LOG_PATH")
    pairs = ["BTCUSDT"]

    for each in range(0, 1):
        strategy = generate_strategy()
        run_many_pairs(pairs, strategy, csv_path, log_path)
