"""Polars frame helpers shared across fast-trade.

Frames are ``pl.DataFrame`` with an explicit ``date`` column holding datetimes;
there is no index. ``to_polars`` additionally accepts frames handed over by
producers that have not been ported yet, so that branch can be dropped once
everything upstream emits Polars.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Optional

import polars as pl

_INDEX_COLUMNS = ("index", "__index_level_0__", "level_0")

_UNIT_ALIASES = {
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
    "y": "y",
    "a": "y",
    "year": "y",
    "years": "y",
}

# Month/year aliases that pandas spells with capitals, where a lowercase match
# would mean something else ("M" is a month, "m" is a minute).
_CALENDAR_UNITS = {"M": "mo", "ME": "mo", "MS": "mo", "Y": "y", "YE": "y", "A": "y"}

_UNIT_SECONDS = {
    "ns": 1e-9,
    "us": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
    "mo": 2592000.0,
    "y": 31536000.0,
}


def to_polars(frame: Any) -> pl.DataFrame:
    """Return ``frame`` as a ``pl.DataFrame`` with a ``date`` column when possible."""
    if frame is None:
        return pl.DataFrame()
    if isinstance(frame, pl.DataFrame):
        return frame
    if isinstance(frame, pl.LazyFrame):
        return frame.collect()
    if isinstance(frame, dict):
        return pl.DataFrame(frame)

    # Producers that still hand over pandas frames keep the dates on the index.
    if hasattr(frame, "reset_index") and hasattr(frame, "columns"):
        frame = frame.reset_index()
    return _normalize_date_column(pl.from_pandas(frame))


def _normalize_date_column(df: pl.DataFrame) -> pl.DataFrame:
    if "date" in df.columns or df.is_empty():
        return df
    for name in _INDEX_COLUMNS:
        if name in df.columns and df.schema[name] in (pl.Date, pl.Datetime):
            return df.rename({name: "date"})
    return df


def is_empty(frame: Any) -> bool:
    """True when ``frame`` is missing or holds no rows."""
    if frame is None:
        return True
    if isinstance(frame, pl.DataFrame):
        return frame.is_empty()
    if isinstance(frame, pl.LazyFrame):
        return frame.limit(1).collect().is_empty()
    empty = getattr(frame, "empty", None)
    if empty is not None:
        return bool(empty)
    try:
        return len(frame) == 0
    except TypeError:
        return False


def has_column(frame: Any, column: str) -> bool:
    columns = getattr(frame, "columns", ())
    return column in columns


def sort_by_date(df: pl.DataFrame) -> pl.DataFrame:
    if "date" in df.columns:
        return df.sort("date")
    return df


def parse_freq(freq: Optional[str]) -> tuple:
    """Split a pandas-style frequency such as ``1Min`` into ``(count, unit)``."""
    if freq is None:
        return 1, "m"
    if isinstance(freq, datetime.timedelta):
        return int(freq.total_seconds()), "s"

    text = str(freq).strip()
    match = re.fullmatch(r"(\d*\.?\d*)\s*([A-Za-z]*)", text)
    if not match:
        raise ValueError(f"Unable to parse frequency: {freq!r}")

    count_text, unit_text = match.groups()
    count = float(count_text) if count_text else 1.0
    if unit_text in _CALENDAR_UNITS:
        unit = _CALENDAR_UNITS[unit_text]
    else:
        unit = _UNIT_ALIASES.get(unit_text.lower())
    if unit is None:
        raise ValueError(f"Unable to parse frequency: {freq!r}")
    return int(count) if count.is_integer() else count, unit


def freq_to_polars(freq: Optional[str]) -> str:
    """Convert a pandas-style frequency to a Polars duration string."""
    count, unit = parse_freq(freq)
    return f"{count}{unit}"


def freq_to_timedelta(freq: Optional[str]) -> datetime.timedelta:
    """Convert a pandas-style frequency to a ``datetime.timedelta``.

    Calendar units are approximated, which is enough for scheduling and for
    padding a start date by a number of periods.
    """
    count, unit = parse_freq(freq)
    return datetime.timedelta(seconds=count * _UNIT_SECONDS[unit])


def write_parquet(df: pl.DataFrame, path: str) -> None:
    """Write ``df`` to ``path`` via a temporary file so readers never see a partial write."""
    import os

    tmp_path = f"{path}.tmp"
    to_polars(df).write_parquet(tmp_path)
    os.replace(tmp_path, path)
