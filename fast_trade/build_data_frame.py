from datetime import datetime
import pandas as pd
from finta import TA
import os
import re


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

    df = prepare_df(df, backtest)

    if df.empty:
        raise Exception("Dataframe is empty. Check the start and end dates")

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
    """Prepares the provided dataframe for a backtest by applying the indicators and splicing based on the given backtest.
        Useful when loading an existing dataframe (ex. from a cache).

    Parameters
    ----------
        df: DataFrame, should have all the open, high, low, close, volume data set as headers and indexed by date
        backtest: dict, provides instructions on how to build the dataframe

    Returns
    ------
        df: DataFrame, with all the indicators as column headers and trimmed to the provided time frames
    """

    indicators = backtest.get("indicators", [])
    df = apply_indicators_to_dataframe(df, indicators)

    if backtest.get("trailing_stop_loss"):
        df["trailing_stop_loss"] = df["close"].cummax() * (1 - backtest.get("trailing_stop_loss"))

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

    if not isinstance(df.index, pd.DatetimeIndex):
        time_unit = detect_time_unit(df.iloc[-1].values[0])
        df.index = pd.to_datetime(df.index, unit=time_unit)
    else:
        df.index = pd.to_datetime(df.index)

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


def apply_indicators_to_dataframe(df: pd.DataFrame, indicators: list):
    """Applies indications from the backtest to the dataframe
    Parameters
    ----------
        df: dataframe loaded with data
        indicators: list of indictors as dictionary objects

        Indicator detail:
        {
            "func": "", string, actual function to be called MUST be in the indicator_map
            "name": "", string, name of the indicator, becomes a column on the dataframe
            "args": [], list arguments to pass the the function
            "df": string, the name of the dataframe column to be used
        }

    Returns
    -------
        df, a modified dataframe with all the indicators calculated as columns
    """
    for ind in indicators:
        func = ind.get("func")
        field_name = ind.get("name")

        if len(ind.get("args", [])):
            args = ind.get("args")
            # df[field_name] = indicator_map[func](df, *args)
            res = indicator_map[func](df, *args)
        else:
            res = indicator_map[func](df)

        if isinstance(res, pd.DataFrame):
            df = process_res_df(df, ind)

        if isinstance(res, pd.Series):
            df[field_name] = res

    return df


def process_res_df(df, ind):
    if ind.get("func", "") == "chandelier":
        return chandelier_helper(df, ind)

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


def chandelier_helper(df, ind):
    if len(ind.get("args", [])):
        args = ind.get("args")
        res = TA.CHANDELIER(df, *args)
    else:
        res = TA.CHANDELIER(df)

    for key in res.keys().values:
        i_name = ind.get("name")
        clean_key = key.lower()
        clean_key = clean_key.replace(".", "")
        df_key = f"{i_name}_{clean_key}"
        df[df_key] = res[key]

    return df

"""
These are all the indicators the can be used in a backtest as a "func".
Any function can be implimented as an indicator.
"""
indicator_map = {
    "sma": TA.SMA,
    "smm": TA.SMM,
    "ssma": TA.SSMA,
    "ema": TA.EMA,
    "dema": TA.DEMA,
    "tema": TA.TEMA,
    "trima": TA.TRIMA,
    "vama": TA.VAMA,
    "er": TA.ER,
    "kama": TA.KAMA,
    "zlema": TA.ZLEMA,
    "wma": TA.WMA,
    "hma": TA.HMA,
    "evwma": TA.EVWMA,
    "vwap": TA.VWAP,
    "smma": TA.SMMA,
    "macd": TA.MACD,
    "ppo": TA.PPO,
    "vw_macd": TA.VW_MACD,
    "ev_macd": TA.EV_MACD,
    "mom": TA.MOM,
    "roc": TA.ROC,
    "rsi": TA.RSI,
    "ift_rsi": TA.IFT_RSI,
    "tr": TA.TR,
    "atr": TA.ATR,
    "sar": TA.SAR,
    "bbands": TA.BBANDS,
    "bbwidth": TA.BBWIDTH,
    "percent_b": TA.PERCENT_B,
    "kc": TA.KC,
    "do": TA.DO,
    "dmi": TA.DMI,
    "adx": TA.ADX,
    "pivot": TA.PIVOT,
    "pivot_fib": TA.PIVOT_FIB,
    "stoch": TA.STOCH,
    "stochd": TA.STOCHD,
    "stochrsi": TA.STOCHRSI,
    "williams": TA.WILLIAMS,
    "uo": TA.UO,
    "ao": TA.AO,
    "mi": TA.MI,
    "vortex": TA.VORTEX,
    "kst": TA.KST,
    "tsi": TA.TSI,
    "tp": TA.TP,
    "adl": TA.ADL,
    "chaikin": TA.CHAIKIN,
    "mfi": TA.MFI,
    "obv": TA.OBV,
    "wobv": TA.WOBV,
    "vzo": TA.VZO,
    "pzo": TA.PZO,
    "efi": TA.EFI,
    "cfi": TA.CFI,
    "ebbp": TA.EBBP,
    "emv": TA.EMV,
    "cci": TA.CCI,
    "copp": TA.COPP,
    "basp": TA.BASP,
    "baspn": TA.BASPN,
    "cmo": TA.CMO,
    "chandelier": TA.CHANDELIER,
    "qstick": TA.QSTICK,
    "tmf": TA.TMF,
    "fish": TA.FISH,
    "ichimoku": TA.ICHIMOKU,
    "apz": TA.APZ,
    "vr": TA.VR,
    "sqzmi": TA.SQZMI,
    "vpt": TA.VPT,
    "fve": TA.FVE,
    "vfi": TA.VFI,
    "msd": TA.MSD,
    # "ta.wto": TA.WTO, needs a helper function
}
