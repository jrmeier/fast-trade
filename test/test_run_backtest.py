from fast_trade import take_action, determine_action
from collections import namedtuple
import pandas as pd


def test_take_action_greater_than():
    mock_backtest = [["close", ">", "short"]]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    res = take_action(mock_row, mock_backtest, max_last_frames=0, last_frames=[])
    assert res is True


def test_take_action_less_than():
    mock_backtest = [["close", "<", "short"]]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    res = take_action(mock_row, mock_backtest, max_last_frames=0, last_frames=[])
    assert res is False


def test_take_action_equal():
    mock_backtest = [["close", "=", 0.0212]]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    res = take_action(mock_row, mock_backtest, max_last_frames=0, last_frames=[])
    assert res is True
