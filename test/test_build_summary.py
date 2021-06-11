from numpy import median
import pandas as pd
from pandas._libs.tslibs import Timedelta

from fast_trade.build_summary import create_trade_log, summarize_time_held


def create_mock_trade_log():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_df.index = pd.to_datetime(mock_df.index, unit="s")

    mock_df["in_trade"] = [True, False, False, False, True, True, False, False, False]

    return mock_df


def test_create_trade_log_simple():
    mock_tl = create_mock_trade_log()

    mock_tl["adj_account_value_change"] = [
        100,
        110,
        100,
        115,
        125,
        125,
        130,
        125,
        135,
    ]

    trade_log_df = create_trade_log(mock_tl)

    assert list(trade_log_df.in_trade) == [True, False, True, False]


def test_summarize_time_held():
    trade_log_df = create_mock_trade_log()

    [
        mean_trade_time_held,
        max_trade_time_held,
        min_trade_time_held,
        median_time_held,
    ] = summarize_time_held(trade_log_df)

    assert mean_trade_time_held.total_seconds() == 59.875
    assert max_trade_time_held.total_seconds() == 60
    assert min_trade_time_held.total_seconds() == 59.0
    assert median_time_held.total_seconds() == 60


def test_summarize_trade_perc():
    mock_tl = create_mock_trade_log()
