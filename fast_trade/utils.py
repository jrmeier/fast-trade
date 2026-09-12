"""Polars helpers shared by the data loading and archive modules.

OHLCV frames in fast-trade are ``pl.DataFrame`` objects with an explicit
``date`` column of dtype ``pl.Datetime`` sorted ascending. There is no index,
so anything that used to rely on a ``DatetimeIndex`` works off ``date``.

Frequencies are still written the pandas way in strategies and configs
(``"1Min"``, ``"1H"``, ``"1D"`` ...). :func:`parse_freq` translates those
aliases into the duration strings Polars expects (``"1m"``, ``"1h"``, ``"1d"``).
"""

import datetime
import re
import typing

import polars as pl

DATE_COL = "date"
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")

# open=first, high=max, low=min, close=last, volume=sum
OHLCV_AGGREGATIONS = (
    ("open", "first"),
    ("high", "max"),
    ("low", "min"),
    ("close", "last"),
    ("volume", "sum"),
)

# pandas offset alias -> polars duration unit
_FREQ_ALIASES = {
    "ns": "ns",
    "us": "us",
    "ms": "ms",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "t": "m",
    "m": "m",
    "min": "m",
    "mins": "m",
    "minute": "m",
    "minutes": "m",
    "h": "h",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
    "d": "d",
    "day": "d",
    "days": "d",
    "w": "w",
    "week": "w",
    "weeks": "w",
    "mo": "mo",
    "month": "mo",
    "months": "mo",
    "q": "q",
    "quarter": "q",
    "quarters": "q",
    "y": "y",
    "year": "y",
    "years": "y",
}

_FREQ_PATTERN = re.compile(r"^\s*(\d*)\s*([A-Za-z]+)\s*$")

# parquet files written by the pandas implementation kept the date in an
# unnamed index, which arrow stores under this column name
_PANDAS_INDEX_COL = "__index_level_0__"


def parse_freq(freq: typing.Any) -> typing.Optional[str]:
    """Translate a frequency alias into a Polars duration string.

    Accepts pandas style aliases (``"1Min"``, ``"30S"``, ``"2H"``), Polars
    duration strings (``"1m"``, ``"30s"``) and ``datetime.timedelta``.
    Returns None when the value cannot be understood.
    """
    if isinstance(freq, datetime.timedelta):
        seconds = freq.total_seconds()
        if seconds <= 0:
            return None
        if seconds % 1:
            return f"{int(seconds * 1_000_000)}us"
        return f"{int(seconds)}s"

    if not isinstance(freq, str):
        # pandas offsets and anything else with a usable repr
        freq = getattr(freq, "freqstr", None) or str(freq)

    match = _FREQ_PATTERN.match(freq)
    if not match:
        return None

    count, unit = match.groups()
    unit = _FREQ_ALIASES.get(unit.lower())
    if unit is None:
        return None

    return f"{int(count) if count else 1}{unit}"


def freq_to_polars(freq: typing.Any) -> str:
    """Same as :func:`parse_freq` but raises on an unusable frequency."""
    parsed = parse_freq(freq)
    if parsed is None:
        raise ValueError(f"Invalid frequency: {freq!r}")
    return parsed


def detect_time_unit(str_or_int: typing.Union[str, int]) -> typing.Optional[str]:
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

    if re.match(r"^(\d{10})$", str_or_int):
        return "s"
    if re.match(r"^(\d{13})$", str_or_int):
        return "ms"
    return None


def ensure_date_column(
    df: pl.DataFrame, date_col: str = DATE_COL, unit: typing.Optional[str] = None
) -> pl.DataFrame:
    """Return ``df`` with ``date_col`` guaranteed to be a Datetime column.

    Epoch seconds/milliseconds, ISO strings and legacy parquet files that
    stored the date in an unnamed pandas index are all handled.
    """
    if date_col not in df.columns and _PANDAS_INDEX_COL in df.columns:
        df = df.rename({_PANDAS_INDEX_COL: date_col})

    if date_col not in df.columns:
        raise ValueError(f"DataFrame does not have a '{date_col}' column")

    dtype = df.schema[date_col]

    if dtype == pl.Date:
        return df.with_columns(pl.col(date_col).cast(pl.Datetime))

    if isinstance(dtype, pl.Datetime):
        return df

    if df.height == 0:
        return df.with_columns(pl.col(date_col).cast(pl.Datetime))

    sample = df.get_column(date_col).drop_nulls()
    sample = sample[0] if len(sample) else None
    time_unit = unit or detect_time_unit(sample) or "s"

    if dtype.is_numeric():
        return df.with_columns(
            pl.from_epoch(pl.col(date_col).cast(pl.Int64), time_unit=time_unit)
        )

    if detect_time_unit(sample):
        return df.with_columns(
            pl.from_epoch(pl.col(date_col).cast(pl.Int64), time_unit=time_unit)
        )

    return df.with_columns(pl.col(date_col).str.to_datetime())


