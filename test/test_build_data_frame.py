import pytest
import pandas as pd
import datetime
from fast_trade.build_data_frame import detect_time_unit, determine_chart_period, load_basic_df_from_csv, apply_indicators_to_dataframe, apply_charting_to_df
from unittest import mock, TestCase


def test_detect_time_unit_s():
    mock_timestring = 1595115901734
    result = detect_time_unit(mock_timestring)

    assert result == "ms"

def test_detect_time_unit_ms():
    mock_timestring = 1595115901
    result = detect_time_unit(mock_timestring)

    assert result == "s"

def test_determine_chart_period_1_num():
    mock_chart_period = 1
    result = determine_chart_period(mock_chart_period)

    assert result == 1

def test_determine_chart_period_multi_num_1():
    mock_chart_period = 10
    result = determine_chart_period(mock_chart_period)

    assert result == 10

def test_determine_chart_period_multi_num_2():
    mock_chart_period = 14
    result = determine_chart_period(mock_chart_period)

    assert result == 14

def test_determine_chart_period_1_min_str_1():
    mock_chart_period = "1m"
    result = determine_chart_period(mock_chart_period)

    assert result == 1

def test_determine_chart_period_15_min_str_1():
    mock_chart_period = "15m"
    result = determine_chart_period(mock_chart_period)

    assert result == 15

def test_determine_chart_period_1_hour_str_1():
    mock_chart_period = "1h"
    result = determine_chart_period(mock_chart_period)

    assert result == 60

def test_determine_chart_period_4_hour_str_2():
    mock_chart_period = "4h"
    result = determine_chart_period(mock_chart_period)

    assert result == 240

def test_determine_chart_period_1_day_str_1():
    mock_chart_period = "1d"
    result = determine_chart_period(mock_chart_period)

    assert result == 1440

def test_determine_chart_period_5_day_str_1():
    mock_chart_period = "5d"
    result = determine_chart_period(mock_chart_period)

    assert result == 7200


def test_load_basic_df_from_csv_str_1():
    mock_ohlcv_path = "./test/ohlcv_data.csv.txt"

    result_df = load_basic_df_from_csv(mock_ohlcv_path)
    header = list(result_df.head())

    assert "close" in header
    assert "open" in header
    assert "high" in header
    assert "low" in header
    assert "volume" in header

    assert result_df.index.name == "date"

def test_load_basic_df_from_csv_list_1():
    mock_ohlcv_path = [ 
        "./test/ohlcv_data.csv.txt",
        "./test/extra_data.txt"
    ]

    result_df = load_basic_df_from_csv(mock_ohlcv_path)

    header = list(result_df.head())
    
    assert "close" in header
    assert "open" in header
    assert "high" in header
    assert "low" in header
    assert "volume" in header
    assert "extra_column_1" in header

    assert "date" in result_df.index.name

    expected_line = [0.01404, 0.01, 0.025, 0.01, 3117.0, 10.0]

    assert list(result_df.iloc[1]) == expected_line

def test_load_basic_df_from_csv_str_error_1():
    mock_ohlcv_path = "./test/SomeFakeNews.csv.txt"

    with pytest.raises(Exception, match=r"File not found:*"):
        load_basic_df_from_csv(mock_ohlcv_path)

def test_load_basic_df_from_csv_list_error_1():
    mock_ohlcv_path = [
        "./test/ohlcv_data.csv.txt",
        "./test/literally_fake_news.csv",
    ]

    with pytest.raises(Exception, match=r"File not found:*"):
        load_basic_df_from_csv(mock_ohlcv_path)

def test_apply_indicators_to_dataframe_1_ind():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")
    mock_indicators = [
        {
            "func": "ta.sma",
            "name": "example_indicator_name",
            "args": [3]
        }
    ]

    result_df = apply_indicators_to_dataframe(mock_df, mock_indicators)

    header = list(result_df.head())

    assert "example_indicator_name" in header
    assert "FAKE_indicator_name" not in header

    assert result_df.index.name == None

def test_apply_indicators_to_dataframe_multi_ind():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")
    mock_indicators = [
        {
            "func": "ta.sma",
            "name": "sma",
            "args": [19]
        },
        {
            "func": "ta.rsi",
            "name": "rsi",
            "args": []
        },
        {
            "func": "ta.uo",
            "name": "uo",
            "args": []
        }
    ]

    result_df = apply_indicators_to_dataframe(mock_df, mock_indicators)

    header = list(result_df.head())

    assert "rsi" in header
    assert "sma" in header
    assert "uo" in header

    assert result_df.index.name == None


def test_apply_charting_to_df_1():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")
    mock_df.set_index(["date"], inplace=True)
    mock_chart_period = 2
    mock_start_time = "2018-04-17 04:00:00"
    mock_stop_time = ""

    result_df = apply_charting_to_df(mock_df, mock_chart_period, mock_start_time, mock_stop_time)

    assert (result_df.iloc[2].name - result_df.iloc[1].name).total_seconds() == 120
    assert (result_df.iloc[4].name - result_df.iloc[1].name).total_seconds() == 360

def test_apply_charting_to_df_2():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")
    mock_df.set_index(["date"], inplace=True)
    mock_chart_period = 1
    mock_start_time = "2018-04-17 04:00:00"
    mock_stop_time = "2018-04-17 04:10:00"

    past_stop_time = datetime.datetime.strptime("2018-04-17 04:11:00", "%Y-%m-%d %H:%M:%S")    
    result_df = apply_charting_to_df(mock_df, mock_chart_period, mock_start_time, mock_stop_time)

    assert result_df.iloc[-1].name < past_stop_time

def test_apply_charting_to_df_2():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")
    mock_df.set_index(["date"], inplace=True)
    mock_chart_period = 1
    mock_start_time = ""
    mock_stop_time = "2018-04-17 04:10:00"

    past_stop_time = "2018-04-17 04:11:00"

    result_df = apply_charting_to_df(mock_df, mock_chart_period, mock_start_time, mock_stop_time)


    past_stop_time = datetime.datetime.strptime("2018-04-17 04:11:00", "%Y-%m-%d %H:%M:%S")    
    result_df = apply_charting_to_df(mock_df, mock_chart_period, mock_start_time, mock_stop_time)

    assert result_df.iloc[-1].name < past_stop_time

def test_apply_to_charting_to_df_3():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")
    mock_df.set_index(["date"], inplace=True)

    mock_chart_period = 1
    mock_start_time = "2018-04-17 04:03:00"
    mock_stop_time = "2018-04-17 04:10:00"

    result_df = apply_charting_to_df(mock_df, mock_chart_period, mock_start_time, mock_stop_time)

    past_stop_time = datetime.datetime.strptime("2018-04-17 04:11:00", "%Y-%m-%d %H:%M:%S")    
    result_df = apply_charting_to_df(mock_df, mock_chart_period, mock_start_time, mock_stop_time)

    assert result_df.iloc[-1].name < past_stop_time
