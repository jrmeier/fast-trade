import datetime
import os
import re
import typing

import polars as pl

from .transformers_map import transformers_map
from .utils import (  # noqa: F401  (detect_time_unit re-exported for callers)
    DATE_COL,
    OHLCV_COLUMNS,
    detect_time_unit,
    ensure_date_column,
    infer_frequency,
    parse_freq,
    resample_first,
    resample_ohlcv,
    upsample_to_freq,
)

_PARTIAL_DATE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")
_FALLBACK_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
)
_MISSING_DATE_MSG = (
    "Data does not have a date column. Headers must include date, open, high, low, close, volume."
)


class TransformerError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return self.message


def build_data_frame(backtest: dict, csv_path: str) -> pl.DataFrame:
    """Creates a Polars DataFrame with the provided backtest. Used when providing a CSV as the datafile

    Parameters
    ----------
    backtest: dict, provides instructions on how to build the dataframe
    csv_path: string, absolute path of where to find the data file

    Returns
    -------
    object, A Polars DataFrame with a sorted "date" column
    """
    df = load_basic_df_from_csv(csv_path)

    if df.is_empty():
        raise Exception("Dataframe is empty. Check the start and end dates")

    df = prepare_df(df, backtest)

    return df


def load_basic_df_from_csv(csv_path: str) -> pl.DataFrame:
    """Loads a dataframe from a csv
    Parameters
    ----------
        csv_path: string, path to the csv so it can be read

    Returns
        df, A basic dataframe with the data from the csv
    """

    if not os.path.isfile(csv_path):
        raise Exception(f"File not found: {csv_path}")

    df = pl.read_csv(csv_path)

    return standardize_df(df)


def prepare_df(df: pl.DataFrame, backtest: dict) -> pl.DataFrame:
    """Prepares the provided dataframe for a backtest by applying the datapoints and splicing based on the given backtest.
        Useful when loading an existing dataframe (ex. from a cache).

    Parameters
    ----------
        df: DataFrame, should have a date column plus open, high, low, close, volume
        backtest: dict, provides instructions on how to build the dataframe

    Returns
    ------
        df: DataFrame, with all the datapoints as column headers and trimmed to the provided time frames
    """

    datapoints = backtest.get("datapoints", [])

    if backtest.get("chart_period"):
        # raise a warning if chart_period is not a valid frequency
        if not parse_freq(backtest.get("chart_period")):
            raise ValueError(f"Invalid chart period: {backtest.get('chart_period')}")
        freq = backtest.get("chart_period")
    else:
        freq = backtest.get("freq", "1Min")

    start_time = backtest.get("start")
    stop_time = backtest.get("stop")
    df = apply_charting_to_df(df, freq, start_time, stop_time)
    df = apply_transformers_to_dataframe(df, datapoints)
    trailing_stop_loss = backtest.get("trailing_stop_loss", 0)
    if trailing_stop_loss:
        df = df.with_columns(
            (pl.col("close").cum_max() * (1 - float(trailing_stop_loss))).alias(
                "trailing_stop_loss"
            )
        )

    return df


def apply_charting_to_df(
    df: pl.DataFrame,
    freq: str,
    start_time: typing.Any,
    stop_time: typing.Any,
) -> pl.DataFrame:
    """Modifies the dataframe based on the freq, start dates and end dates
    Parameters
    ----------
        df: dataframe with data loaded
        freq: string, describes how often to sample data, default is '1Min' (1 minute)
        start_time: datestring in YYYY-MM-DD HH:MM (ex. 2020-08-31 04:00) of when to begin the backtest
        stop_time: datestring of YYYY-MM-DD HH:MM when to stop the backtest
    Returns
        DataFrame, a sorted dataframe ready for consumption by run_backtest
    """
    if DATE_COL not in df.columns:
        raise Exception(_MISSING_DATE_MSG)

    df = ensure_date_column(df).sort(DATE_COL)

    start = parse_date_bound(start_time)
    stop = parse_date_bound(stop_time, upper=True)

    df = resample_first(df, freq)
    df = upsample_to_freq(df, freq)

    if start is not None:
        df = df.filter(pl.col(DATE_COL) >= start)
    if stop is not None:
        df = df.filter(pl.col(DATE_COL) <= stop)

    return df


