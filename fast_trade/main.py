from build_data_frame import build_data_frame
import os
import datetime
import re
import json
import zipfile
import pandas as pd
import uuid
import random
import string


def run_pair_sim(csv_path, strategy, pair, log_path, run_id, remove_csv=False, avg_time=None):
    # take in the dataframe
    # take in the strategy
    # read each frame
    if not os.path.isfile(csv_path):
        print("{} does not exist.".format(csv_path))
        return

    start = datetime.datetime.utcnow()
    df = build_data_frame(csv_path, strategy.get('indicators', []))
    def run_it(frame):
        last_price = frame['close']
        enter = take_action(frame, strategy['enter'])
        exit_position = take_action(frame, strategy['exit'])
        if enter:
            return 'enter'
        if exit_position:
            return 'exit'
        if not enter and not exit_position:
            return 'hold'

    df['action'] = df.apply(lambda frame: run_it(frame), axis=1)
    stop = datetime.datetime.utcnow()

    log = pd.DataFrame()
    log['date'] = df['date']
    log['action'] = df['action']
    log['close'] = df['close']
    
    summary = {
        "name": strategy.get('name'),
        "run_id": run_id,
        "pair": pair,
        "start": start.strftime("%m/%d/%Y %H:%M:%S"),
        "stop": stop.strftime("%m/%d/%Y %H:%M:%S"),
        "total_time": str(stop - start),
        "log_file": None,
    }

    if log_path:
        strat_name = strategy.get('name').replace(" ","")
        log_filename = "{}_log.csv".format(pair)

        strat_filename = "_{}_strat.json".format(strat_name)

        with open(os.path.join(log_path, strat_filename), 'w+') as strat_file:
            strat_file.write(json.dumps(strategy, indent=3))


        new_logpath = os.path.join(log_path, log_filename)

        summary['log_file'] = new_logpath + ".zip"

        log.to_csv(new_logpath,index=False)

        with zipfile.ZipFile(f"{new_logpath}.zip", "w") as log_zip:
            log_zip.write(
                new_logpath, compress_type=zipfile.ZIP_DEFLATED, arcname=log_filename,
            )
        os.remove(new_logpath)
        summary_filename = "{}_sum.json".format(pair)
        summary_path = os.path.join(log_path, summary_filename)

        with open(summary_path, 'w+') as summary_file:
            summary_file.write(json.dumps(summary, indent=3))

    # remove the csv file?
    if remove_csv:
        os.remove(csv_path)



def take_action(df_row, strategy):
    results = []
    for each in strategy:
        if each[1] == ">":
            results.append(bool(df_row[each[0]] > df_row[each[2]]))
        if each[1] == "<":
            results.append(bool(df_row[each[0]] < df_row[each[2]]))
        if each[1] == "=":
            results.append(bool(df_row[each[0]] == df_row[each[2]]))
    
    if len(results):
        return all(results)

def main(pairs, strategy, csv_base, log_path):
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
        print("{} {}/{}".format(pair, pairs.index(pair)+1, len(pairs)))
        csv_path = os.path.join(csv_base, csv_filename)
        remove_csv = False
        if not os.path.isfile(csv_path):
            # check for a zip
            if os.path.isfile("{}.zip".format(csv_path)):
                with zipfile.ZipFile("{}.zip".format(csv_path), "r") as zip_file:
                    zip_file.extractall(csv_base)
                remove_csv = True

        run_pair_sim(csv_path, strategy, pair, log_path, run_id, remove_csv)



    run_stop = datetime.datetime.utcnow()
    run_sum = {
        "id": run_id,
        "total_time": str(run_stop - run_start),
        "start": run_start.strftime("%m/%d/%Y %H:%M:%S"),
        "stop": run_stop.strftime("%m/%d/%Y %H:%M:%S"),
        "strategy": strategy,
        "pairs": pairs
    }
    if log_path:
        run_sum_path = os.path.join(log_path, "RunSummary.json")
        with open(run_sum_path, 'w+') as new_run_log:
            new_run_log.write(json.dumps(run_sum, indent=3))

if __name__ == "__main__":
    # csv_base = "/Users/jedmeier/Projects/fast_trade/fast_trade"
    csv_base = "/Users/jedmeier/zipped"
    log_path = "/Users/jedmeier/Projects/fast_trade/fast_trade/logs"
    
    # csv_base = "/home/jedmeier/crypto-data/crypto_data/2017_standard"
    # log_path = "/home/jedmeier/fast_trade/fast_trade/logs"
    # log_path = None
    # pairs = ["BTCUSDT_sample"]
    with open("../2017_all.json") as all_pairs_file:
        pairs = json.load(all_pairs_file)
    
    with open("../SimpleMa.strat.json") as strat_file:
        strategy = json.load(strat_file)
    
    main(pairs, strategy, csv_base, log_path)