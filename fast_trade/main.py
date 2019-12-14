from build_data_frame import build_data_frame
import os
import datetime
import re
import json
import zipfile
import pandas as pd


def run_pair_sim(csv_path, strategy, pair, log_path, current_time, remove_csv=False):
    # take in the dataframe
    # take in the strategy
    # read each frame
    if not os.path.isfile(csv_path):
        print("{} does not exist.".format(csv_path))
        return

    start = datetime.datetime.now()
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
    stop = datetime.datetime.now()

    log = pd.DataFrame()
    log['date'] = df['date']
    log['action'] = df['action']
    log['close'] = df['close']

    summary = {
        "strategy": strategy.get('name'),
        "pair": pair,
        "start": start.strftime("%m_%d_%Y__%H_%M_%S"),
        "stop": stop.strftime("%m_%d_%Y__%H_%M_%S"),
        "total_time": str(stop - start),
        "log_file": None,
    }

    if log_path:
        strat_name = strategy.get('name').replace(" ","")
        log_filename = "{}_{}_{}_log.csv".format(strat_name, pair, current_time)

        summary['log_file'] = log_filename
        new_logpath = os.path.join(log_path, log_filename)
        log.to_csv(new_logpath,index=False)

        summary_filename = "{}_{}_{}_summary.json".format(strategy.get('name'), pair, current_time)

        summary_path = os.path.join(log_path, summary_filename)

        with open(summary_path, 'w+') as summary_file:
            summary_file.write(json.dumps(summary, indent=3))

    print(summary)
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
    current_time = datetime.datetime.now().strftime("%m_%d_%Y__%H_%M_%S")
    for pair in pairs:
        csv_filename = "{}.csv".format(pair)
        csv_path = os.path.join(csv_base, csv_filename)
        remove_csv = False
        if not os.path.isfile(csv_path):
            # check for a zip
            if os.path.isfile("{}.zip".format(csv_path)):
                with zipfile.ZipFile("{}.zip".format(csv_path), "r") as zip_file:
                    zip_file.extractall(csv_base)
                remove_csv = True

        run_pair_sim(csv_path, strategy, pair, log_path, current_time, remove_csv)

if __name__ == "__main__":
    # csv_path = 'BTCUSDT_sample.csv'
    csv_base = "/Users/jedmeier/Projects/fast_trade/fast_trade"
    log_path = "/Users/jedmeier/Projects/fast_trade/fast_trade/logs"
    # csv_base = "/home/jedmeier/crypto-data/crypto_data/2017_standard"
    # log_path = "/home/jedmeier/fast_trade/fast_trade/logs"
    # log_path = None
    pairs = ["BTCUSDT_sample"]
    # with open("../2017_all.json") as all_pairs_file:
    #     pairs = json.load(all_pairs_file)
    
    
    strategy = {
        "name": "Simple MA",
        "enter": [
            ('short','>','mid'), # ref to compare, operator, other ref to compare
            ('short', '>', 'long')
            ],
        "exit": [('short','<', 'mid')],
        "indicators": [ # must be a list, must look like below
            {
                'ref':'short', # reference for strategy
                'name': 'ta.ma', # indicator name
                'timeperiod': 4, # timeperiod to use
                'df':'close' # data frame column name
            },
            {   'ref':'mid',
                'name': 'ta.ma',
                'timeperiod': 10,
                'df':'close'
            },
            {   'ref':'long',
                'name': 'ta.ma',
                'timeperiod': 21,
                'df':'close'
            },
        ]

    }

    main(pairs, strategy, csv_base, log_path)