def apply_transformers_to_dataframe(
    df: pl.DataFrame,
    transformers: list,
) -> pl.DataFrame:
    """Applies indications from the backtest to the dataframe
    Parameters
    ----------
        df: dataframe loaded with data
        transformers: list of transformers as dictionary objects

        transformer detail:
        {
            "transformer": "", string, actual function to be called MUST be in the transformers_map
            "name": "", string, name of the transformer, becomes a column on the dataframe
            "args": [], list arguments to pass the the function,
            "freq": "", string, frequency of the transformer, default is the freq in the backtest
        }

    Returns
    -------
        df, a modified dataframe with all the datapoints calculated as columns
    """
    if DATE_COL not in df.columns:
        raise Exception(_MISSING_DATE_MSG)

    df = ensure_date_column(df).sort(DATE_COL)

    base_freq = infer_frequency(df)
    # put the dataframe on a regular grid so the transformers see even spacing
    if base_freq:
        df = upsample_to_freq(df, base_freq)

    for ind in transformers:
        transformer = ind.get("transformer")
        field_name = ind.get("name")
        freq = ind.get("freq", None)

        # Create a temporary dataframe with the desired frequency
        if freq:
            tmp_df = resample_ohlcv(df, freq).fill_null(strategy="forward")
        else:
            tmp_df = df

        # make sure the transformer is in the transformers_map
        if transformer not in transformers_map:
            raise ValueError(f"Transformer '{transformer}' not a valid transformer.")
        try:
            if len(ind.get("args", [])):
                args = ind.get("args")
                trans_res = transformers_map[transformer](tmp_df, *args)
            else:
                trans_res = transformers_map[transformer](tmp_df)
        except Exception as e:
            raise TransformerError(f"Error applying transformer '{transformer}': {e}")

        dates = tmp_df.get_column(DATE_COL)

        if isinstance(trans_res, pl.DataFrame):
            df = process_res_df(df, ind, trans_res, dates)
        elif isinstance(trans_res, pl.Series):
            df = attach_transformer_columns(df, {field_name: trans_res}, dates)

        if base_freq:
            df = upsample_to_freq(df, base_freq, forward_fill=True)

    return df


def process_res_df(
    df: pl.DataFrame,
    ind: dict,
    trans_res: pl.DataFrame,
    dates: typing.Optional[pl.Series] = None,
) -> pl.DataFrame:
    """handle if a transformer returns multiple columns
    To manage this, we just add the name of column in a clean
    way, removing periods and lowercasing it.

    Parameters
    ----------
    df, dataframe, current dataframe
    ind, indicator object
    trans_res, result from the transformer function
    dates, optional date column the transformer ran against, used to align
        results that were calculated at another frequency

    Returns
    -------
    df, dataframe, updated dataframe with the new columns
    """
    columns = {}
    for key in trans_res.columns:
        i_name = ind.get("name")
        clean_key = key.lower()
        clean_key = clean_key.replace(".", "")
        clean_key = clean_key.replace(" ", "_")
        # include the name of the transformer in the key
        df_key = f"{i_name}_{ind.get('transformer')}_{clean_key}"
        columns[df_key] = trans_res.get_column(key)

    return attach_transformer_columns(df, columns, dates)


