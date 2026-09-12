import datetime

import polars as pl
import pytest

from fast_trade.calculate_perc_missing import calculate_perc_missing


def _frame(dates):
    return pl.DataFrame({"date": dates, "close": [0] * len(dates)})


def _date_range(start, periods, freq="1m"):
    return pl.datetime_range(
        start,
        start + datetime.timedelta(days=30),
        interval=freq,
        eager=True,
    ).head(periods)


def test_calculate_perc_missing_none_missing():
    # generate a list of dates from the first to the last date in the dataframe
    today = datetime.datetime.now()
    last_week = today - datetime.timedelta(days=7)
    mock_dates = pl.datetime_range(last_week, today, interval="1m", eager=True)
    mock_df = _frame(mock_dates)

    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)

    assert perc_missinng == 0.0
    assert total_missing == 0.0


def test_calculate_perc_missing_some_missing():
    start = datetime.datetime.now().replace(
        second=0, microsecond=0, hour=12, minute=0
    ) - datetime.timedelta(hours=1)
    mock_dates = _date_range(start, 10)
    # remove 2 dates from the middle of the range
    kept = list(mock_dates[:5]) + list(mock_dates[7:])
    mock_df = _frame(kept)

    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)

    assert perc_missinng == 20
    assert total_missing == 2


def test_calculate_perc_missing_empty_df():
    with pytest.raises(ValueError, match="empty"):
        calculate_perc_missing(pl.DataFrame())


def test_calculate_perc_missing_no_date_column():
    mock_df = pl.DataFrame({"close": [1, 2, 3, 4, 5]})
    with pytest.raises(ValueError, match="date"):
        calculate_perc_missing(mock_df)


def test_calculate_perc_missing_non_datetime_date_column():
    mock_df = pl.DataFrame({"date": ["a", "b"], "close": [1, 2]})
    with pytest.raises(ValueError, match="not a datetime"):
        calculate_perc_missing(mock_df)


def test_calculate_perc_missing_some_with_different_freq():
    start = datetime.datetime.now().replace(
        second=0, microsecond=0, hour=12, minute=0
    ) - datetime.timedelta(hours=1)
    # 10 bars at 10 minute spacing, expanded onto the minute grid they cover
    mock_dates = _date_range(start, 91)
    kept = list(mock_dates[:5]) + list(mock_dates[7:])
    mock_df = _frame(kept)

    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)

    assert perc_missinng == 2.2
    assert total_missing == 2


def test_calculate_perc_missing_explicit_freq():
    start = datetime.datetime(2024, 1, 1)
    mock_dates = [start + datetime.timedelta(minutes=10 * i) for i in range(10)]
    mock_df = _frame(mock_dates)

    # measured against its own frequency nothing is missing
    assert calculate_perc_missing(mock_df) == [0.0, 0]
    # measured against minutes, only every tenth bar is present
    assert calculate_perc_missing(mock_df, freq="1Min") == [89.01, 81]


def test_calculate_perc_missing_never_returns_negative():
    start = datetime.datetime(2024, 1, 1)
    mock_dates = [start + datetime.timedelta(seconds=30 * i) for i in range(5)]
    mock_df = _frame(mock_dates)

    [perc_missing, total_missing] = calculate_perc_missing(mock_df, freq="1Min")

    # 5 rows inside a 3 minute range: more bars than expected, never negative
    assert total_missing == 0
    assert perc_missing == 0.0
