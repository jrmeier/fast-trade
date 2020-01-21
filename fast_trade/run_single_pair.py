import pandas as pd
import os
import datetime
import json
import zipfile
import csv

from build_data_frame import build_data_frame


def determine_action(frame, strategy, df_col_map, datasaver):
    enter = take_action(frame, strategy["enter"], df_col_map)
    if enter:
        if datasaver:
            return "e"
        return [frame[0], "en", frame[1]]

    exit_position = take_action(frame, strategy["exit"], df_col_map)
    if exit_position:
        if datasaver:
            return "x"
        return [frame[0], "ex", frame[1]]

    if datasaver:
        return "h"
    return [frame[0], "h", frame[1]]


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


def run_single_pair(csv_path, strategy, pair, log_path, run_id, datasaver):
    if not os.path.isfile(csv_path):
        print("{} does not exist.".format(csv_path))
        return

    start = datetime.datetime.utcnow()
    df = build_data_frame(csv_path, strategy.get("indicators"))

    log = filter(
        None,
        [
            determine_action(frame, strategy, list(df.columns), datasaver)
            for frame in df.values
        ],
    )

    stop = datetime.datetime.utcnow()

    summary = {
        "name": strategy.get("name"),
        "run_id": run_id,
        "pair": pair,
        "start": start.strftime("%m/%d/%Y %H:%M:%S"),
        "stop": stop.strftime("%m/%d/%Y %H:%M:%S"),
        "total_time": str(stop - start),
        "log_file": None,
    }

    if log_path:
        strat_name = strategy.get("name").replace(" ", "")
        log_filename = "{}_log.csv".format(pair)

        strat_filename = "{}_strat.json".format(strat_name)

        with open(os.path.join(log_path, strat_filename), "w+") as strat_file:
            strat_file.write(json.dumps(strategy, indent=3))

        new_logpath = os.path.join(log_path, log_filename)

        summary["log_file"] = new_logpath + ".zip"

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
        summary_filename = "{}_sum.json".format(pair)
        summary_path = os.path.join(log_path, summary_filename)

        with open(summary_path, "w+") as summary_file:
            summary_file.write(json.dumps(summary, indent=3))
        
        os.remove(csv_path)