def attach_transformer_columns(
    df: pl.DataFrame,
    columns: typing.Dict[str, pl.Series],
    dates: typing.Optional[pl.Series] = None,
) -> pl.DataFrame:
    """Adds transformer results to the dataframe.

    Polars has no index to align on, so results computed at the base frequency
    are concatenated by position, and results computed at another frequency are
    joined back on their own dates.
    """
    if dates is None or (
        len(dates) == df.height and dates.equals(df.get_column(DATE_COL))
    ):
        if any(len(series) != df.height for series in columns.values()):
            raise ValueError(
                "Transformer result length does not match the dataframe; "
                "pass the dates the transformer ran against to align them."
            )
        return df.with_columns(
            [series.alias(name) for name, series in columns.items()]
        )

    aligned = pl.DataFrame(
        {DATE_COL: dates, **{name: series for name, series in columns.items()}}
    )

    return df.drop([c for c in columns if c in df.columns]).join(
        aligned, on=DATE_COL, how="left"
    ).sort(DATE_COL)


def parse_date_bound(
    value: typing.Any, upper: bool = False
) -> typing.Optional[datetime.datetime]:
    """Turns a backtest start/stop value into a datetime to filter the date column on.

    Accepts datetimes, epoch seconds/milliseconds and date strings. Partial
    date strings behave like pandas label slicing: as an upper bound
    "2020-08-31" covers the whole day.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime.datetime):
        return value

    if isinstance(value, datetime.date):
        start = datetime.datetime(value.year, value.month, value.day)
        return _end_of_day(start) if upper else start

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _from_epoch(value)

    text = str(value).strip()
    if not text:
        return None

    if detect_time_unit(text):
        return _from_epoch(int(text))

    partial = _PARTIAL_DATE.match(text)
    if partial:
        year, month, day = partial.groups()
        return _partial_date_bound(int(year), month, day, upper)

    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        pass

    for fmt in _FALLBACK_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: {value!r}")


def _from_epoch(value: typing.Union[int, float]) -> datetime.datetime:
    unit = detect_time_unit(int(value)) or "s"
    divisor = 1000 if unit == "ms" else 1

    return datetime.datetime.fromtimestamp(
        float(value) / divisor, tz=datetime.timezone.utc
    ).replace(tzinfo=None)


def _end_of_day(start: datetime.datetime) -> datetime.datetime:
    return start + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)


def _partial_date_bound(
    year: int, month: typing.Optional[str], day: typing.Optional[str], upper: bool
) -> datetime.datetime:
    start = datetime.datetime(year, int(month) if month else 1, int(day) if day else 1)

    if not upper:
        return start

    if day:
        return _end_of_day(start)
    if month:
        next_month = (
            datetime.datetime(year + 1, 1, 1)
            if int(month) == 12
            else datetime.datetime(year, int(month) + 1, 1)
        )
        return next_month - datetime.timedelta(microseconds=1)

    return datetime.datetime(year + 1, 1, 1) - datetime.timedelta(microseconds=1)


def standardize_df(df: pl.DataFrame) -> pl.DataFrame:
    """Standardizes a dataframe with the basic features used
    throughout the project.
    Parameters
    ----------
        df: A Polars dataframe (probably one just created) with
    at least the required columns of: date, open, close, high, low, volume.

    Returns
    -------
        A new Polars dataframe with a datetime "date" column, sorted ascending,
        deduplicated and with the OHLCV columns cast to floats.
    """
    if DATE_COL not in df.columns:
        raise Exception(_MISSING_DATE_MSG)

    new_df = ensure_date_column(df)
    new_df = new_df.sort(DATE_COL).unique(
        subset=[DATE_COL], keep="first", maintain_order=True
    )

    new_df = new_df.drop("ignore", strict=False)

    new_df = new_df.with_columns(
        [
            pl.col(col).cast(pl.Float64)
            for col in OHLCV_COLUMNS
            if col in new_df.columns
        ]
    )

    ordered = [DATE_COL]
    ordered.extend(col for col in OHLCV_COLUMNS if col in new_df.columns)
    ordered.extend(col for col in new_df.columns if col not in ordered)

    return new_df.select(ordered)
