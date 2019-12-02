import pandas as pd
import talib as ta
from custom_functions import *
indicator_map = {
    'ta.ma': ta.MA,
    'ta.ema': ta.EMA,
    'ta.ht_trendline': ta.HT_TRENDLINE,
    'custom': custom
}

def build_data_frame(csv_path, indicators=[], interval=1):
    # read in the csv file
    df = pd.read_csv(csv_path)
    # make all the calculations
    df = df.iloc[::interval, :]
    for ind in indicators:
        field_name = ind.get('ref')
        ind_name = ind.get('name', None)
        timeperiod = ind.get('timeperiod', None)
        field = ind.get('df', None)
        
        df[field_name] = indicator_map[ind_name](df[field], timeperiod)
    
    return df

if __name__ == "__main__":
    path = "BTCUSDT.csv"
    interval = 15
    indicators = [
        {
            'ref':'short',
            'name': 'ta.ma',
            'timeperiod': 21,
            'df':'last_price'
        },
        {   'ref':'mid',
            'name': 'ta.ma',
            'timeperiod': 44,
            'df':'last_price'
        },
        {   'ref':'long',
            'name': 'ta.ma',
            'timeperiod': 75,
            'df':'last_price'
        },
    ]

    # buy signal 
    data_frame = build_data_frame(path, indicators, interval)
    print(data_frame)