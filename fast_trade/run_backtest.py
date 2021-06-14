import datetime
import pandas as pd
import re
import itertools

from .build_data_frame import build_data_frame
from .run_analysis import apply_logic_to_df
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

    performance_start_time = datetime.datetime.utcnow()
    new_backtest = prepare_new_backtest(backtest)
    if ohlcv_path:
        df = build_data_frame(new_backtest, ohlcv_path)

    df = apply_backtest_to_df(df, new_backtest)

    if summary:
        summary, trade_log = build_summary(df, performance_start_time)
    else:
        performance_stop_time = datetime.datetime.utcnow()
        summary = {
            "test_duration": (
                performance_stop_time - performance_start_time
            ).total_seconds()
        }
        trade_log = None

    return {
        "summary": summary,
        "df": df,
        "trade_df": trade_log,
        "backtest": new_backtest,
    }


def prepare_new_backtest(backtest):
    """
    Parameters
    ----------
        backtest, a raw backest object

    Returns
    -------
        backtest, a backtest dictionary normalized with defaults

    """
    new_backtest = backtest.copy()
    new_backtest["base_balance"] = backtest.get("base_balance", 1000)
    new_backtest["exit_on_end"] = backtest.get("exit_on_end", False)
    new_backtest["comission"] = backtest.get("comission", 0)
    new_backtest["trailing_stop_loss"] = backtest.get("trailing_stop_loss", 0)
    new_backtest["any_enter"] = backtest.get("any_enter", [])
    new_backtest["any_exit"] = backtest.get("any_exit", [])
    new_backtest["lot_size_perc"] = float(backtest.get("lot_size", 1))
    new_backtest["max_lot_size"] = int(backtest.get("max_lot_size", 0))

    return new_backtest


def apply_backtest_to_df(df: pd.DataFrame, backtest: dict):
    """Processes the frame and adds the resultent rows
    Parameters
    ----------
        df, dataframe with all the calculated datapoints
        backtest, backtest object

    Returns
    -------
        df, dataframe with with all the actions and backtest processed
    """

    df = process_logic_and_generate_actions(df, backtest)

    df = apply_logic_to_df(df, backtest)

    df["adj_account_value_change_perc"] = df["adj_account_value"].pct_change()
    df["adj_account_value_change"] = df["adj_account_value"].diff()

    return df


def process_logic_and_generate_actions(df: pd.DataFrame, backtest: object):
    """
    Parameters
    ----------
        df, dataframe with the datapoints (indicators) calculated
        backtest, backtest object

    Returns
    -------
        df, a modified dataframe with the "actions" added

    Explainer
    ---------
    In this function, like the name suggests, we process the logic and generate the actions.

    """

    """we need to search though all the logics and find the highest confirmation number
    so we know how many frames to pass in
    """
    logics = [
        backtest["enter"],
        backtest["exit"],
        backtest["any_exit"],
        backtest["any_enter"],
    ]

    logics = list(itertools.chain(*logics))
    max_last_frames = 0  # the we need to keep the
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
            wtf = determine_action(frame, backtest, last_frames)
            actions.append(wtf)
        df["action"] = actions
    else:
        df["action"] = [determine_action(frame, backtest) for frame in df.itertuples()]

    return df


def determine_action(frame: pd.DataFrame, backtest: dict, last_frames=[]):
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

    if take_action(frame, backtest["exit"], last_frames):
        return "x"

    if take_action(frame, backtest["any_exit"], last_frames, require_any=True):
        return "ax"

    if take_action(frame, backtest["enter"], last_frames):
        return "e"

    if take_action(frame, backtest["any_enter"], last_frames, require_any=True):
        return "ae"

    return "h"


def take_action(current_frame, logics, last_frames=[], require_any=False):
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
        for logic in logics:
            if len(logic) > 3:
                frames = logic[3]
                lcl_frames = last_frames[:frames]
                lcl_results = []

                if len(lcl_frames) < frames:
                    res = False
                else:
                    for lcl_frame in lcl_frames:
                        lcl_res = process_single_frame(
                            [logic], lcl_frame, require_any=False
                        )
                        lcl_results.append(lcl_res)
                    res = all(lcl_results)
                results.append(res)
            else:
                res = process_single_frame([logic], current_frame, require_any)
                results.append(res)
    else:
        res = process_single_frame(logics, current_frame, require_any)
        results.append(res)

    ret_value = False
    if len(results):
        if require_any:
            ret_value = any(results)
        else:
            ret_value = all(results)
    return ret_value


def process_single_frame(logics, row, require_any):
    results = []

    return_value = False
    for logic in logics:
        res = process_single_logic(logic, row)
        # print("row: ", row)
        results.append(res)

    if len(results):
        if require_any:
            return_value = any(results)
        else:
            return_value = all(results)

    return return_value


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


def clean_field_type(field, row=None):
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
    if row:
        if not isinstance(row, dict):
            row = row._asdict()

    if isinstance(field, str):
        if field.isnumeric():
            return int(field)
        if re.match(r"^-?\d+(?:\.\d+)$", field):  # if its a string in a float
            return float(field)

    if type(field) is bool:
        return field

    if isinstance(field, int) or isinstance(field, float):

        return field

    if row:
        return row[field]

    return row
