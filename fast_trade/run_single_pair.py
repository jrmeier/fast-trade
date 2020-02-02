import pandas as pd
import os
import datetime
import json
import zipfile
import csv
from dotenv import load_dotenv

from build_data_frame import build_data_frame
from run_analysis import analyze_df


def determine_action(frame, strategy, df_col_map):
    if take_action(frame, strategy["enter"], df_col_map):
        return "e"

    if take_action(frame, strategy["exit"], df_col_map):
        return "x"

    return "h"


def take_action(raw_row, strategy, columns):
    results = []

    df_col_map = {}
    for idx, each in enumerate(columns):
        df_col_map[each] = raw_row[idx]

    for each in strategy:
        if each[1] == ">":
            results.append(bool(df_col_map[each[0]] > df_col_map[each[2]]))
        if each[1] == "<":
            results.append(bool(df_col_map[each[0]] < df_col_map[each[2]]))
        if each[1] == "=":
            results.append(bool(df_col_map[each[0]] == df_col_map[each[2]]))

    if len(results):
        return all(results)


def run_single_pair(csv_path, strategy, pair, log_path, run_id, starting_balance, profit_perc):
    if not os.path.isfile(csv_path):
        print("{} does not exist.".format(csv_path))
        return

    start = datetime.datetime.utcnow()
    df = build_data_frame(csv_path, strategy.get("indicators"))

    df["actions"] = [
        determine_action(frame, strategy, list(df.columns)) for frame in df.values
    ]

    stop = datetime.datetime.utcnow()
    base, aux = analyze_df(df, starting_balance)
    df["base_balance"] = base
    # = df.iloc[[0, -1]]


    summary = {
        "pair": pair,
        "start": start.strftime("%m/%d/%Y %H:%M:%S"),
        "stop": stop.strftime("%m/%d/%Y %H:%M:%S"),
        "total_time": str(stop - start),
        "log_file": None,
        "starting_base": 0,
        "ending_base": df.iloc[-1]['base_balance'],
        "starting_aux": starting_balance,
        "ending_aux": df.iloc[-1]['aux_balance'],
        "aux_max": df["aux_balance"].max(),
        "base_max": df["base_balance"].max()

    }

    if df['aux_balance'].max() > starting_balance * profit_perc:
        print("okay I'm saving it")
    # save_summary_file(summary, log_path)

    # print(summary)
    # df.to_csv("what.csv")
    # os.remove(csv_path)

    # save_log_file(strategy, pair, log_path, actions, summary)
    return summary

def save_summary_file(summary, log_path):
    summary_filename = "{}_sum.json".format(pair)
    summary_path = os.path.join(log_path, summary_filename)

    with open(summary_path, "w+") as summary_file:
        summary_file.write(json.dumps(summary, indent=2))


def save_log_file(strategy, pair, log_path, log, summary):
    strat_name = strategy.get("name").replace(" ", "")
    log_filename = "{}_log.csv".format(pair)

    strat_filename = "{}_strat.json".format(strat_name)

    with open(os.path.join(log_path, strat_filename), "w+") as strat_file:
        strat_file.write(json.dumps(strategy, indent=3))

    new_logpath = os.path.join(log_path, log_filename)

    # summary["log_file"] = new_logpath + ".zip"

    with open(new_logpath, "w") as new_logfile:
        file_writer = csv.writer(
            new_logfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
        )
        file_writer.writerows(log)

    with zipfile.ZipFile(f"{new_logpath}.zip", "w") as log_zip:
        log_zip.write(
            new_logpath, compress_type=zipfile.ZIP_DEFLATED, arcname=log_filename,
        )
    
    os.remove(new_logpath)


if __name__ == "__main__":
    # def run_single_pair(csv_path, strategy, pair, log_path, run_id, datasaver):
    load_dotenv()
    csv_path = f"{os.getenv('CSV_PATH')}BTCUSDT.csv"
    log_path = os.getenv("LOG_PATH")

    with open("./example_strat.json", "r") as strat_file:
        strategy = json.load(strat_file)

    pair = "BTCUSDT"
    run_id = "123"
    datasaver = True
    # print("csv_file: ",csv_path)
    starting_balance = 1000
    # profit percentage to save log file
    profit_perc = 1.2
    run_single_pair(csv_path, strategy, pair, log_path, run_id, starting_balance, profit_perc)
