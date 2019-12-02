from build_data_frame import build_data_frame

def run(data_frame, strategy):
    # take in the dataframe
    # take in the strategy
    # read each frame
    results = []
    for frame in data_frame.iterrows():
        # print(frame[''])
        enter = take_action(frame[1], strategy['enter'])
        exit_position = take_action(frame[1], strategy['exit'])
        if enter:
            print("should enter")
        if exit_position:
            print("should exit")
         


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
    path = "BTCUSDT.csv"
    interval = 15 # 
    indicators = [
        {
            'ref':'short', # reference for strategy
            'name': 'ta.ma', # indicator name
            'timeperiod': 4, # timeperiod to use
            'df':'last_price' # data frame column name
        },
        {   'ref':'mid',
            'name': 'ta.ma',
            'timeperiod': 10,
            'df':'last_price'
        },
        {   'ref':'long',
            'name': 'ta.ma',
            'timeperiod': 20,
            'df':'last_price'
        },
    ]

    data_frame = build_data_frame(path, indicators, interval)

    strategy = {
        "enter": [('short','>','mid')],
        "exit": [('short','<', 'mid')]
    }

    res = run(data_frame, strategy)

    print(res)