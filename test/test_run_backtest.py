from fast_trade import take_action, determine_action
from collections import namedtuple
import pandas as pd


def test_take_action_greater_than():
    mock_strategy = [["close", ">", "short"]]
    mock_columns = ["date", "close", "open", "high", "low", "volume", "short"]
    mock_df = pd.DataFrame(
        data={
            "date": 1523937963,
            "close": 0.0212,
            "open": 0.01,
            "high": 0.025,
            "low": 0.01,
            "volume": 36898,
            "short": 0.0112,
        },
        columns=mock_columns,
        index=[0],
    ).set_index("date")

    res = take_action(mock_df, mock_strategy)
    assert res == True


def test_take_action_less_than():
    mock_strategy = [["close", "<", "short"]]
    mock_row = [1523937963, 0.0212, 0.01, 0.025, 0.01, 36898, 0.0112]
    mock_columns = ["date", "close", "open", "high", "low", "volume", "short"]

    mock_df = pd.DataFrame(
        data={
            "date": 1523937963,
            "close": 0.0212,
            "open": 0.01,
            "high": 0.025,
            "low": 0.01,
            "volume": 36898,
            "short": 0.0112,
        },
        columns=mock_columns,
        index=[0],
    ).set_index("date")

    res = take_action(mock_df, mock_strategy)
    assert res == False


def test_take_action_equal():
    mock_strategy = [["close", "=", 0.0212]]
    mock_columns = ["date", "close", "open", "high", "low", "volume", "short"]

    mock_df = pd.DataFrame(
        data={
            "date": 1523937963,
            "close": 0.0212,
            "open": 0.01,
            "high": 0.025,
            "low": 0.01,
            "volume": 36898,
            "short": 0.0112,
        },
        columns=mock_columns,
        index=[0],
    ).set_index("date")

    print(mock_df)
    res = take_action(mock_df, mock_strategy)
    assert res == True
