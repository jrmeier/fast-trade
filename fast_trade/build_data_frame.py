import pandas as pd
from finta import TA
import os

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def build_data_frame(strategy: dict, csv_path: str):
    """Creates a Pandas DataFame with the provided strategy. Used when providing a CSV as the datafile

    Parameters
    ----------
    strategy: dict, provides instructions on how to build the dataframe
    csv_path: string, absolute path of where to find the data file

    Returns
    -------
    object, A Pandas DataFrame indexed buy date
    """
    df = load_basic_df_from_csv(csv_path)

    df = prepare_df(df, strategy)

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
    cols = [0, 1, 2, 3, 4, 5]
    df = pd.read_csv(csv_path, parse_dates=True, usecols=cols)
    df = df.set_index("date")
    df = df.drop_duplicates()
    time_unit = detect_time_unit(df.iloc[0].values[0])
    df.index = pd.to_datetime(df.index, unit=time_unit)

    return df


def prepare_df(df: pd.DataFrame, strategy: dict):
    """Prepares the provided dataframe for a backtest by applying the indicators and splicing based on the given strategy.
        Useful when loading an existing dataframe (ex. from a cache).

    Parameters
    ----------
        df: DataFrame, should have all the open, high, low, close, volume data set as headers and indexed by date
        strategy: dict, provides instructions on how to build the dataframe

    Returns
    ------
        df: DataFrame, with all the indicators as column headers and trimmed to the provided time frames
    """

    indicators = strategy.get("indicators", [])
    df = apply_indicators_to_dataframe(df, indicators)

    chart_period = strategy.get("chart_period", "1Min")

    start_time = strategy.get("start")
    stop_time = strategy.get("stop")
    df = apply_charting_to_df(df, chart_period, start_time, stop_time)

    return df


def add_freq(idx, freq=None):
    """Add a frequency attribute to idx, through inference or directly.

    Returns a copy.  If `freq` is None, it is inferred.
    """

    idx = idx.copy()
    if freq is None:
        if idx.freq is None:
            freq = pd.infer_freq(idx)
        else:
            return idx
    idx.freq = pd.tseries.frequencies.to_offset(freq)
    if idx.freq is None:
        raise AttributeError(
            "no discernible frequency found to `idx`.  Specify"
            " a frequency string with `freq`."
        )
    return idx


def apply_charting_to_df(
    df: pd.DataFrame, chart_period: str, start_time: str, stop_time: str
):
    """Modifies the dataframe based on the chart_period, start dates and end dates
    Parameters
    ----------
        df: dataframe with data loaded
        chart_period: string, describes how often to sample data, default is '1M' (1 minute)
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

    df = df.resample(chart_period).first()

    if start_time and stop_time:
        df = df[start_time:stop_time]  # noqa
    elif start_time and not stop_time:
        df = df[start_time:]  # noqa
    elif not start_time and stop_time:
        df = df[:stop_time]

    return df


def apply_indicators_to_dataframe(df: pd.DataFrame, indicators: list):
    """Applies indications from the strategy to the dataframe
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
        if ind.get("args"):
            args = ind.get("args")
            df[field_name] = indicator_map[func](df, *args)
        else:
            df[field_name] = indicator_map[func](df)

    return df


def detect_time_unit(timestamp: int):
    """Detects whether the timestamp is in seconds or milliseconds

    Parameters
        timestamp, usually a np.int64
    Returns
        string
    """
    if len(str(timestamp)) == 10:
        return "s"

    return "ms"


"""
These are all the indicators the can be used in a strategy as a "func".
Any function can be implimented as an indicator.
"""
indicator_map = {
    "ta.sma": TA.SMA,
    "ta.smm": TA.SMM,
    "ta.ssma": TA.SSMA,
    "ta.ema": TA.EMA,
    "ta.dema": TA.DEMA,
    "ta.tema": TA.TEMA,
    "ta.trima": TA.TRIMA,
    "ta.vama": TA.VAMA,
    "ta.er": TA.ER,
    "ta.kama": TA.KAMA,
    "ta.zlema": TA.ZLEMA,
    "ta.wma": TA.WMA,
    "ta.hma": TA.HMA,
    "ta.evwma": TA.EVWMA,
    "ta.vwap": TA.VWAP,
    "ta.smma": TA.SMMA,
    "ta.macd": TA.MACD,
    "ta.ppo": TA.PPO,
    "ta.vw_macd": TA.VW_MACD,
    "ta.ev_macd": TA.EV_MACD,
    "ta.mom": TA.MOM,
    "ta.roc": TA.ROC,
    "ta.rsi": TA.RSI,
    "ta.ift_rsi": TA.IFT_RSI,
    "ta.tr": TA.TR,
    "ta.atr": TA.ATR,
    "ta.sar": TA.SAR,
    "ta.bbands": TA.BBANDS,
    "ta.bbwidth": TA.BBWIDTH,
    "ta.percent_b": TA.PERCENT_B,
    "ta.kc": TA.KC,
    "ta.do": TA.DO,
    "ta.dmi": TA.DMI,
    "ta.adx": TA.ADX,
    "ta.pivot": TA.PIVOT,
    "ta.pivot_fib": TA.PIVOT_FIB,
    "ta.stoch": TA.STOCH,
    "ta.stochd": TA.STOCHD,
    "ta.stochrsi": TA.STOCHRSI,
    "ta.williams": TA.WILLIAMS,
    "ta.uo": TA.UO,
    "ta.ao": TA.AO,
    "ta.mi": TA.MI,
    "ta.vortex": TA.VORTEX,
    "ta.kst": TA.KST,
    "ta.tsi": TA.TSI,
    "ta.tp": TA.TP,
    "ta.adl": TA.ADL,
    "ta.chaikin": TA.CHAIKIN,
    "ta.mfi": TA.MFI,
    "ta.obv": TA.OBV,
    "ta.wobv": TA.WOBV,
    "ta.vzo": TA.VZO,
    "ta.pzo": TA.PZO,
    "ta.efi": TA.EFI,
    "ta.cfi": TA.CFI,
    "ta.ebbp": TA.EBBP,
    "ta.emv": TA.EMV,
    "ta.cci": TA.CCI,
    "ta.copp": TA.COPP,
    "ta.basp": TA.BASP,
    "ta.baspn": TA.BASPN,
    "ta.cmo": TA.CMO,
    "ta.chandelier": TA.CHANDELIER,
    "ta.qstick": TA.QSTICK,
    "ta.tmf": TA.TMF,
    "ta.fish": TA.FISH,
    "ta.ichimoku": TA.ICHIMOKU,
    "ta.apz": TA.APZ,
    "ta.vr": TA.VR,
    "ta.sqzmi": TA.SQZMI,
    "ta.vpt": TA.VPT,
    "ta.fve": TA.FVE,
    "ta.vfi": TA.VFI,
    "ta.msd": TA.MSD,
    # "ta.wto": TA.WTO, needs a helper function
}
