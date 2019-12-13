from build_data_frame import build_data_frame
import os
import datetime
import re
import json



def run_pair_sim(csv_path, strategy, pair, log_path):
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
        # log_obj = ['date','enter','price']
        log_obj = []
        if enter:
            log_obj = [frame[1]['date'],'enter',last_price]
        if exit_position:
            log_obj = [frame[1]['date'],'exit',last_price]
        # if not enter and not exit_position:
            # log_obj = [frame[1]['date'],'hold',last_price]
        
        if log_path and log_obj:
            log.append(log_obj)
    
    stop = datetime.datetime.now()
    
    total_time = stop - start
    # return data_frame, log
    # re.replace()
    # re.sub(r'(?is)</html>.+', '</html>', article)
    log_filename = "{}_{}_{}.json".format(strategy.get('name'), pair, datetime.datetime.now())
    log_filename = re.sub(r'(\s)|(:)|(-)',"_",log_filename)
    # print(log_filename)
    new_logpath = os.path.join(log_path, log_filename)
    print("total time: ", total_time)
    # return new_logpath
    with open(new_logpath, 'w+') as log_file:
        log_file.write(json.dumps(log,indent=3))



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
    for pair in pairs:
        # csv_path = os.path.abspath(csv_base.format(pair))
        csv_filename = "{}.csv".format(pair)
        csv_path = os.path.join(csv_base, csv_filename)
        run_pair_sim(csv_path, strategy, pair, log_path)

if __name__ == "__main__":
    # csv_path = 'BTCUSDT_sample.csv'
    csv_base = "/Users/jedmeier/Projects/crypto-data/crypto_data/2017_standard"
    log_path = "/Users/jedmeier/Projects/fast_trade/fast_trade/logs"
    pairs = ["ADABNB","XMRBTC"]
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