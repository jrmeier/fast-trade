import datetime
import pandas as pd

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

    flagged_enter, flagged_exit = get_flagged_logiz(backtest)

    new_backtest = backtest.copy()
    new_backtest["base_balance"] = backtest.get("base_balance", 1000)
    new_backtest["exit_on_end"] = backtest.get("exit_on_end", True)
    new_backtest["commission"] = backtest.get("commission", 0)
    new_backtest["hard_exit"] = backtest.get("hard_exit", [])
    new_backtest["trailing_stop_loss"] = backtest.get("trailing_stop_loss", 0)

    if ohlcv_path:
        df = build_data_frame(backtest, ohlcv_path)

    df = apply_backtest_to_dataframe(df, new_backtest)

    if flagged_enter or flagged_exit:
        new_backtest["enter"].extend(flagged_enter)
        new_backtest["exit"].extend(flagged_exit)

        df = apply_backtest_to_dataframe(df, new_backtest)

    if summary:
        summary, trade_log = build_summary(df, perf_start_time, new_backtest)
    else:
        perf_stop_time = datetime.datetime.utcnow()
        summary = {"test_duration": (perf_stop_time - perf_start_time).total_seconds()}
        trade_log = None

    return {
        "summary": summary,
        "df": df,
        "trade_df": trade_log,
        "backtest": new_backtest,
    }


def get_flagged_logiz(backtest: dict):
    """removes logiz that need to be processed after the initial run

    Parameters
    ----------
        backtest, dictionary of instructions

    Returns
    -------
     tuple, flagged_enter, flagged_exit list of what to reprocess after the first process
        backtest, dict, modified backtest object
    """

    to_flag = ["aux_perc_change"]
    flagged_exit_idx = []
    flagged_enter_idx = []

    flagged_enter = []
    flagged_exit = []

    for idx, ex in enumerate(backtest["exit"]):
        if ex[0] in to_flag or ex[2] in to_flag:
            flagged_exit_idx.append(idx)

    for e_ex in flagged_exit_idx:
        flagged_exit.append(backtest["exit"].pop(e_ex))

    for idx, en in enumerate(backtest["enter"]):
        if en[0] in to_flag or en[2] in to_flag:
            flagged_enter_idx.append(idx)

    for e_en in flagged_enter:
        flagged_enter.append(backtest["enter"].pop(e_en))

    return flagged_enter, flagged_exit


def flatten_to_logics(list_of_logics):
    if len(list_of_logics) == 1:
        return list_of_logics
    if isinstance(list_of_logics[0], list):
        return flatten_to_logics(list_of_logics[0]) + flatten_to_logics(list_of_logics[1:])
    return list_of_logics[:1] + flatten_to_logics(list_of_logics[1:])


def apply_backtest_to_dataframe(df: pd.DataFrame, backtest: dict):
    """Processes the frame and adds the resultent rows
    Parameters
    ----------
        df, dataframe with all the calculated indicators
        backtest, backtest object

    Returns
    -------
        df, dataframe with with all the actions and backtest processed
    """
    # df["action"] = [determine_action(frame, backtest) for frame in df.itertuples()]

    # get the max length to pass in
    logics = [
        backtest['enter'],
        backtest['exit'],
        backtest['hard_exit'],
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
            actions.append(determine_action(frame, backtest, max_last_frames, last_frames))
        df["action"] = actions
    else:
        df["action"] = [determine_action(frame, backtest) for frame in df.itertuples()]

    df = analyze_df(df, backtest)

    df["aux_perc_change"] = df["total_value"].pct_change() * 100
    df["aux_change"] = df["total_value"].diff()

    return df


def determine_action(frame: pd.DataFrame, backtest: dict, max_last_frames=0, last_frames=[]):
    """processes the actions with the applied logic
    Parameters
    ----------
        frame: current row of the dataframe
        backtest: object with the logic of how to trade
        df_col_map: dictionary with the column name and index
        of the dataframe

    Returns
    -------
        string, "e" (enter), "x" (exit), "h" (hold) of what
        the backtest would do
    """

    trailing_stop_loss = backtest.get("trailing_stop_loss")

    if trailing_stop_loss:
        if frame.close <= frame.trailing_stop_loss:
            return 'x'

    if take_action(frame, backtest['hard_exit'], max_last_frames, last_frames, require_any=True):
        return 'x'

    if take_action(frame, backtest["enter"], max_last_frames, last_frames):
        return "e"

    if take_action(frame, backtest["exit"], max_last_frames, last_frames):
        return "x"

    return "h"


def take_action(current_frame, logics, max_last_frames, last_frames, require_any=False):
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

    last_frames.insert(0, current_frame)
    if len(last_frames) > max_last_frames and len(last_frames) > 1:
        last_frames.pop()

    for last_frame in last_frames:
        res = process_single_frame(logics, last_frame, require_any)
        results.append(res)

    wtf = all(results)
    print("Wtf: ", results)
    return wtf


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
    elif isinstance(field, float) or isinstance(field, int):
        return field

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