def date_series(df: pl.DataFrame, date_col: str = DATE_COL) -> pl.Series:
    """Return the datetime column of ``df``, raising when it is unusable."""
    if date_col not in df.columns:
        raise ValueError(f"DataFrame does not have a '{date_col}' column")

    series = df.get_column(date_col)
    if not isinstance(series.dtype, pl.Datetime) and series.dtype != pl.Date:
        raise ValueError(f"Column '{date_col}' is not a datetime column")

    return series


def infer_frequency(
    df: pl.DataFrame, date_col: str = DATE_COL
) -> typing.Optional[str]:
    """Infers the frequency of a DataFrame from the gaps in its date column.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame with a datetime ``date`` column
    date_col : str
        Name of the datetime column

    Returns
    -------
    str
        The inferred frequency as a pandas style string (e.g. '1Min', '5Min',
        '1H', '1D'). Returns None when the frequency cannot be determined.
    """
    dates = date_series(df, date_col)

    if len(dates) < 2:
        return None

    diffs = dates.diff().drop_nulls().dt.total_microseconds()
    diffs = diffs.filter(diffs > 0)
    if diffs.is_empty():
        return None

    modes = diffs.mode().sort()
    micros = modes[0] if len(modes) else diffs.median()
    seconds = float(micros) / 1_000_000

    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        return f"{int(seconds)}S"
    if seconds < 3600:
        return f"{int(seconds / 60)}Min"
    if seconds < 86400:
        return f"{int(seconds / 3600)}H"
    return f"{int(seconds / 86400)}D"


def resample_ohlcv(
    df: pl.DataFrame, interval: str, date_col: str = DATE_COL
) -> pl.DataFrame:
    """Aggregate an OHLCV frame to ``interval``.

    open=first, high=max, low=min, close=last, volume=sum. Only windows that
    contain data are returned; use :func:`upsample_to_freq` to get a
    gap free grid.
    """
    every = freq_to_polars(interval)

    aggregations = [
        getattr(pl.col(name), how)().alias(name)
        for name, how in OHLCV_AGGREGATIONS
        if name in df.columns
    ]

    return (
        df.sort(date_col)
        .group_by_dynamic(date_col, every=every)
        .agg(aggregations)
    )


def resample_first(
    df: pl.DataFrame, interval: str, date_col: str = DATE_COL
) -> pl.DataFrame:
    """Downsample every column of ``df`` to the first value in each window."""
    every = freq_to_polars(interval)

    return (
        df.sort(date_col)
        .group_by_dynamic(date_col, every=every)
        .agg(pl.exclude(date_col).first())
    )


def upsample_to_freq(
    df: pl.DataFrame,
    interval: str,
    date_col: str = DATE_COL,
    forward_fill: bool = False,
) -> pl.DataFrame:
    """Put ``df`` on a regular ``interval`` grid, optionally forward filling.

    This is the Polars equivalent of ``df.asfreq(freq)`` (and
    ``df.asfreq(freq).ffill()`` when ``forward_fill`` is set): rows land on the
    grid anchored at the first date, and gaps show up as nulls.
    """
    every = freq_to_polars(interval)

    out = df.sort(date_col)
    if out.height > 1:
        out = out.upsample(time_column=date_col, every=every)
    if forward_fill:
        out = out.fill_null(strategy="forward")

    return out


def to_dataframe(ticks: list) -> pl.DataFrame:
    """Convert a list of ticks to an OHLCV frame with a ``date`` column."""
    df = pl.DataFrame(ticks)

    if DATE_COL not in df.columns and "time" in df.columns:
        df = df.rename({"time": DATE_COL})

    df = ensure_date_column(df)

    ordered = [DATE_COL] + [col for col in df.columns if col != DATE_COL]

    return df.select(ordered).sort(DATE_COL)


def resample(df: pl.DataFrame, interval: str) -> pl.DataFrame:
    """Resample DataFrame by <interval>."""
    return resample_ohlcv(df, interval)


def resample_calendar(df: pl.DataFrame, offset: str) -> pl.DataFrame:
    """Resample the DataFrame by calendar offset.

    Polars durations are calendar aware, so this matches :func:`resample`.
    """
    return resample_ohlcv(df, offset)


def trending_up(df: pl.Series, period: int) -> pl.Series:
    """returns boolean Series if the inputs Series is trending up over last n periods.
    :param df: data
    :param period: range
    :return: result Series
    """
    return (df.diff(period) > 0).fill_null(False).alias(
        "trending_up {}".format(period)
    )


def trending_down(df: pl.Series, period: int) -> pl.Series:
    """returns boolean Series if the input Series is trending up over last n periods.
    :param df: data
    :param period: range
    :return: result Series
    """
    return (df.diff(period) < 0).fill_null(False).alias(
        "trending_down {}".format(period)
    )
