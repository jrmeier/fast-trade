from build_data_frame import build_data_frame

def run(csv_path, interval, indicators, strategy, should_log=True):
    # take in the dataframe
    # take in the strategy
    # read each frame
    data_frame = build_data_frame(csv_path, indicators, interval)
    log = []
    
    for frame in data_frame.iterrows():
        last_price = frame[1]['close']
        enter = take_action(frame[1], strategy['enter'])
        exit_position = take_action(frame[1], strategy['exit'])
        # log_obj = ['date','enter','price']
        if enter:
            log_obj = [frame[1]['date'],'enter',last_price]
        if exit_position:
            log_obj = [frame[1]['date'],'exit',last_price]
        if not enter and not exit_position:
            log_obj = {'action': 'hold', 'price': last_price, 'current': frame[0]}
            log_obj = [frame[1]['date'],'hold',last_price]
        if should_log:
            log.append(log_obj)


    return data_frame, log



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


if __name__ == "__main__":
    csv_path = 'BTCUSDT_sample.csv'
    interval = 5 # in minutes
    indicators = [ # must be a list, must look like below
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

    strategy = {
        "enter": [
            ('short','>','mid'), # ref to compare, operator, other ref to compare
            ('short', '>', 'long')
            ],
        "exit": [('short','<', 'mid')]
    }

    df,log = run(csv_path, interval, indicators, strategy)


    print(log)