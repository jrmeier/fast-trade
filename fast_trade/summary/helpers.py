"""Small numeric and run-length helpers shared by the summary metrics."""

from __future__ import annotations

import math
from typing import Any, Optional

import polars as pl

# Metric helpers degrade to a neutral value instead of failing a backtest, so
# they catch anything a malformed frame can throw at an aggregation.
NUMERIC_ERRORS = (
    ArithmeticError,
    AttributeError,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
    pl.exceptions.PolarsError,
)


def clean_float(value: Any, ndigits: Optional[int] = None) -> float:
    """Coerce ``value`` to a float, mapping missing values to 0.0."""
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number):
        return 0.0
    if ndigits is None:
        return number
    return float(round(number, ndigits))


def finite(series: pl.Series) -> pl.Series:
    """Drop nulls and NaNs so aggregations skip missing values."""
    series = series.drop_nulls()
    if series.dtype.is_float():
        series = series.filter(series.is_not_nan())
    return series


def run_ids(values: pl.Series) -> pl.Series:
    """Label each contiguous run of equal values with an increasing id."""
    return (values != values.shift()).fill_null(True).cum_sum()


def run_lengths(flags: pl.Series) -> pl.Series:
    """Lengths of the contiguous runs where ``flags`` is true."""
    flags = flags.fill_null(False).cast(pl.Boolean)
    runs = pl.DataFrame({"run": run_ids(flags), "flag": flags}).filter(pl.col("flag"))
    if runs.is_empty():
        return pl.Series("len", [], dtype=pl.UInt32)
    return runs.group_by("run").len()["len"]


def replace_non_finite(df: pl.DataFrame) -> pl.DataFrame:
    """Null out infinities and NaNs in float columns."""
    float_columns = [name for name, dtype in df.schema.items() if dtype.is_float()]
    if not float_columns:
        return df
    return df.with_columns(
        [
            pl.when(pl.col(name).is_infinite() | pl.col(name).is_nan())
            .then(None)
            .otherwise(pl.col(name))
            .alias(name)
            for name in float_columns
        ]
    )
