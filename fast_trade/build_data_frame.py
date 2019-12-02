import pandas as pd
import talib as ta

def custom(close, *args, **kwargs):
    return close

indicator_map = {
    'ta.ma': ta.MA,
    'ta.ema': ta.EMA,
    'ta.ht_trendline': ta.HT_TRENDLINE,
    'custom': custom
}

def build_data_frame(csv_path, indicators=[], interval=10):
    # read in the csv file
    df = pd.read_csv(csv_path)
    # make all the calculations
    df = df.iloc[::interval, :]

    for ind in indicators:
        # print("ind: ",ind)
        field_name = ind.get('field_name')
        ind_name = ind.get('name', None)
        timeperiod = ind.get('timeperiod', None)
        field = ind.get('field', None)
        
        df[field_name] = indicator_map[ind_name](df[field], timeperiod)
    return df

if __name__ == "__main__":
    path = "BTCUSDT.csv"
    interval = 15
    indicators = [
        {
            'field_name':'21_ma',
            'name': 'ta.ma',
            'timeperiod': 21,
            'field':'last_price'
        },
        {   'field_name':'44_ma',
            'name': 'ta.ma',
            'timeperiod': 44,
            'field':'last_price'
        },
    ]

    res = build_data_frame(path, indicators, interval)
    print(res)