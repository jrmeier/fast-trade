import datetime
from os import fwalk
import pandas as pd

from .build_data_frame import build_data_frame
from .run_analysis import analyze_df
from .build_summary import build_summary


def run_backtest(
    strategy: dict, ohlcv_path: str = "", df: pd.DataFrame = None, summary=True
):
    """
    Parameters
        strategy: dict, required, object containing the logic to test and other details
        ohlcv_path: string or list, required, where to find the csv file of the ohlcv data
        df: pandas dataframe indexed by date
    Returns
        dict
            summary dict, summary of the performace of backtest
            df dataframe, object used in the backtest
            trade_log, dataframe of all the rows where transactions happened
    """

    perf_start_time = datetime.datetime.utcnow()

    if ohlcv_path:
        df = build_data_frame(strategy, ohlcv_path)
    flagged_enter, flagged_exit = get_flagged_logiz(strategy)

    new_strategy = strategy.copy()
    new_strategy["base_balance"] = strategy.get("base_balance", 1000)
    new_strategy["exit_on_end"] = strategy.get("exit_on_end", True)
    new_strategy["commission"] = strategy.get("commission", 0)
    new_strategy["hard_exit"] = strategy.get("hard_exit", [])

    df = apply_strategy_to_dataframe(df, new_strategy)

    if flagged_enter or flagged_exit:
        new_strategy["enter"].extend(flagged_enter)
        new_strategy["exit"].extend(flagged_exit)

        df = apply_strategy_to_dataframe(df, new_strategy)

    if summary:
        summary, trade_log = build_summary(df, perf_start_time, new_strategy)
    else:
        perf_stop_time = datetime.datetime.utcnow()
        summary = {"test_duration": (perf_stop_time - perf_start_time).total_seconds()}
        trade_log = None

    return {
        "summary": summary,
        "df": df,
        "trade_df": trade_log,
        "strategy": new_strategy,
    }


def get_flagged_logiz(strategy: dict):
    """removes logiz that need to be processed after the initial run

    Parameters
    ----------
        strategy, dictionary of instructions

    Returns
    -------
     tuple, flagged_enter, flagged_exit list of what to reprocess after the first process
        strategy, dict, modified strategy object
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

    return flagged_enter, flagged_exit


def flatten_to_logics(list_of_logics):
    if len(list_of_logics) == 1:
        return list_of_logics
    if isinstance(list_of_logics[0], list):
        return flatten_to_logics(list_of_logics[0]) + flatten_to_logics(list_of_logics[1:])
    return list_of_logics[:1] + flatten_to_logics(list_of_logics[1:])


def apply_strategy_to_dataframe(df: pd.DataFrame, strategy: dict):
    """Processes the frame and adds the resultent rows
    Parameters
    ----------
        df, dataframe with all the calculated indicators
        strategy, strategy object

    Returns
    -------
        df, dataframe with with all the actions and strategy processed
    """
    # df["action"] = [determine_action(frame, strategy) for frame in df.itertuples()]

    # get the max length to pass in
    logics = [
        strategy['enter'],
        strategy['exit'],
        strategy['hard_exit'],
    ]

    logics = flatten_to_logics(logics)

    max_last_frames = 0

    for logic in logics:
        if len(logic) > 3:
            if logic[3] > max_last_frames:
                max_last_frames = logic[3]

    if max_last_frames:
        actions = []
        last_frames = []
        for frame in df.itertuples():
            actions.append(determine_action(frame, strategy, max_last_frames, last_frames))
        df["action"] = actions
    else:
        df["action"] = [determine_action(frame, strategy) for frame in df.itertuples()]

    df = analyze_df(df, strategy)

    df["aux_perc_change"] = df["total_value"].pct_change() * 100
    df["aux_change"] = df["total_value"].diff()

    return df


def determine_action(frame: pd.DataFrame, strategy: dict, max_last_frames=0, last_frames=[]):
    """processes the actions with the applied logic
    Parameters
    ----------
        frame: current row of the dataframe
        strategy: object with the logic of how to trade
        df_col_map: dictionary with the column name and index
        of the dataframe

    Returns
    -------
        string, "e" (enter), "x" (exit), "h" (hold) of what
        the strategy would do
    """

    if take_action(frame, strategy['hard_exit'], max_last_frames, last_frames, require_any=True):
        return 'x'

    if take_action(frame, strategy["enter"], max_last_frames, last_frames):
        return "e"

    if take_action(frame, strategy["exit"], max_last_frames, last_frames):
        return "x"

    return "h"


def take_action(current_frame, logics, max_last_frames, last_frames, require_any=False):
    """determines whether to take action based on the logic in the strategy
    Parameters
    ----------
        row: data row to operate on
        strategy: dictionary of logic and how to impliment it

    Returns
    -------
        boolean, True if row meets the criteria of given strategy,
        False if otherwise
    """

    results = []

    last_frames.insert(0, current_frame)

    if len(last_frames) > max_last_frames:
        last_frames.pop()

    for last_frame in last_frames:
        res = process_single_frame(logics, last_frame, require_any)
        results.append(res)

    return all(results)


def process_single_frame(logics, row, require_any):
    results = []
    if not isinstance(row, dict):
        row = row._asdict()

    return_value = False
    for logic in logics:
        res = process_single_logic(logic, row, require_any)
        results.append(res)

    if len(results):
        if require_any:
            return_value = any(results)
        else:
            return_value = all(results)

    return return_value


def clean_field_type(field, row):
    if isinstance(field, str):
        if field.isnumeric():
            return int(field)

    return row[field]


def process_single_logic(logic, row, require_any):
    val0 = clean_field_type(logic[0], row=row)
    val1 = clean_field_type(logic[2], row=row)

    results = []

    if logic[1] == ">":
        results.append(bool(val0 > val1))
    if logic[1] == "<":
        results.append(bool(val0 < val1))
    if logic[1] == "=":
        results.append(bool(val0 == val1))
    if logic[1] == "!=":
        results.append(bool(val0 != val1))

    if require_any:
        return any(results)

    return all(results)
