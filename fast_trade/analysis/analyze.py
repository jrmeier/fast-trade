import zipfile
import os
import csv
import json
import requests

def analyze_file(log_filepath):
    arc_name = log_filepath.split("/")[-1].split(".zip")[0]

    unzipped_path = "/".join(log_filepath.split("/")[:-1])
    unzipped_file = f"{unzipped_path}/{arc_name}"
    if not os.path.isfile(unzipped_file):
        with zipfile.ZipFile(log_filepath, "r") as zip_ref:
            zip_ref.extractall(unzipped_path)

    with open(log_filepath, "r") as opened_file:
        log = csv.reader(opened_file, delimiter=",")
        logs = list(log)[1:]

    in_trade = False
    transactions = []
    diffs = []
    for row in logs:
        if row[1] == "en" and not in_trade:
            transactions.append(row)
            in_trade = True

        if row[1] == "ex" and in_trade:
            diff = round(float(row[2]) - float(transactions[-1][2]), 8)
            diffs.append(diff)
            transactions.append(row)
            in_trade = False

    return diffs


def process_run_path(run_obj):
    # get the log file
    # buid the real path
    for log_obj in run_obj:

        for pair in log_obj['pairs']:
            pair_obj = log_obj['pairs'][pair]
            log_filepath = f"{log_obj['base_path']}{pair_obj['log']}"
            # call the analysis function



def get_log_files(log_path):
    run_paths = []
    for run in os.listdir(log_path):
        base_path = f"{log_path}{run}/"
        log_obj = {
            "base_path": base_path,
            "RunSummary": None,
            "strat": None,
            "pairs": {}
        }

        # this is each file in the base path
        for run_file in os.listdir(base_path):
            if run_file == "RunSummary.json":
                log_obj["RunSummary"] = run_file
            if "_strat" in run_file:
                log_obj["strat"] = run_file

            # symbol specific stuff
            symbol = run_file.split("_log")[0]
            if "_log" in run_file:
                if log_obj["pairs"].get(symbol):
                    log_obj["pairs"][symbol]['log'] = run_file
                else:
                    log_obj["pairs"][symbol] = {}
                    log_obj["pairs"][symbol]['log'] = run_file
            
            if "_sum" in run_file:
                symbol = run_file.split("_sum")[0]
                if log_obj["pairs"].get(symbol):
                    log_obj["pairs"][symbol]['sum'] = run_file
                else:

                    log_obj["pairs"][symbol] = {}
                    log_obj["pairs"][symbol]['sum'] = run_file      
        run_paths.append(log_obj)

    return run_paths


if __name__ == "__main__":
    # log_filepath = "./fast_trade/logs/run_01_17_2020_21_51_35/ZRXETH_log.csv"
    # log_path = "/Users/jedmeier/fast_trade/fast_trade/logs/"
    # res = anaylze(log_filepath)

    # res = get_log_files(log_path)
    # print(json.dumps(res, indent=2))
    
    run_paths = [{
    "base_path": "/Users/jedmeier/fast_trade/fast_trade/logs/run_01_23_2020_20_51_25/",
    "RunSummary": "RunSummary.json",
    "strat": "second-hand-trains_strat.json",
    "pairs": {
      "ETHBTC": {
        "sum": "ETHBTC_sum.json",
        "log": "ETHBTC_log.csv.zip"
      },
      "BTCUSDT": {
        "sum": "BTCUSDT_sum.json",
        "log": "BTCUSDT_log.csv.zip"
      }
    }
    }]

    res = process_run_path(run_paths)

