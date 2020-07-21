import pytest
import pandas as pd
import random
from fast_trade import enter_trade, exit_trade, analyze_df


def test_enter_trade_1():
    mock_close = 10
    mock_aux_balance = 100
    res = enter_trade(mock_close, mock_aux_balance)

    assert res == 10


def test_enter_trade_2():
    mock_close = 0.025
    mock_aux_balance = 60

    res = enter_trade(mock_close, mock_aux_balance)
    assert res == 2400.0


def test_enter_trade_3():
    mock_close = 0.3123
    mock_aux_balance = 212.2333

    res = enter_trade(mock_close, mock_aux_balance)
    assert res == 679.58149215


def test_enter_trade_4():
    mock_close = 0.3123
    mock_aux_balance = 0

    res = enter_trade(mock_close, mock_aux_balance)
    assert res == 0


def test_exit_trade_1():
    mock_close = 0.99992
    mock_base_balance = 133.22

    aux = exit_trade(mock_close, mock_base_balance)

    assert aux == 133.2093424

def test_exit_trade_2():
    mock_close = 0.99992
    mock_base_balance = 0

    aux = exit_trade(mock_close, mock_base_balance)

    assert aux == 0.0



def test_analyze_df_1():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")

    mock_strategy = {
        "base_balance": 1000,
        "exit_on_end": True
    }

    mock_df['actions'] = ["e","h","x","x","x","e","x","h","h"]
    
    aux_log, base_log, smooth_base = analyze_df(mock_df, mock_strategy)

    assert aux_log == [100000.0, 100000.0, 0, 0, 0, 103237.41007194, 0, 0, 0]
    assert base_log == [0, 0, 2296.0, 2296.0, 2296.0, 0, 2274.32014388, 2274.32014388, 2274.32014388]
    assert smooth_base == [1000.0, 1000.0, 2296.0, 2296.0, 2296.0, 2296.0, 2274.32014388, 2274.32014388, 2274.32014388]


def test_analyze_df_2():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt")

    mock_strategy = {
        "base_balance": 1000,
        "exit_on_end": True
    }
    mock_df['actions'] = ["e","h","h","x","h","h","e","h","h"]

    aux_log, base_log, smooth_base = analyze_df(mock_df, mock_strategy)

    assert aux_log == [100000.0, 100000.0, 100000.0, 0, 0, 0, 96232.41034952, 96232.41034952, 96232.41034952, 0]
    assert base_log == [0, 0, 0, 2120.0, 2120.0, 2120.0, 0, 0, 0, 2065.1475261]
    assert smooth_base == [1000.0, 1000.0, 1000.0, 2120.0, 2120.0, 2120.0, 2120.0, 2120.0, 2120.0, 2065.1475261]
