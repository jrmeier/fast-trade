import datetime
import pandas as pd
import re

from .build_data_frame import build_data_frame
from .run_analysis import analyze_df
from .build_summary import build_summary


def run_backtest(
    backtest: dict, ohlcv_path: str = "", df: pd.DataFrame = None, summary=True
):
    """
    Parameters
        backtest: dict, required, object containing the logic to test and other details
        ohlcv_path: string or list, required, where to find the csv file of the ohlcv data
        df: pandas dataframe indexed by date
    Returns
        dict
            summary dict, summary of the performace of backtest
            df dataframe, object used in the backtest
            trade_log, dataframe of all the rows where transactions happened
    """

    perf_start_time = datetime.datetime.utcnow()
    new_backtest = prepare_new_backtest(backtest)
    if ohlcv_path:
        df = build_data_frame(backtest, ohlcv_path)

    df = apply_backtest_to_dataframe(df, new_backtest)

    if summary:
        summary, trade_log = build_summary(df, perf_start_time, new_backtest)
    else:
        perf_stop_time = datetime.datetime.utcnow()
        summary = {"test_duration": (perf_stop_time - perf_start_time).total_seconds()}
        trade_log = None

    return {
        "summary": summary,
        "col": df,
        "trade_df": trade_log,
        "backtest": new_backtest,
    }


def prepare_new_backtest(backtest):
    new_backtest = backtest.copy()
    new_backtest["base_balance"] = backtest.get("base_balance", 1000)
    new_backtest["exit_on_end"] = backtest.get("exit_on_end", False)
    new_backtest["comission"] = backtest.get("comission", 0)
    new_backtest["trailing_stop_loss"] = backtest.get("trailing_stop_loss", 0)
    new_backtest["any_enter"] = backtest.get("any_enter", [])
    new_backtest["any_exit"] = backtest.get("any_exit", [])

    return new_backtest


def flatten_to_logics(list_of_logics):
    if len(list_of_logics) < 2:
        return list_of_logics
    if isinstance(list_of_logics[0], list):
        return flatten_to_logics(list_of_logics[0]) + flatten_to_logics(
            list_of_logics[1:]
        )

    return list_of_logics[:1] + flatten_to_logics(list_of_logics[1:])


def apply_backtest_to_dataframe(df: pd.DataFrame, backtest: dict):
    """Processes the frame and adds the resultent rows
    Parameters
    ----------
        df, dataframe with all the calculated datapoints
        backtest, backtest object

    Returns
    -------
        df, dataframe with with all the actions and backtest processed
    """

    df = process_logic_and_actions(df, backtest)

    df = analyze_df(df, backtest)

    df["aux_perc_change"] = df["total_value"].pct_change() * 100
    df["aux_change"] = df["total_value"].diff()

    return df


def process_logic_and_actions(df, backtest):
    logics = [
        backtest["enter"],
        backtest["exit"],
        backtest["any_exit"],
        backtest["any_enter"],
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
            last_frames.insert(0, frame)
            if len(last_frames) >= max_last_frames + 1:
                last_frames.pop()

            actions.append(
                determine_action(frame, backtest, max_last_frames, last_frames)
            )
        df["action"] = actions
    else:
        df["action"] = [determine_action(frame, backtest) for frame in df.itertuples()]

    return df


def determine_action(
    frame: pd.DataFrame, backtest: dict, max_last_frames=0, last_frames=[]
):
    """processes the actions with the applied logic
    Parameters
    ----------
        frame: current row of the dataframe
        backtest: object with the logic of how to trade

    Returns
    -------
        string, "e" (enter), "x" (exit), "h" (hold) of what
        the backtest would do
    """

    trailing_stop_loss = backtest.get("trailing_stop_loss")

    if trailing_stop_loss:
        if frame.close <= frame.trailing_stop_loss:
            return "tsl"

    if take_action(frame, backtest["exit"], max_last_frames, last_frames):
        return "x"

    if take_action(
        frame, backtest["any_exit"], max_last_frames, last_frames, require_any=True
    ):
        return "ax"

    if take_action(frame, backtest["enter"], max_last_frames, last_frames):
        return "e"

    if take_action(
        frame, backtest["any_enter"], max_last_frames, last_frames, require_any=True
    ):
        return "ae"

    return "h"


def take_action(
    current_frame, logics, max_last_frames, last_frames=[], require_any=False
):
    """determines whether to take action based on the logic in the backtest
    Parameters
    ----------
        row: data row to operate on
        backtest: dictionary of logic and how to impliment it

    Returns
    -------
        boolean, True if row meets the criteria of given backtest,
        False if otherwise
    """

    results = []

    if len(last_frames):
        for last_frame in last_frames:
            res = process_single_frame(logics, last_frame, require_any)
            results.append(res)

    else:
        res = process_single_frame(logics, current_frame, require_any)
        results.append(res)

    return all(results)


def process_single_frame(logics, row, require_any):
    results = []

    return_value = False
    for logic in logics:
        res = process_single_logic(logic, row)
        results.append(res)

    if len(results):
        if require_any:
            return_value = any(results)
        else:
            return_value = all(results)

    return return_value


def clean_field_type(field, row):
    """Determines the value of what to run the logic against.
        This might be a calculated value from the current row,
        or a supplied value, such as a number.

    Parameters
    ----------
        field - str, int, or float, logic field to check
        row - dict, dictionary of values of the current frame

    Returns
    -------
        str or int

    """
    if not isinstance(row, dict):
        row = row._asdict()

    if isinstance(field, str):
        if field.isnumeric():
            return int(field)
        if re.match(r"^-?\d+(?:\.\d+)$", field):  # if its a string in a float
            return float(field)
    elif isinstance(field, int) or isinstance(field, float):
        return field

    return row[field]


def process_single_logic(logic, row):
    val0 = clean_field_type(logic[0], row=row)
    val1 = clean_field_type(logic[2], row=row)

    if logic[1] == ">":
        return_value = bool(val0 > val1)
    if logic[1] == "<":
        return_value = bool(val0 < val1)
    if logic[1] == "=":
        return_value = bool(val0 == val1)
    if logic[1] == "!=":
        return_value = bool(val0 != val1)

    return return_value
