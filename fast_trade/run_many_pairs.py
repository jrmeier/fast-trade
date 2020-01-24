import os
import datetime
import json
import zipfile
import pandas as pd
import uuid
from indicator_map import indicator_map
from build_data_frame import build_data_frame

from generate_strategy import generate_strategy
from run_single_pair import run_single_pair
from dotenv import load_dotenv


def run_many_pairs(pairs, strategy, csv_base, log_path, datasaver):
    # prep the csv files, the might be zipped
    run_id = str(uuid.uuid4())
    run_start = datetime.datetime.utcnow()

    if log_path:
        run_dir_name = "run_{}".format(run_start.strftime("%m_%d_%Y_%H_%M_%S"))
        log_path = os.path.join(log_path, run_dir_name)
        if not os.path.isdir(log_path):
            os.mkdir(log_path)

    for pair in pairs:
        csv_filename = "{}.csv".format(pair)
        print("{} {}/{}".format(pair, pairs.index(pair) + 1, len(pairs)))
        time_elapsed = datetime.datetime.utcnow() - run_start
        status = {
            "current_pair": pair,
            "current_location": pairs.index(pair) + 1,
            "total_pairs": len(pairs),
            "time_elapsed": str(time_elapsed),
            "perc_complete": str((pairs.index(pair) + 1 / len(pairs))),
        }

        status_path = os.path.join(log_path, "status.json")
        with open(status_path, "w+") as status_file:
            status_file.write(json.dumps(status))

        csv_path = os.path.join(csv_base, csv_filename)
        remove_csv = False
        if not os.path.isfile(csv_path):
            # check for a zip
            if os.path.isfile("{}.zip".format(csv_path)):
                with zipfile.ZipFile("{}.zip".format(csv_path), "r") as zip_file:
                    zip_file.extractall(csv_base)
                remove_csv = True

        run_single_pair(csv_path, strategy, pair, log_path, run_id, datasaver)

    run_stop = datetime.datetime.utcnow()
    run_sum = {
        "id": run_id,
        "total_time": str(run_stop - run_start),
        "start": run_start.strftime("%m/%d/%Y %H:%M:%S"),
        "stop": run_stop.strftime("%m/%d/%Y %H:%M:%S"),
        "strategy": strategy,
        "pairs": pairs,
    }
    if log_path:
        run_sum_path = os.path.join(log_path, "RunSummary.json")
        with open(run_sum_path, "w+") as new_run_log:
            new_run_log.write(json.dumps(run_sum, indent=3))


if __name__ == "__main__":
    load_dotenv()
    pairs = []
    strategy = None

    csv_path = os.getenv("CSV_PATH")
    log_path = os.getenv("LOG_PATH")
    config_path = os.getenv("CONFIG_PATH")

    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    datasaver = config.get("datasaver", False)

    if config.get("pairs"):
        pairs = config.get("pairs")

    if not pairs:
        with open(config.get("pairs_file", "r")) as pairs_file:
            pairs = json.load(pairs_file)

    if config.get("strategy_file"):
        with open(config.get("strategy_file", "r")) as strat_file:
            strategy = json.load(strat_file)

    for each in range(0, config.get("iterations", 1)):
        strategy = generate_strategy()
        run_many_pairs(pairs, strategy, csv_path, log_path, datasaver)
