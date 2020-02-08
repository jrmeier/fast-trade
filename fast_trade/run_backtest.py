import datetime
from .build_data_frame import build_data_frame
from .run_analysis import analyze_df


def determine_action(frame, strategy, df_col_map):
    """
    Params:
        frame: current row of the dataframe
        strategy: object with the logic of how to trade
        df_col_map: dictionary with the column name and index
        of the dataframe
    Returns:
        string, "e" (enter), "x" (exit), "h" (hold) of what
        the strategy would do
    """
    if take_action(frame, strategy["enter"], df_col_map):
        return "e"

    if take_action(frame, strategy["exit"], df_col_map):
        return "x"

    return "h"


def take_action(row, strategy, columns):
    """
    Params:
        row: data row to operate on
        strategy: dictionary of logic and how to impliment it
        columns: list of data points describing the row
    Returns:
        boolean, True if row meets the criteria of given strategy,
        False if otherwise
    """
    results = []

    df_col_map = {}
    for idx, each in enumerate(columns):
        df_col_map[each] = row[idx]

    for each in strategy:
        if each[1] == ">":
            results.append(bool(df_col_map[each[0]] > df_col_map[each[2]]))
        if each[1] == "<":
            results.append(bool(df_col_map[each[0]] < df_col_map[each[2]]))
        if each[1] == "=":
            results.append(bool(df_col_map[each[0]] == df_col_map[each[2]]))

    if len(results):
        return all(results)

    return False


def run_backtest(csv_path, strategy, starting_aux_bal=1000):
    """
    Params:
        csv_path: required, where to find the csv file of the ohlcv data
        strategy: required, object containing the logic to test
        starting_aux_balance: optional, default 1000 how much of the aux coin to
        the backtest
    Returns:
        tuple
            object 1 is a dict summary of the performace of backtest
            object 2 is a pandas dataframe object used in the backtest
    """

    start = datetime.datetime.utcnow()
    df = build_data_frame(csv_path, strategy.get("indicators"))

    df["actions"] = [
        determine_action(frame, strategy, list(df.columns)) for frame in df.values
    ]

    base, aux = analyze_df(df, starting_aux_bal)

    df["base_balance"] = base
    df["aux_balance"] = aux

    aux_sum = {
        "start_balance": starting_aux_bal,
        "end_balance": round(df.iloc[-1]["aux_balance"], 8),
        "max": round(df["aux_balance"].max(), 8),
        "mean": round(df["aux_balance"].mean(), 8),
        "median": round(df["aux_balance"].median(), 8),
    }

    base_sum = {
        "start_balance": 0,
        "end_balance": round(df.iloc[-1]["base_balance"], 8),
        "max": round(df["base_balance"].max(), 8),
        "mean": round(df["base_balance"].mean(), 8),
        "median": round(df["base_balance"].median(), 8),
    }

    max_gain_perc = round((1 - (starting_aux_bal / df["aux_balance"].max())) * 100, 3)

    stop = datetime.datetime.utcnow()

    return (
        {
            "start": start.strftime("%m/%d/%Y %H:%M:%S"),
            "stop": stop.strftime("%m/%d/%Y %H:%M:%S"),
            "total_time": str(stop - start),
            "max_gain_perc": max_gain_perc,
            "strategy": strategy,
            "base_sum": base_sum,
            "aux_sum": aux_sum,
        },
        df,
    )
