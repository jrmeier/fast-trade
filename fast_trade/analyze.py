import zipfile
import os
import csv
import json

def anaylze(log_filepath):
    arc_name = log_filepath.split("/")[-1].split(".zip")[0]

    unzipped_path = "/".join(log_filepath.split("/")[:-1])
    unzipped_file = f"{unzipped_path}/{arc_name}"
    if not os.path.isfile(unzipped_file):
        with zipfile.ZipFile(log_filepath, "r") as zip_ref:
          zip_ref.extractall(unzipped_path)


    with open(log_filepath, 'r') as opened_file:
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

    

    return sum(diffs)


if __name__ == "__main__":
    log_filepath = "./fast_trade/logs/run_01_17_2020_21_51_35/ZRXETH_log.csv"

    res = anaylze(log_filepath)

    print(res)
    