import pandas as pd
import os
import datetime
import json
import zipfile

from build_data_frame import build_data_frame

def determine_action_iter(frame, strategy):
    last_price = frame['close']
    enter = take_action(frame, strategy['enter'])
    exit_position = take_action(frame, strategy['exit'])
    if enter:
        return 'enter'
    if exit_position:
        return 'exit'
    if not enter and not exit_position:
        return 'hold'

def run_single_pair(csv_path, strategy, pair, log_path, run_id, remove_csv=False, avg_time=None):
    if not os.path.isfile(csv_path):
        print("{} does not exist.".format(csv_path))
        return

    start = datetime.datetime.utcnow()
    df = build_data_frame(csv_path, strategy.get('indicators'))

    df['action'] = df.apply(lambda frame: determine_action_iter(frame, strategy), axis=1)
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