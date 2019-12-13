import pandas as pd
import talib as ta
from custom_functions import *

indicator_map = {
    'ta.ma': ta.MA,
    'ta.ema': ta.EMA,
    'ta.ht_trendline': ta.HT_TRENDLINE,
    'custom': custom
}

def build_data_frame(csv_path, indicators=[]):
    # read in the csv file
    df = pd.read_csv(csv_path)
    # make all the calculations
    for ind in indicators:
        field_name = ind.get('ref')
        ind_name = ind.get('name', None)
        timeperiod = ind.get('timeperiod', None)
        field = ind.get('df', None)
        
        df[field_name] = indicator_map[ind_name](df[field], timeperiod)
    
    return df
