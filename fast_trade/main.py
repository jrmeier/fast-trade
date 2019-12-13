from build_data_frame import build_data_frame
import os
import datetime
import re
import json
import zipfile



def run_pair_sim(csv_path, strategy, pair, log_path, remove_csv=False):
    # take in the dataframe
    # take in the strategy
    # read each frame
    if not os.path.isfile(csv_path):
        print("{} does not exist.".format(csv_path))
        return

    start = datetime.datetime.now()

    data_frame = build_data_frame(csv_path, strategy.get('indicators', []))
    log = []
    
    for frame in data_frame.iterrows():
        last_price = frame[1]['close']
        enter = take_action(frame[1], strategy['enter'])
        exit_position = take_action(frame[1], strategy['exit'])
        log_obj = []
        if enter:
            log_obj = [frame[1]['date'],'enter',last_price]
        if exit_position:
            log_obj = [frame[1]['date'],'exit',last_price]
        if not enter and not exit_position:
            log_obj = [frame[1]['date'],'hold',last_price]
        
        if log_path and log_obj:
            log.append(log_obj)
    
    stop = datetime.datetime.now()
    
    total_time = stop - start
    summary = {
        "strategy": strategy.get('name'),
        "pair": pair,
        "start": start.strftime("%m_%d_%Y__%H_%M_%S"),
        "stop": stop.strftime("%m_%d_%Y__%H_%M_%S"),
        "total_time": str(total_time),
        "log_file": None,
    }

    if log_path:
        current_time = datetime.datetime.now().strftime("%m_%d_%Y__%H_%M_%S")
        log_filename = "log_{}_{}_{}.json".format(strategy.get('name'), pair, current_time)

        summary['log_file'] = log_filename
        new_logpath = os.path.join(log_path, log_filename)

        with open(new_logpath, 'w+') as log_file:
            log_file.write(json.dumps(log,indent=3))

        summary_filename = "summary_{}_{}_{}.json".format(strategy.get('name'), pair, current_time)

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

        run_pair_sim(csv_path, strategy, pair, log_path, remove_csv)

if __name__ == "__main__":
    # csv_path = 'BTCUSDT_sample.csv'
    # csv_base = "/Users/jedmeier/Projects/fast_trade/fast_trade"
    csv_base = "/home/jedmeier/crypto-data/crypto_data/2017_standard"
    log_path = "/home/jedmeier/fast_trade/fast_trade/logs"
    # log_path = None
    # pairs = ["BTCPAX"]
    with open("../2017_all.json") as all_pairs_file:
        pairs = json.load(all_pairs_file)
    
    
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
