import datetime
import operator
import re
import multiprocessing as mp
from collections import deque
from functools import partial

import pandas as pd

from fast_trade.archive.db_helpers import get_kline

from .build_data_frame import prepare_df
from .build_summary import build_summary
from .evaluate import evaluate_rules
from .run_analysis import apply_logic_to_df
from .logic_utils import can_vectorize_logic, max_last_frames, vectorized_actions
from .validate_backtest import validate_backtest, validate_backtest_with_df


_LOGIC_OPERATORS = {
    ">": operator.gt,
    "<": operator.lt,
    "=": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
}


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


def run_backtest(
    backtest: dict,
    df: pd.DataFrame = pd.DataFrame(),
    summary=True,
    progress_callback=None,
):
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
        if progress_callback:
            progress_callback({"phase": "data", "percent": 0})
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

        start = backtest.get("start", None)
        if start and not isinstance(start, datetime.datetime):
            start = datetime.datetime.fromisoformat(start)
            start = start - td_freq * max_periods

        # get the data from the local archive
        df = get_kline(
            backtest.get("symbol"),
            backtest.get("exchange"),
            start,
            backtest.get("stop"),
            freq=backtest.get("freq") or backtest.get("chart_period"),
        )
        if progress_callback:
            progress_callback({"phase": "data", "percent": 100})

    if df.empty:
        raise MissingData(
            f"No data found for {backtest.get('symbol')} on {backtest.get('exchange')} or in the given dataframe"
        )

    df = prepare_df(df, new_backtest)

    df = apply_backtest_to_df(
        df,
        new_backtest,
        progress_callback=progress_callback,
    )
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


def apply_backtest_to_df(df: pd.DataFrame, backtest: dict, progress_callback=None):
    """Processes the frame and adds the resultent rows
    Parameters
    ----------
        df, dataframe with all the calculated datapoints
        backtest, backtest object

    Returns
    -------
        df, dataframe with with all the actions and backtest processed
    """

    df = process_logic_and_generate_actions(
        df,
        backtest,
        progress_callback=(
            lambda payload: progress_callback(
                {**payload, "phase": "actions"}
            )
            if progress_callback
            else None
        ),
    )

    df = apply_logic_to_df(
        df,
        backtest,
        progress_callback=(
            lambda payload: progress_callback(
                {**payload, "phase": "simulation"}
            )
            if progress_callback
            else None
        ),
    )

    df["adj_account_value_change_perc"] = df["adj_account_value"].pct_change()
    df["adj_account_value_change"] = df["adj_account_value"].diff()

    # set the index to the date
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df


