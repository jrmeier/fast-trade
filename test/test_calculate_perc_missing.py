import datetime
import numpy as np
import pandas as pd
import pytest
from fast_trade.calculate_perc_missing import calculate_perc_missing
import random


def test_calculate_perc_missing_none_missing():
    # generate a list of dates from the first to the last date in the dataframe
    today = datetime.datetime.now()
    last_week = today - datetime.timedelta(days=7)
    mock_dates = pd.date_range(start=last_week, end=today, freq="1Min")
    mock_df = pd.DataFrame(index=mock_dates)
    mock_df["close"] = 0
    mock_df = mock_df.asfreq("1Min")
    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)

    assert perc_missinng == 0.0
    assert total_missing == 0.0


def test_calculate_perc_missing_some_missing():
    today = datetime.datetime.now().replace(second=0, microsecond=0, hour=12, minute=0)
    last_week = today - datetime.timedelta(hours=1)
    mock_dates = pd.date_range(start=last_week, freq="1Min", periods=10)
    mock_df = pd.DataFrame(index=mock_dates)
    mock_df = mock_df.asfreq("1Min")

    # remove 2 dates from the list
    mock_df = mock_df.drop(mock_df.index[-5])
    mock_df = mock_df.drop(mock_df.index[-5])
    mock_df["close"] = 0

    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)

    assert perc_missinng == 20
    assert total_missing == 2


def test_calculate_perc_missing_empty_df():
    mock_df = pd.DataFrame()
    with pytest.raises(ValueError):
        calculate_perc_missing(mock_df)


def test_calculate_perc_missing_no_index():
    mock_df = pd.DataFrame({"close": [1, 2, 3, 4, 5]})
    with pytest.raises(ValueError):
        calculate_perc_missing(mock_df)


def test_calculate_perc_missing_some_with_different_freq():
    today = datetime.datetime.now().replace(second=0, microsecond=0, hour=12, minute=0)
    last_week = today - datetime.timedelta(hours=1)
    # freq = random.choice(["1Min", "5Min", "15Min", "30Min", "1H", "4H", "1D"])
    mock_dates = pd.date_range(start=last_week, freq="10Min", periods=10)
    # remove 2 dates from the list
    # mock_dates = mock_dates.drop(mock_dates[-5])
    # mock_dates = mock_dates.drop(mock_dates[-5])
    # mock_dates = mock_dates.drop(mock_dates[-5])
    mock_df = pd.DataFrame(index=mock_dates)
    mock_df = mock_df.asfreq("1Min")

    # remove 2 dates from the list
    mock_df = mock_df.drop(mock_df.index[-5])
    mock_df = mock_df.drop(mock_df.index[-5])
    mock_df["close"] = 0

    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)

    assert perc_missinng == 2.2
    assert total_missing == 2
