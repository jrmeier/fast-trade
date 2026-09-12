import typing

import polars as pl

from .utils import DATE_COL, date_series, freq_to_polars, infer_frequency


def calculate_perc_missing(
    df: pl.DataFrame, freq: typing.Optional[str] = None
) -> list:
    """
    Calculate the percentage and total count of missing entries
    in a DataFrame based on its date column.

    Parameters:
    - df (pl.DataFrame): The input DataFrame with a datetime "date" column.
    - freq (str): Optional frequency to measure against, inferred when omitted.

    Returns:
    - list: [percentage_missing (float), total_missing (int)]
    """
    # Handle empty DataFrame
    if df is None or df.is_empty():
        raise ValueError("DataFrame is empty")

    if DATE_COL not in df.columns:
        raise ValueError(f"DataFrame does not have a '{DATE_COL}' column")

    dates = date_series(df, DATE_COL)

    # Default to minutes when the frequency cannot be inferred from the dates
    freq = freq or infer_frequency(df) or "1Min"

    # Get the full range of expected dates
    expected = pl.datetime_range(
        dates.min(), dates.max(), interval=freq_to_polars(freq), eager=True
    )

    total_possible = len(expected)
    total_actual = df.height

    total_missing = total_possible - total_actual

    # Calculate percentage
    perc_missing = (total_missing / total_possible) * 100 if total_possible > 0 else 0.0
    perc_missing = round(perc_missing, 2)

    return [perc_missing, 0 if total_missing < 0 else total_missing]
