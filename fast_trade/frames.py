"""Polars frame helpers shared across fast-trade.

Frames are ``pl.DataFrame`` with an explicit ``date`` column holding datetimes;
there is no index.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Optional

import polars as pl

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
    """Return ``frame`` as a ``pl.DataFrame``."""
    if frame is None:
        return pl.DataFrame()
    if isinstance(frame, pl.DataFrame):
        return frame
    if isinstance(frame, pl.LazyFrame):
        return frame.collect()
    if isinstance(frame, dict):
        return pl.DataFrame(frame)
    raise TypeError(
        f"Expected a Polars DataFrame/LazyFrame or dict, got {type(frame).__name__}"
    )


def is_empty(frame: Any) -> bool:
    """True when ``frame`` is missing or holds no rows."""
    if frame is None:
        return True
    if isinstance(frame, pl.DataFrame):
        return frame.is_empty()
    if isinstance(frame, pl.LazyFrame):
        return frame.limit(1).collect().is_empty()
    try:
        return len(frame) == 0
    except TypeError:
        return False


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


def freq_to_timedelta(freq: Optional[str]) -> datetime.timedelta:
    """Convert a pandas-style frequency to a ``datetime.timedelta``.

    Calendar units are approximated, which is enough for scheduling and for
    padding a start date by a number of periods.
    """
    count, unit = parse_freq(freq)
    return datetime.timedelta(seconds=count * _UNIT_SECONDS[unit])
