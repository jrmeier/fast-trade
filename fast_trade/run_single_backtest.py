import os
import datetime
import json
from dotenv import load_dotenv

from build_data_frame import build_data_frame
from run_analysis import analyze_df


def determine_action(frame, strategy, df_col_map):
    """
    Params:
        frame: current row of the dataframe
        strategy: object with the logic of how to trade
        df_col_map: dictionary with the column name and index of the dataframe
    
    Returns: 
        string, "e" (enter), "x" (exit), "h" (hold) of what the strategy would do
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
        boolean, True if row meets the criteria of given strategy, False if otherwise
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


def run_single_backtest(csv_path, strategy, starting_aux_bal=0):
    """
    Params:
        csv_path: required, where to find the csv file of the ohlcv data
        strategy: require, object containing the logic of this given strategy
        starting_aux_balance: optional, how much of the aux coin to start the backtest with

    Returns:
        summary of the performace of backtest and dataframe
    """
    # if not os.path.isfile(csv_path):
    #     print(f"{csv_path} is not a file")
    #     return
    
    start = datetime.datetime.utcnow()
    df = build_data_frame(csv_path, strategy.get("indicators"))

    df["actions"] = [
        determine_action(frame, strategy, list(df.columns)) for frame in df.values
    ]

    stop = datetime.datetime.utcnow()
    if starting_aux_bal:
        # if there's not a starting balance
        base, aux = analyze_df(df, starting_aux_bal)
        df["base_balance"] = base
        df["aux_balance"] = aux

        ending_base = (df.iloc[-1]["base_balance"],)
        ending_aux = df.iloc[-1]["aux_balance"]
        aux_max = round(df["aux_balance"].max(), 8)
        base_max = round(df["base_balance"].max(), 8)
        ending_aux = df.iloc[-1]["aux_balance"]
        ending_base = df.iloc[-1]["base_balance"]

        max_gain_perc = round(
            (1 - (starting_aux_bal / df["aux_balance"].max())) * 100, 3
        )
    else:
        df["base_balance"] = 0
        df["aux_balance"] = 0
        aux_max = 0
        base_max = 0
        max_gain_perc = 0
        ending_aux = 0
        ending_base = 0

    return {
        "start": start.strftime("%m/%d/%Y %H:%M:%S"),
        "stop": stop.strftime("%m/%d/%Y %H:%M:%S"),
        "total_time": str(stop - start),
        "starting_base": 0,
        "ending_base": ending_base,
        "starting_aux": starting_aux_bal,
        "ending_aux": ending_aux,
        "aux_max": aux_max,
        "base_max": base_max,
        "strategy": strategy,
        "max_gain_perc": max_gain_perc,
        # "df": df,
    }


if __name__ == "__main__":
    load_dotenv()
    csv_path = f"{os.getenv('CSV_PATH')}BTCUSDT.csv"

    with open("./example_strat.json", "r") as strat_file:
        strategy = json.load(strat_file)

    # starting_aux_bal = 15000

    res = run_single_backtest(csv_path, strategy)

    print(res)