def process_logic_and_generate_actions(
    df: pd.DataFrame, backtest: object, progress_callback=None
):
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
    This optimized version uses vectorized operations where possible.
    """

    """we need to search though all the logics and find the highest confirmation number
    so we know how many frames to pass in
    """
    max_last = max_last_frames(backtest)
    compiled_logic = compile_action_logic(backtest)

    # If we need to look at previous frames, we can't fully vectorize
    if max_last:
        actions = []
        last_frames = deque(maxlen=max_last)
        total_rows = len(df)
        update_every = max(1, total_rows // 200)
        for idx, frame in enumerate(df.itertuples()):
            last_frames.appendleft(frame)
            actions.append(determine_action_compiled(frame, compiled_logic, last_frames))
            if progress_callback and (idx % update_every == 0 or idx == total_rows - 1):
                progress_callback({"percent": int((idx + 1) / total_rows * 100)})
        df["action"] = actions
    else:
        try:
            if can_vectorize_logic(df, backtest):
                df["action"] = vectorized_actions(df, backtest)
                if progress_callback:
                    progress_callback({"percent": 100})
            else:
                actions = []
                total_rows = len(df)
                update_every = max(1, total_rows // 200)
                for idx, frame in enumerate(df.itertuples()):
                    actions.append(determine_action_compiled(frame, compiled_logic))
                    if progress_callback and (idx % update_every == 0 or idx == total_rows - 1):
                        progress_callback({"percent": int((idx + 1) / total_rows * 100)})
                df["action"] = actions
        except Exception:
            # If vectorization fails for any reason, fall back to row-by-row processing
            actions = []
            total_rows = len(df)
            update_every = max(1, total_rows // 200)
            for idx, frame in enumerate(df.itertuples()):
                actions.append(determine_action_compiled(frame, compiled_logic))
                if progress_callback and (
                    idx % update_every == 0 or idx == total_rows - 1
                ):
                    progress_callback({"percent": int((idx + 1) / total_rows * 100)})
            df["action"] = actions

    return df


def _compile_field_accessor(field):
    if isinstance(field, str):
        if field.isnumeric():
            return False, int(field)
        if re.match(r"^-?\d+(?:\.\d+)$", field):
            return False, float(field)
        return True, field

    if isinstance(field, (bool, int, float)):
        return False, field

    return False, field


def compile_action_logic(backtest: dict) -> dict:
    def compile_group(logics):
        return [
            (
                _compile_field_accessor(logic[0]),
                _LOGIC_OPERATORS.get(logic[1]),
                _compile_field_accessor(logic[2]),
                logic[3] if len(logic) > 3 else 0,
            )
            for logic in logics
        ]

    return {
        "trailing_stop_loss": bool(backtest.get("trailing_stop_loss")),
        "exit": compile_group(backtest.get("exit", [])),
        "any_exit": compile_group(backtest.get("any_exit", [])),
        "enter": compile_group(backtest.get("enter", [])),
        "any_enter": compile_group(backtest.get("any_enter", [])),
    }


def _resolve_compiled_field(field_accessor, row):
    is_attr, value = field_accessor
    if not is_attr:
        return value
    if isinstance(row, dict):
        return row[value]
    return getattr(row, value)


def _process_compiled_logic(compiled_logic, row):
    left_accessor, op, right_accessor, _frames = compiled_logic
    left_value = _resolve_compiled_field(left_accessor, row)
    right_value = _resolve_compiled_field(right_accessor, row)
    return bool(op(left_value, right_value))


def _take_action_compiled(current_frame, compiled_logics, last_frames=None, require_any=False):
    if not compiled_logics:
        return False

    if last_frames is None:
        last_frames = []

    for compiled_logic in compiled_logics:
        frames = compiled_logic[3]
        if frames > 0:
            if len(last_frames) < frames:
                if not require_any:
                    return False
                continue

            result = True
            for frame_idx in range(frames):
                if not _process_compiled_logic(compiled_logic, last_frames[frame_idx]):
                    result = False
                    break
        else:
            result = _process_compiled_logic(compiled_logic, current_frame)

        if require_any and result:
            return True
        if not require_any and not result:
            return False

    return not require_any


def determine_action_compiled(frame, compiled_logic: dict, last_frames=None):
    if last_frames is None:
        last_frames = []

    if compiled_logic.get("trailing_stop_loss"):
        if frame.close <= frame.trailing_stop_loss:
            return "tsl"

    if _take_action_compiled(frame, compiled_logic.get("exit", []), last_frames):
        return "x"

    if _take_action_compiled(
        frame,
        compiled_logic.get("any_exit", []),
        last_frames,
        require_any=True,
    ):
        return "ax"

    if _take_action_compiled(frame, compiled_logic.get("enter", []), last_frames):
        return "e"

    if _take_action_compiled(
        frame,
        compiled_logic.get("any_enter", []),
        last_frames,
        require_any=True,
    ):
        return "ae"

    return "h"


def determine_action(frame: pd.DataFrame, backtest: dict, last_frames=None):
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

    if last_frames is None:
        last_frames = []
    return determine_action_compiled(frame, compile_action_logic(backtest), last_frames)


def take_action(current_frame, logics, last_frames=None, require_any=False):
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

    if last_frames is None:
        last_frames = []
    if not logics:
        return False

    if len(last_frames):
        for logic in logics:
            if len(logic) > 3:
                frames = logic[3]
                if len(last_frames) < frames:
                    if not require_any:
                        return False
                    continue

                res = True
                for frame_idx in range(frames):
                    if not process_single_frame([logic], last_frames[frame_idx], require_any=False):
                        res = False
                        break
            else:
                res = process_single_frame([logic], current_frame, require_any)

            if require_any and res:
                return True
            if not require_any and not res:
                return False
    else:
        return process_single_frame(logics, current_frame, require_any)

    return not require_any


def process_single_frame(logics, row, require_any):
    if not logics:
        return False

    for logic in logics:
        res = process_single_logic(logic, row)
        if require_any:
            if res:
                return True
        elif not res:
            return False

    return not require_any


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
        if isinstance(row, dict):
            return row[field]
        return getattr(row, field)

    return row


def run_backtests_parallel(
    backtests: list, df: pd.DataFrame = pd.DataFrame(), summary=True, n_processes=None
):
    """
    Run multiple backtests in parallel

    Parameters
    ----------
    backtests: list of dict, required, list of backtest configurations to run
    df: pandas dataframe, optional, dataframe to use for all backtests
    summary: bool, optional, whether to generate summary statistics
    n_processes: int, optional, number of processes to use (defaults to CPU count)

    Returns
    -------
    list of dict, results from each backtest
    """
    if n_processes is None:
        n_processes = mp.cpu_count()

    # Create a partial function with fixed df and summary parameters
    run_backtest_partial = partial(run_backtest, df=df, summary=summary)

    # Run backtests in parallel
    with mp.Pool(processes=n_processes) as pool:
        results = pool.map(run_backtest_partial, backtests)

    return results


def run_backtest_chunked(
    backtest: dict, df: pd.DataFrame = pd.DataFrame(), summary=True, chunk_size=None
):
    """
    Run a backtest by splitting the dataframe into chunks and processing them in parallel

    Parameters
    ----------
    backtest: dict, required, backtest configuration
    df: pandas dataframe, optional, dataframe to use
    summary: bool, optional, whether to generate summary statistics
    chunk_size: int, optional, size of chunks to split the dataframe into

    Returns
    -------
    dict, combined results from the chunked backtest
    """
    performance_start_time = datetime.datetime.utcnow()
    new_backtest = prepare_new_backtest(backtest)
    errors = validate_backtest(new_backtest)

    if errors.get("has_error"):
        error_keys = [
            key for key, value in errors.items() if value and key != "has_error"
        ]
        error_msgs = extract_error_messages(errors)
        for ek in error_keys:
            if ek not in ["any_enter", "any_exit"]:
                raise BacktestKeyError(error_msgs)

    if df.empty:
        # Same data loading logic as in run_backtest
        def get_max_periods(datapoint):
            args = datapoint.get("args", [])
            periods = [int(arg) for arg in args if isinstance(arg, int)]
            if len(periods) == 0:
                return 0
            return max(periods)

        args = [get_max_periods(dp) for dp in new_backtest.get("datapoints", [])]
        max_periods = max(args)
        freq = new_backtest.get("freq")
        if not freq and new_backtest.get("chart_period"):
            freq = new_backtest.get("chart_period")
        td_freq = pd.Timedelta(freq)

        start = backtest.get("start", None)
        if start and not isinstance(start, datetime.datetime):
            start = datetime.datetime.fromisoformat(start)
            start = start - td_freq * max_periods

        df = get_kline(
            backtest.get("symbol"),
            backtest.get("exchange"),
            start,
            backtest.get("stop"),
            freq=backtest.get("freq") or backtest.get("chart_period"),
        )

    if df.empty:
        raise MissingData(
            f"No data found for {backtest.get('symbol')} on {backtest.get('exchange')} or in the given dataframe"
        )

    # Prepare the dataframe with indicators
    df = prepare_df(df, new_backtest)

    # Determine chunk size if not provided
    if chunk_size is None:
        # Default to a reasonable chunk size based on dataframe length
        chunk_size = max(1000, len(df) // mp.cpu_count())

    # Split the dataframe into chunks
    chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]

    # Process each chunk in parallel
    with mp.Pool(processes=mp.cpu_count()) as pool:
        processed_chunks = pool.map(
            partial(apply_backtest_to_df, backtest=new_backtest), chunks
        )

    # Combine the processed chunks
    processed_df = pd.concat(processed_chunks)

    # Validate the combined dataframe
    validate_backtest_with_df(new_backtest, processed_df)

    # Generate summary if requested
    if summary:
        summary, trade_log = build_summary(processed_df, performance_start_time)
    else:
        performance_stop_time = datetime.datetime.utcnow()
        summary = {
            "test_duration": (
                performance_stop_time - performance_start_time
            ).total_seconds()
        }
        trade_log = pd.DataFrame()

    # Evaluate rules
    rule_eval = evaluate_rules(summary, new_backtest.get("rules", []))
    summary["rules"] = {
        "all": rule_eval[0],
        "any": rule_eval[1],
        "results": rule_eval[2],
    }

    # Add strategy to summary
    summary["strategy"] = new_backtest

    return {
        "summary": summary,
        "df": processed_df,
        "trade_df": trade_log,
        "backtest": new_backtest,
    }
