import datetime
import pandas as pd

from .build_data_frame import build_data_frame
from .run_analysis import analyze_df
from .build_summary import build_summary


def take_action(row, strategy, columns):
    """
    Params:
        row: data row to operate on
        strategy: dictionary of logic and how to impliment it
        columns: list of data points describing th row
    Returns:
        boolean, True if row meets the criteria of given strategy,
        False if otherwise
    """
    results = []

    df_col_map = dict(zip(columns, row))
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

    return all(results)


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

    action = "h"

    if take_action(frame, strategy["enter"], df_col_map):
        action = "e"

    if take_action(frame, strategy["exit"], df_col_map):
        action = "x"

    return action


def run_backtest(strategy, ohlcv_path="", df=None):
    """
    Params:
        strategy: dict, required, object containing the logic to test
        ohlcv_path: string or list, required, where to find the csv file of the ohlcv data
        df
    Returns: dictionary
            summary is a dict summary of the performace of backtest
            df is a pandas dataframe object used in the backtest
    """

    start = datetime.datetime.utcnow()

    if not df:
        df = build_data_frame(strategy, ohlcv_path)

    flagged_enter, flagged_exit, strategy = get_flagged_logiz(strategy)

    strategy["base_balance"] = strategy.get("base_balance", 1000)
    strategy["exit_on_end"] = strategy.get("exit_on_end", True)

    df = process_dataframe(df, strategy)

    if flagged_enter or flagged_exit:
        strategy["enter"].extend(flagged_enter)
        strategy["exit"].extend(flagged_exit)

        df = process_dataframe(df, strategy)

    summary = build_summary(df, start)

    return {"summary": summary, "df": df}


def get_flagged_logiz(strategy):
    """
    removes logiz that need to be processed after the initial run
    """
    to_flag = ["aux_perc_change"]
    flagged_exit_idx = []
    flagged_enter_idx = []

    flagged_enter = []
    flagged_exit = []

    for idx, ex in enumerate(strategy["exit"]):
        if ex[0] in to_flag or ex[2] in to_flag:
            flagged_exit_idx.append(idx)

    for e_ex in flagged_exit_idx:
        flagged_exit.append(strategy["exit"].pop(e_ex))

    for idx, en in enumerate(strategy["enter"]):
        if en[0] in to_flag or en[2] in to_flag:
            flagged_enter_idx.append(idx)

    for e_en in flagged_enter:
        flagged_enter.append(strategy["enter"].pop(e_en))

    return flagged_enter, flagged_exit, strategy


def process_dataframe(df, strategy):
    """
    Processes the frame and adds the resultant rows
    """
    df["actions"] = [
        determine_action(frame, strategy, list(df.columns)) for frame in df.values
    ]
    base, aux, smooth_base = analyze_df(df, strategy)

    if len(base) != len(df.index):
        new_row = pd.DataFrame(
            df[-1:].values,
            index=[df.index[-1] + pd.Timedelta(minutes=1)],
            columns=df.columns,
        )
        df = df.append(new_row)

    df["base_balance"] = base
    df["aux_balance"] = aux
    df["smooth_base"] = smooth_base

    df["aux_perc_change"] = df["smooth_base"].pct_change() * 100
    df["aux_change"] = df["smooth_base"].diff()

    return df
