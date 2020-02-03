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


def run_single_backtest(csv_path, strategy, starting_aux_bal):
    """
    Params:
        csv_path: where to find the csv file of the ohlcv data
        strategy: object containing the logic of this given strategy
        starting_aux_balance: how much of the aux coin to start with

    Returns:
        summary of the performace of backtest and dataframe
    """
    if not os.path.isfile(csv_path):
        print("{} does not exist.".format(csv_path))
        return

    start = datetime.datetime.utcnow()
    df = build_data_frame(csv_path, strategy.get("indicators"))

    df["actions"] = [
        determine_action(frame, strategy, list(df.columns)) for frame in df.values
    ]

    stop = datetime.datetime.utcnow()
    base, aux = analyze_df(df, starting_aux_bal)
    df["base_balance"] = base
    df["aux_balance"] = aux

    return {
        "start": start.strftime("%m/%d/%Y %H:%M:%S"),
        "stop": stop.strftime("%m/%d/%Y %H:%M:%S"),
        "total_time": str(stop - start),
        "starting_base": 0,
        "ending_base": df.iloc[-1]["base_balance"],
        "starting_aux": starting_aux_bal,
        "ending_aux": df.iloc[-1]["aux_balance"],
        "aux_max": df["aux_balance"].max(),
        "base_max": df["base_balance"].max(),
        "strategy": strategy,
        "df": df,
    }


if __name__ == "__main__":
    load_dotenv()
    csv_path = f"{os.getenv('CSV_PATH')}BTCUSDT.csv"

    with open("./example_strat.json", "r") as strat_file:
        strategy = json.load(strat_file)

    starting_aux_bal = 15000

    res = run_single_backtest(csv_path, strategy, starting_aux_bal)

    print(res)
