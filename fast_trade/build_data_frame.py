import pandas as pd
from indicator_map import indicator_map
import os

def build_data_frame(csv_path, indicators=[]):
    if not os.path.isfile(csv_path):
        raise Exception(f"File doesn't exist: {csv_path}")
    
    csv = pd.read_csv(csv_path, parse_dates=False)
    df = csv.copy()  # not sure if this is needed
    for ind in indicators:
        timeperiod = determine_timeperiod(str(ind.get("timeperiod")))
        func = ind.get("func")
        field_name = ind.get("name")
        df[field_name] = indicator_map[func](csv, timeperiod)

    # drop all rows where the close is 0
    df = df[df.close != 0]
    return df


def determine_timeperiod(timeperiod_str):
    if "m" in timeperiod_str:
        return int(timeperiod_str.replace("m", ""))

    if "h" in timeperiod_str:
        clean_timeperiod = timeperiod_str.replace("h", "")
        return int(clean_timeperiod) * 60

    if "d" in timeperiod_str:
        clean_timeperiod = timeperiod_str.replace("d", "")
        return int(clean_timeperiod) * 1440

    return int(timeperiod_str)
