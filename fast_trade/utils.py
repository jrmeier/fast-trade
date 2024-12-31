import pandas as pd


def to_dataframe(ticks: list) -> pd.DataFrame:
    """Convert list to Series compatible with the library."""

    df = pd.DataFrame(ticks)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)

    return df


def resample(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Resample DataFrame by <interval>."""

    d = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

    return df.resample(interval).agg(d)


def resample_calendar(df: pd.DataFrame, offset: str) -> pd.DataFrame:
    """Resample the DataFrame by calendar offset.
    See http://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#anchored-offsets for compatible offsets.
    :param df: data
    :param offset: calendar offset
    :return: result DataFrame
    """

    d = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

    return df.resample(offset).agg(d)


def trending_up(df: pd.Series, period: int) -> pd.Series:
    """returns boolean Series if the inputs Series is trending up over last n periods.
    :param df: data
    :param period: range
    :return: result Series
    """

    return pd.Series(df.diff(period) > 0, name="trending_up {}".format(period))


def trending_down(df: pd.Series, period: int) -> pd.Series:
    """returns boolean Series if the input Series is trending up over last n periods.
    :param df: data
    :param period: range
    :return: result Series
    """

    return pd.Series(df.diff(period) < 0, name="trending_down {}".format(period))


def infer_frequency(df: pd.DataFrame) -> str:
    """Infers the frequency of a DataFrame by analyzing time differences between consecutive index values.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a datetime index

    Returns
    -------
    str
        The inferred frequency as a string (e.g., '1Min', '5Min', '1H', '1D', etc.)
        Returns None if frequency cannot be determined
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DatetimeIndex")

    if df.index.freq is not None:
        return df.index.freq

    # Calculate time differences between consecutive index values
    time_diffs = df.index.to_series().diff()

    # Get the most common time difference
    most_common_diff = time_diffs.mode()[0]
    seconds = most_common_diff.total_seconds()

    # Convert seconds to appropriate frequency string
    if seconds < 60:
        return f"{int(seconds)}S"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}Min"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}H"
    else:
        days = int(seconds / 86400)
        return f"{days}D"
