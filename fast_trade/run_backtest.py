import datetime
import itertools
import re

import pandas as pd

from fast_trade.archive.db_helpers import get_kline

from .build_data_frame import prepare_df
from .build_summary import build_summary
from .evaluate import evaluate_rules
from .run_analysis import apply_logic_to_df
from .validate_backtest import validate_backtest, validate_backtest_with_df


def extract_error_messages(error_dict: dict) -> str:
    """
    Extract and format error messages from the error dictionary.

    Parameters
    ----------
    error_dict: dict, the dictionary containing error information

    Returns
    -------
    str, formatted error messages
    """
    messages = []

    def traverse_errors(d):
        if isinstance(d, dict):
            for key, value in d.items():
                if key == "msgs" and isinstance(value, list):
                    for msg in value:
                        if isinstance(msg, str):
                            messages.append(msg)
                        elif isinstance(msg, dict):
                            traverse_errors(msg)
                        else:
                            messages.append(str(msg))
                else:
                    traverse_errors(value)
        elif isinstance(d, list):
            for item in d:
                traverse_errors(item)

    traverse_errors(error_dict)

    return "\n".join(messages)


class MissingData(Exception):
    pass


class BacktestKeyError(Exception):
    def __init__(self, error_msgs):
        # Ensure error_msgs is a list of strings
        if isinstance(error_msgs, str):
            error_msgs = [error_msgs]
        self.error_msgs = "\n".join([f"-{msg}" for msg in error_msgs])
        super().__init__(f"Backtest Error(s):\n{self.error_msgs}")


def run_backtest(backtest: dict, df: pd.DataFrame = pd.DataFrame(), summary=True):
    """
    Run a backtest on a given dataframe
    Parameters
        backtest: dict, required, object containing the logic to test and other details
        data_path: string or list, required, where to find the csv file of the ohlcv data
        df: pandas dataframe indexed by date
    Returns
        dict
            summary dict, summary of the performace of backtest
            df dataframe, object used in the backtest
            trade_log, dataframe of all the rows where transactions happened
    """

    performance_start_time = datetime.datetime.utcnow()
    new_backtest = prepare_new_backtest(backtest)
    errors = validate_backtest(new_backtest)

    if errors.get("has_error"):
        # find all the keys with values
        error_keys = [
            key for key, value in errors.items() if value and key != "has_error"
        ]
        error_msgs = extract_error_messages(errors)
        for ek in error_keys:
            if ek not in ["any_enter", "any_exit"]:
                # get the errors from the errors dict
                raise BacktestKeyError(error_msgs)

    if df.empty:
        # check the local archive for the data
        # calculate the start and end dates based on the max number of periods in any dp args
        def get_max_periods(datapoint):
            args = datapoint.get("args", [])
            periods = [int(arg) for arg in args if isinstance(arg, int)]
            if len(periods) == 0:
                return 0
            return max(periods)

        args = [get_max_periods(dp) for dp in new_backtest.get("datapoints", [])]
        max_periods = max(args)
        # print(max_periods)
        # get the frequency of the backtest
        freq = new_backtest.get("freq")
        if not freq and new_backtest.get("chart_period"):
            freq = new_backtest.get("chart_period")
        # convert the frequency to a timedelta
        td_freq = pd.Timedelta(freq)

        start_date = backtest.get("start_date", None)
        if start_date and not isinstance(start_date, datetime.datetime):
            start_date = datetime.datetime.fromisoformat(start_date)
            start_date = start_date - td_freq * max_periods

        # get the data from the local archive
        df = get_kline(
            backtest.get("symbol"),
            backtest.get("exchange"),
            start_date,
            backtest.get("end_date"),
            freq=backtest.get("freq") or backtest.get("chart_period"),
        )

    if df.empty:
        raise MissingData(
            f"No data found for {backtest.get('symbol')} on {backtest.get('exchange')} or in the given dataframe"
        )

    df = prepare_df(df, new_backtest)

    df = apply_backtest_to_df(df, new_backtest)
    # throw an error if the backtest is not valid
    validate_backtest_with_df(new_backtest, df)

    if summary:
        summary, trade_log = build_summary(df, performance_start_time)
    else:
        performance_stop_time = datetime.datetime.utcnow()
        summary = {
            "test_duration": (
                performance_stop_time - performance_start_time
            ).total_seconds()
        }
        trade_log = pd.DataFrame()

    rule_eval = evaluate_rules(summary, new_backtest.get("rules", []))
    summary["rules"] = {
        "all": rule_eval[0],
        "any": rule_eval[1],
        "results": rule_eval[2],
    }
    # add the strategy to the summary
    summary["strategy"] = new_backtest
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
    # new_backtest["any_enter"] = backtest.get("any_enter", [])
    # new_backtest["any_exit"] = backtest.get("any_exit", [])
    new_backtest["lot_size_perc"] = float(backtest.get("lot_size", 1))
    new_backtest["max_lot_size"] = int(backtest.get("max_lot_size", 0))
    new_backtest["rules"] = backtest.get("rules", [])

    # if chart_start and chart_stop are provided, use them
    if backtest.get("chart_start"):
        new_backtest["start"] = backtest.get("chart_start")
        del new_backtest["chart_start"]
        print("Warning: chart_start is deprecated, use start instead.")
    if backtest.get("chart_stop"):
        new_backtest["stop"] = backtest.get("chart_stop")
        del new_backtest["chart_stop"]
        print("Warning: chart_stop is deprecated, use stop instead.")

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

    # set the index to the date
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
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
        backtest.get("enter", []),
        backtest.get("exit", []),
        backtest.get("any_exit", []),
        backtest.get("any_enter", []),
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

    if take_action(frame, backtest.get("exit", []), last_frames):
        return "x"

    if take_action(frame, backtest.get("any_exit", []), last_frames, require_any=True):
        return "ax"

    if take_action(frame, backtest.get("enter", []), last_frames):
        return "e"

    if take_action(frame, backtest.get("any_enter", []), last_frames, require_any=True):
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
    if logic[1] == ">=":
        return_value = bool(val0 >= val1)
    if logic[1] == "<=":
        return_value = bool(val0 <= val1)

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
