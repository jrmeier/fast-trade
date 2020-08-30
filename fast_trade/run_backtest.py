import datetime
import pandas as pd

from .build_data_frame import build_data_frame
from .run_analysis import analyze_df
from .build_summary import build_summary


def take_action(row, strategy):
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
    for each in strategy:
        val0 = each[0] if isinstance(each[0], int) or isinstance(each[0], float) else row[each[0]]
        val1 = each[2] if isinstance(each[2], int) or isinstance(each[2], float) else row[each[2]]

        # print("val0: ",val0)
        if isinstance(val0, pd.Series):
            val0 = row[each[0]].values[0]
        
        if isinstance(val1, pd.Series):
            val1 = row[each[2]].values[0]

        if each[1] == ">":
            results.append(bool(val0 > val1))
        if each[1] == "<":
            results.append(bool(val0 < val1))
        if each[1] == "=":
            results.append(bool(val0 == val1))
        if each[1] == "!=":
            results.append(bool(val0 != val1))

    return all(results)


def determine_action(frame, strategy):
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

    if take_action(frame, strategy["enter"]):
        action = "e"

    if take_action(frame, strategy["exit"]):
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

    if ohlcv_path:
        df = build_data_frame(strategy, ohlcv_path)

    flagged_enter, flagged_exit, strategy = get_flagged_logiz(strategy)

    strategy["base_balance"] = strategy.get("base_balance", 1000)
    strategy["exit_on_end"] = strategy.get("exit_on_end", True)
    strategy["commission"] = strategy.get("commission", 0)

    df = process_dataframe(df, strategy)


    if flagged_enter or flagged_exit:
        strategy["enter"].extend(flagged_enter)
        strategy["exit"].extend(flagged_exit)

        df = process_dataframe(df, strategy)


    summary, trade_log = build_summary(df, start, strategy)

    return {"summary": summary, "df": df, "trade_log": trade_log}


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
    # for idx, row in df.iterrows():
    df["action"] = [
        determine_action(frame, strategy) for idx, frame in df.iterrows()
    ]

    df = analyze_df(df, strategy)

    df["aux_perc_change"] = df["total_value"].pct_change() * 100
    df["aux_change"] = df["total_value"].diff()

    return df
