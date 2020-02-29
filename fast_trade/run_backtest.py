import datetime
from .build_data_frame import build_data_frame
from .run_analysis import analyze_df
from .build_summary import build_summary
import pandas as pd


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
        check1 = each[0] if type(each[0]) == int else df_col_map[each[0]]
        check2 = each[2] if type(each[2]) == int else df_col_map[each[2]]

        if each[1] == ">":
            results.append(bool(check1 > check2))
        if each[1] == "<":
            results.append(bool(check1 < check2))
        if each[1] == "=":
            results.append(bool(check1 == check2))
        if each[1] == "!=":
            results.append(bool(check1 != check2))

    if len(results):
        return all(results)

    return False


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


def run_backtest(csv_path, strategy, timerange={}, starting_aux_bal=1000):
    """
    Params:
        csv_path: required, where to find the csv file of the ohlcv data
        strategy: required, object containing the logic to test
        starting_aux_balance: optional, default 1000 how much of the aux coin to
        the backtest
    Returns: tuple
            object 1 is a dict summary of the performace of backtest
            object 2 is a pandas dataframe object used in the backtest
    """

    start = datetime.datetime.utcnow()
    # print("df: ",strategy)
    try:
        df = build_data_frame(csv_path, strategy, timerange)
    except Exception as e:
        print(e)
        return "Data frame creation fail"

    df["actions"] = [
        determine_action(frame, strategy, list(df.columns)) for frame in df.values
    ]

    base, aux, total_trades = analyze_df(df, starting_aux_bal)    

    df["base_balance"] = base
    df["aux_balance"] = aux

    summary = build_summary(df, starting_aux_bal, start)

    return (
        summary,
        df
    )
