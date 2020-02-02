import pandas as pd
from indicator_map import indicator_map


def build_data_frame(csv_path, indicators=[]):
    csv = pd.read_csv(csv_path, parse_dates=False)
    df = csv.copy()  # not sure if this is needed

    for ind in indicators:
        timeperiod = determine_timeperiod(str(ind.get("timeperiod")))
        ind_name = ind.get("name")
        field_name = ind.get("ref")
        df[field_name] = indicator_map[ind_name](csv, timeperiod)

    # drop all rows where the close is 0
    df = df[df.close != 0]
    return df


def determine_timeperiod(timeperiod_str):
    if "m" in timeperiod_str:
        return int(timeperiod_str.replace("m", ""))

    if "h" in timeperiod_str:
        clean = timeperiod_str.replace("h", "")
        return int(clean) * 60

    if "d" in timeperiod_str:
        clean = timeperiod_str.replace("d", "")
        return int(clean) * 1440

    return int(timeperiod_str)
