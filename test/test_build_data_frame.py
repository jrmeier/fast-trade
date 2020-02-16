import pytest
import pandas as pd
from pandas.core import series
from finta import TA
import os
from fast_trade.build_data_frame import (
    determine_chart_period,
    build_data_frame,
    indicator_map,
)


# def test_determine_chart_period_min():
#     mock_time_str = "10m"
#     res = determine_chart_period(mock_time_str)

#     assert res == 10


# def test_determine_chart_period_hour():
#     mock_time_str = "3h"
#     res = determine_chart_period(mock_time_str)

#     assert res == 180


# def test_determine_chart_period_day():
#     mock_time_str = "3d"
#     res = determine_chart_period(mock_time_str)

#     assert res == 4320


# def test_determine_chart_period_int():
#     mock_time_str = "77"
#     res = determine_chart_period(mock_time_str)

#     assert res == 77


# def test_build_data_frame_no_csv():
#     mock_csv_path = "./ohlcv.csv"
#     with pytest.raises(Exception) as excinfo:
#         build_data_frame(mock_csv_path, {})

#     assert "File doesn't exist: ./ohlcv.csv" == str(excinfo.value)


def test_build_data_frame_no_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"

    res = build_data_frame(mock_csv_path, {"indicators": []})
    assert isinstance(res, type(pd.DataFrame()))
    assert len(res.values) == 9
    assert list(res.columns) == ["date", "close", "open", "high", "low", "volume"]


def test_build_data_frame_with_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_strat = {
        "indicators": [
            {"name": "short", "func": "ta.ema", "timeperiod": "1m", "df": "close"}
        ]
    }

    res = build_data_frame(mock_csv_path, mock_strat)
    print(res)

    assert "short" in list(res.columns)
    assert list(list(res.values)[4]) == list(
        [1523938023.0, 0.02247, 0.01, 0.025, 0.01, 119548.0, 0.01945766]
    )


def test_build_data_frame_with_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_strat = {
        "indicators": [
            {"name": "short", "func": "ta.ema", "timeperiod": "1m", "df": "close"}
        ]
    }

    res = build_data_frame(mock_csv_path, mock_strat)

    assert "short" in list(res.columns)
    assert list(list(res.values)[4]) == list(
        [1523938023.0, 0.02247, 0.01, 0.025, 0.01, 119548.0, 0.01945766]
    )


def test_build_data_frame_with_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_strat = {
        "indicators": [
            {"name": "short", "func": "ta.ema", "timeperiod": "1m", "df": "close"},
            {"name": "mid", "func": "ta.ema", "timeperiod": "2m", "df": "close"},
        ],
    }

    res = build_data_frame(mock_csv_path, mock_strat)

    assert "short" in list(res.columns)
    assert "mid" in list(res.columns)


def test_indicator_map():
    """ makes sure the functions are mapped correctly"""
    for func_name in indicator_map:
        method_name = func_name.split(".").pop().upper()

        assert indicator_map[func_name].__name__ == method_name


def test_build_data_frame_timerange():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_strat = {
        "indicators": [
            {"name": "short", "func": "ta.ema", "timeperiod": "1m", "df": "close"}
        ]
    }

    timerange = {"start": "2018-04-17 04:04:04", "stop": "2018-04-17 04:06:30"}

    df = build_data_frame(mock_csv_path, mock_strat, timerange)

    assert str(df.index.values[0]) == "2018-04-17T04:04:04.000000000"
    assert str(df.index.values[1]) == "2018-04-17T04:05:03.000000000"
    assert str(df.index.values[2]) == "2018-04-17T04:06:03.000000000"


def test_build_data_frame_timerange_not_set():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_strat = {
        "indicators": [
            {"name": "short", "func": "ta.ema", "timeperiod": "1m", "df": "close"}
        ]
    }

    df = build_data_frame(mock_csv_path, mock_strat)

    assert str(df.index.values[0]) == "2018-04-17T04:03:04.000000000"
    assert str(df.index.values[1]) == "2018-04-17T04:04:04.000000000"
    assert str(df.index.values[2]) == "2018-04-17T04:05:03.000000000"
    assert str(df.index.values[3]) == "2018-04-17T04:06:03.000000000"
