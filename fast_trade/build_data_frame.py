from datetime import datetime
import pandas as pd
import os
import re

from .transformers_map import transformers_map


def build_data_frame(backtest: dict, csv_path: str):
    """Creates a Pandas DataFame with the provided backtest. Used when providing a CSV as the datafile

    Parameters
    ----------
    backtest: dict, provides instructions on how to build the dataframe
    csv_path: string, absolute path of where to find the data file

    Returns
    -------
    object, A Pandas DataFrame indexed buy date
    """
    df = load_basic_df_from_csv(csv_path)

    if df.empty:
        raise Exception("Dataframe is empty. Check the start and end dates")

    df = prepare_df(df, backtest)

    return df


def load_basic_df_from_csv(csv_path: str):
    """Loads a dataframe from a csv
    Parameters
    ----------
        csv_path: string, path to the csv so it can be read

    Returns
        df, A basic dataframe with the data from the csv
    """

    if not os.path.isfile(csv_path):
        raise Exception(f"File not found: {csv_path}")

    df = pd.read_csv(csv_path, header=0)
    df = standardize_df(df)

    return df


def prepare_df(df: pd.DataFrame, backtest: dict):
    """Prepares the provided dataframe for a backtest by applying the datapoints and splicing based on the given backtest.
        Useful when loading an existing dataframe (ex. from a cache).

    Parameters
    ----------
        df: DataFrame, should have all the open, high, low, close, volume data set as headers and indexed by date
        backtest: dict, provides instructions on how to build the dataframe

    Returns
    ------
        df: DataFrame, with all the datapoints as column headers and trimmed to the provided time frames
    """

    datapoints = backtest.get("datapoints", [])
    df = apply_transformers_to_dataframe(df, datapoints)

    trailing_stop_loss = backtest.get("trailing_stop_loss", 0)
    if trailing_stop_loss:
        df["trailing_stop_loss"] = df["close"].cummax() * (
            1 - float(trailing_stop_loss)
        )

    chart_period = backtest.get("chart_period", "1Min")

    start_time = backtest.get("start")
    stop_time = backtest.get("stop")
    df = apply_charting_to_df(df, chart_period, start_time, stop_time)

    return df


def apply_charting_to_df(
    df: pd.DataFrame, chart_period: str, start_time: str, stop_time: str
):
    """Modifies the dataframe based on the chart_period, start dates and end dates
    Parameters
    ----------
        df: dataframe with data loaded
        chart_period: string, describes how often to sample data, default is '1Min' (1 minute)
            see https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#dateoffset-objects
        start_time: datestring in YYYY-MM-DD HH:MM (ex. 2020-08-31 04:00) of when to begin the backtest
        stop_time: datestring of YYYY-MM-DD HH:MM when to stop the backtest
    Returns
        DataFrame, a sorted dataframe ready for consumption by run_backtest
    """

    if start_time:
        if isinstance(start_time, datetime) or type(start_time) is int:
            time_unit = detect_time_unit(start_time)
            start_time = pd.to_datetime(start_time, unit=time_unit)
            start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")

    if stop_time:
        if isinstance(stop_time, datetime) or type(stop_time) is int:
            time_unit = detect_time_unit(stop_time)
            stop_time = pd.to_datetime(stop_time, unit=time_unit)
            stop_time = stop_time.strftime("%Y-%m-%d %H:%M:%S")

    df = df.resample(chart_period).first()

    if start_time and stop_time:
        df = df[start_time:stop_time]  # noqa
    elif start_time and not stop_time:
        df = df[start_time:]  # noqa
    elif not start_time and stop_time:
        df = df[:stop_time]

    return df


def apply_transformers_to_dataframe(df: pd.DataFrame, datapoints: list):
    """Applies indications from the backtest to the dataframe
    Parameters
    ----------
        df: dataframe loaded with data
        datapoints: list of indictors as dictionary objects

        transformer detail:
        {
            "transformer": "", string, actual function to be called MUST be in the datapoints
            "name": "", string, name of the transformer, becomes a column on the dataframe
            "args": [], list arguments to pass the the function
        }

    Returns
    -------
        df, a modified dataframe with all the datapoints calculated as columns
    """
    for ind in datapoints:
        transformer = ind.get("transformer")
        field_name = ind.get("name")

        if len(ind.get("args", [])):
            args = ind.get("args")
            # df[field_name] = datapoints[transformer](df, *args)
            trans_res = transformers_map[transformer](df, *args)
        else:
            trans_res = transformers_map[transformer](df)

        if isinstance(trans_res, pd.DataFrame):
            df = process_res_df(df, ind, trans_res)

        if isinstance(trans_res, pd.Series):
            df[field_name] = trans_res

    return df


def process_res_df(df, ind, trans_res):
    """handle if a transformer returns multiple columns
    To manage this, we just add the name of column in a clean
    way, removing periods and lowercasing it.

    Parameters
    ----------
    df, dataframe, current dataframe
    ind, indicator object
    trans_res, result from the transformer function

    Returns
    -------
    df, dataframe, updated dataframe with the new columns
    """
    for key in trans_res.keys().values:
        i_name = ind.get("name")
        clean_key = key.lower()
        clean_key = clean_key.replace(".", "")
        clean_key = clean_key.replace(" ", "_")
        df_key = f"{i_name}_{clean_key}"
        df[df_key] = trans_res[key]

    return df


def detect_time_unit(str_or_int: str or int):
    """Determines a if a timestamp is really a timestamp and if it
    matches is in seconds or milliseconds
    Parameters
    ----------
        str_or_int: string or int of the timestamp to detect against

    Returns
    -------
        string of "s" or "ms", or None if nothing detected
    """
    str_or_int = str(str_or_int)
    regex1 = r"^(\d{10})$"
    regex2 = r"^(\d{13})$"

    if re.match(regex1, str_or_int):
        return "s"
    if re.match(regex2, str_or_int):
        return "ms"


def standardize_df(df: pd.DataFrame):
    """Standardizes a dataframe with the basic features used
    throughout the project.
    Parameters
    ----------
        df: A pandas dataframe (probably one just created) with
    at least the required columns of: date, open, close, high, low, volume.

    Returns
    -------
        A new pandas dataframe of with all the data in the expected types.
    """
    new_df = df.copy()

    if "date" in new_df.columns:
        new_df = new_df.set_index("date")

    ts = str(new_df.index[0])

    time_unit = detect_time_unit(ts)

    new_df.index = pd.to_datetime(new_df.index, unit=time_unit)
    new_df = new_df[~new_df.index.duplicated(keep="first")]
    new_df = new_df.sort_index()

    columns_to_drop = ["ignore", "date"]

    new_df.drop(columns=columns_to_drop, errors="ignore")

    new_df.open = pd.to_numeric(new_df.open)
    new_df.close = pd.to_numeric(new_df.close)
    new_df.high = pd.to_numeric(new_df.high)
    new_df.low = pd.to_numeric(new_df.low)
    new_df.volume = pd.to_numeric(new_df.volume)

    return new_df
