import pandas as pd
from indicator_map import indicator_map
def build_data_frame(csv_path, indicators=[]):
    csv = pd.read_csv(csv_path, parse_dates=False)
    df = csv.copy() # not sure if this is needed
    
    for ind in indicators:
        timeperiod = ind.get('timeperiod')
        ind_name = ind.get('name')
        field_name = ind.get('ref')
        df[field_name] = indicator_map[ind_name](csv, timeperiod)

    return df