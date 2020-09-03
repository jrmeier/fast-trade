import pytest
import pandas as pd
import random
from fast_trade import convert_base_to_aux, convert_aux_to_base, analyze_df


def test_convert_base_to_aux_1():
    mock_close = 10
    mock_last_base = 100
    res = convert_base_to_aux(mock_last_base, mock_close)

    assert res == 10


def test_convert_base_to_aux_2():
    mock_close = 0.025
    mock_last_base = 60

    res = convert_base_to_aux(mock_last_base, mock_close)
    assert res == 2400.0


def test_convert_base_to_aux_3():
    mock_close = 0.3123
    mock_last_base = 212.2333

    res = convert_base_to_aux(mock_last_base, mock_close)
    assert res == 679.58149215


def test_convert_base_to_aux_4():
    mock_close = 0.3123
    mock_last_base = 0

    res = convert_base_to_aux(mock_last_base, mock_close)
    assert res == 0


def test_convert_base_to_aux_0s():
    mock_close = 0
    mock_last_base = 0

    res = convert_base_to_aux(mock_last_base, mock_close)
    assert res == 0


def test_convert_aux_to_base_1():
    mock_close = 0.99992
    mock_last_aux = 133.22

    aux = convert_aux_to_base(mock_last_aux, mock_close)

    assert aux == 133.2093424


def test_convert_aux_to_base_2():
    mock_close = 0.99992
    mock_base_balance = 0

    aux = convert_aux_to_base(mock_close, mock_base_balance)

    assert aux == 0.0


def test_analyze_df_1():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_df.index = pd.to_datetime(mock_df.index, unit="s")
    mock_strategy = {"base_balance": 1000, "exit_on_end": True, "commission": 0.00}

    mock_df["action"] = ["e", "h", "x", "x", "x", "e", "x", "h", "h"]

    df = analyze_df(mock_df, mock_strategy)

    print(df.action)
    assert list(df.aux.values) == [
        100000.0,
        100000.0,
        100000.0,
        100000.0,
        100000.0,
        103237.41007194,
        103237.41007172,
        103237.41007172,
        103237.41007172,
    ]
    assert list(df.base.values) == [
        0,
        0,
        2296.0,
        2296.0,
        2296.0,
        0,
        2274.32014388,
        2274.32014388,
        2274.32014388,
    ]
    assert list(df.total_value.values) == [
        1000.0,
        1000.0,
        2296.0,
        2296.0,
        2296.0,
        2296.0,
        2274.32014388,
        2274.32014388,
        2274.32014388,
    ]


def test_analyze_df_2():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_df.index = pd.to_datetime(mock_df.index, unit="s")

    mock_strategy = {"base_balance": 1000, "exit_on_end": True, "commission": 0.00}
    mock_df["action"] = ["e", "h", "h", "x", "h", "h", "e", "h", "h"]

    df = analyze_df(mock_df, mock_strategy)

    assert list(df.aux.values) == [
        100000.0,
        100000.0,
        100000.0,
        100000.0,
        100000.0,
        100000.0,
        96232.41034952,
        96232.41034952,
        96232.41034952,
        96232.41034949,
    ]
    assert list(df.base.values) == [
        0,
        0,
        0,
        2120.0,
        2120.0,
        2120.0,
        0,
        0,
        0,
        2065.1475261,
    ]
    assert list(df.total_value.values) == [
        1000.0,
        1000.0,
        1000.0,
        2120.0,
        2120.0,
        2120.0,
        2120.0,
        2120.0,
        2120.0,
        2120.0,
    ]
