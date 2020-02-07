import pytest
import pandas as pd
from pandas.core import series

import os
from fast_trade.build_data_frame import (
    determine_timeperiod,
    build_data_frame
)



def test_determine_timeperiod_min():
    mock_time_str = "10m"
    res = determine_timeperiod(mock_time_str)

    assert res == 10

def test_determine_timeperiod_hour():
    mock_time_str = "3h"
    res = determine_timeperiod(mock_time_str)

    assert res == 180

def test_determine_timeperiod_day():
    mock_time_str = "3d"
    res = determine_timeperiod(mock_time_str)

    assert res == 4320

def test_determine_timeperiod_int():
    mock_time_str = "77"
    res = determine_timeperiod(mock_time_str)

    assert res == 77


def test_build_data_frame_no_csv():
    mock_csv_path = "./ohlcv.csv"
    with pytest.raises(Exception) as excinfo:
        build_data_frame(mock_csv_path)

    assert "File doesn't exist: ./ohlcv.csv" == str(excinfo.value)

def test_build_data_frame_no_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"


    res = build_data_frame(mock_csv_path)
    assert isinstance(res, type(pd.DataFrame()))
    assert len(res.values) == 9
    assert list(res.columns) == ['date','close','open','high','low','volume']

def test_build_data_frame_with_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_indicators = [
        {
            "name": "short",
            "func": "ta.ema",
            "timeperiod": "1m",
            "df": "close"
        }
    ]
    
    res = build_data_frame(mock_csv_path, mock_indicators)

    assert "short" in list(res.columns)
    assert list(list(res.values)[4]) == list([1523938023.0,0.02247,0.01,0.025,0.01,119548.0, 0.02247])

def test_build_data_frame_with_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_indicators = [
        {
            "name": "short",
            "func": "ta.ema",
            "timeperiod": "1m",
            "df": "close"
        }
    ]
    
    res = build_data_frame(mock_csv_path, mock_indicators)

    assert "short" in list(res.columns)
    assert list(list(res.values)[4]) == list([1523938023.0,0.02247,0.01,0.025,0.01,119548.0, 0.02247])


def test_build_data_frame_with_indicators():
    this_path = os.path.abspath(__file__).split("/")
    this_path.pop()

    this_path = "/".join(this_path)
    mock_csv_path = f"{this_path}/ohlcv_data.csv.txt"
    mock_indicators = [
        {
            "name": "short",
            "func": "ta.ema",
            "timeperiod": "1m",
            "df": "close"
        },
        {
            "name": "mid",
            "func": "ta.ema",
            "timeperiod": "2m",
            "df": "close"
        }
    ]
    
    res = build_data_frame(mock_csv_path, mock_indicators)

    assert "short" in list(res.columns)
    assert "mid" in list(res.columns)
