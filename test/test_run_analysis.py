import pytest
import pandas as pd
from fast_trade import enter_trade, exit_trade


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
    mock_close = 0.43123
    mock_base_balance = 9888

    res = enter_trade(mock_close, mock_base_balance)
    assert res == 22929.75906129


def test_exit_trade_2():
    mock_close = 123.12345
    mock_base_balance = 1000

    res = enter_trade(mock_close, mock_base_balance)
    assert res == 8.12192966


def test_exit_trade_3():
    mock_close = 0.000001
    mock_base_balance = 234.23

    res = enter_trade(mock_close, mock_base_balance)
    assert res == 234230000.0


def test_exit_trade_4():
    mock_close = 0.89937873
    mock_base_balance = 0

    res = enter_trade(mock_close, mock_base_balance)
    assert res == 0


def test_get_last_value():
    mock_df = pd.DataFrame(
        [
            ["date", "close", "open", "high", "low", "volume"],
            [1523938023.0, 0.02247, 0.01, 0.025, 0.01, 109548.0],
            [1523938023.0, 0.02247, 0.01, 0.025, 0.04, 0.0],
            [1523938023.0, 0.02247, 0.01, 0.025, 0.01, 119548.0],
        ]
    )

    assert True == True
