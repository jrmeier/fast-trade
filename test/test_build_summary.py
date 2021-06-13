import datetime
from numpy import median, nan
import pandas as pd
from pandas._libs.tslibs import Timedelta

from fast_trade.build_summary import (
    build_summary,
    calculate_buy_and_hold_perc,
    calculate_return_perc,
    calculate_shape_ratio,
    create_trade_log,
    summarize_time_held,
    summarize_trade_perc,
    summarize_trades,
)


def create_mock_trade_log():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_df.index = pd.to_datetime(mock_df.index, unit="s")

    mock_df["in_trade"] = [True, False, False, False, True, True, False, False, False]
    mock_df["fee"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

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
    mock_tl["adj_account_value_change_perc"] = [
        0,
        0.1,
        0.4,
        0.20,
        -0.30,
        0.55,
        0.4,
        0.33,
        0.54,
    ]

    [
        max_trade_perc,
        min_trade_perc,
        mean_trade_perc,
        median_trade_perc,
    ] = summarize_trade_perc(mock_tl)

    assert max_trade_perc == round(mock_tl.adj_account_value_change_perc.max(), 4)
    assert min_trade_perc == round(mock_tl.adj_account_value_change_perc.min(), 4)

    assert median_trade_perc == round(mock_tl.adj_account_value_change_perc.median(), 4)
    assert mean_trade_perc == round(mock_tl.adj_account_value_change_perc.mean(), 4)


def test_summarize_trades():
    mock_total_trades = 100
    mock_tl = create_mock_trade_log()
    mock_tl["adj_account_value_change_perc"] = [
        0,
        0.1,
        0.4,
        0.20,
        -0.30,
        0.55,
        0.4,
        0.33,
        0.54,
    ]

    [total_trades, avg_trade_perc, avg_change] = summarize_trades(
        mock_tl, mock_total_trades
    )

    assert total_trades == 9

    assert avg_trade_perc == round(
        mock_tl.adj_account_value_change_perc.mean() * 100, 3
    )

    assert avg_change == 9


def test_summarize_trades_no_trades():
    mock_total_trades = 0
    mock_tl = create_mock_trade_log()
    mock_tl["adj_account_value_change_perc"] = [
        0,
        0.1,
        0.4,
        0.20,
        -0.30,
        0.55,
        0.4,
        0.33,
        0.54,
    ]

    [total_trades, avg_trade_perc, avg_change] = summarize_trades(
        mock_tl, mock_total_trades
    )

    assert total_trades == 9

    assert avg_trade_perc == round(
        mock_tl.adj_account_value_change_perc.mean() * 100, 3
    )

    assert avg_change == 0.0


def test_calculate_return_perc_simple():
    mock_tl = create_mock_trade_log()
    mock_tl["adj_account_value"] = [
        90,
        150,
        120,
        90,
        22,
        64,
        180,
        120,
        100,
    ]

    res = calculate_return_perc(mock_tl)

    assert res == 10


def test_calculate_return_perc_rounding():
    mock_tl = create_mock_trade_log()
    mock_tl["adj_account_value"] = [
        94,
        150,
        120,
        90,
        22,
        64,
        180,
        120,
        104,
    ]

    res = calculate_return_perc(mock_tl)

    assert res == 9.615


def test_calculate_return_perc_empty_tl():
    mock_tl = pd.DataFrame()

    res = calculate_return_perc(mock_tl)

    assert res == 0.0


def test_calculate_buy_and_hold_perc():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )

    mock_df.close = [1, 3, 12, 13, 14, 15, 16, 17, 10]

    res = calculate_buy_and_hold_perc(mock_df)

    assert res == 90.0


def test_calculate_sharpe_ratio():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_df["adj_account_value_change_perc"] = [1, 2, 4, 7, 7, 6, 6, 5, 6]

    res = calculate_shape_ratio(mock_df)
    assert res == 6.83


# TODO: build more of these
def test_build_summary():
    mock_df = create_mock_trade_log()
    mock_df.close = [10, 11, 11, 9, 9, 10, 11, 90, 11]

    mock_df["account_value"] = [90, 110, 110, 90, 90, 100, 110, 90, 100]
    mock_df["adj_account_value"] = [90, 110, 110, 90, 90, 100, 110, 90, 100]
    mock_df["adj_account_value_change"] = mock_df["adj_account_value"].diff()
    mock_df["adj_account_value_change_perc"] = mock_df["account_value"].pct_change()

    mock_performance_start_time = datetime.datetime.utcnow()
    res, trade_df = build_summary(mock_df, mock_performance_start_time)

    assert res["return_perc"] == 10.0
    assert res["sharpe_ratio"] == 0.469
    assert res["equity_peak"] == 110
    assert res["max_drawdown"] == 90
    assert res["buy_and_hold_perc"] == 9.091
    assert res["median_trade_len"] == 179.5
    assert res["mean_trade_len"] == 179.5
    assert res["max_trade_held"] == 299.0
    assert res["min_trade_len"] == 60.0
    assert res["total_num_winning_trades"] == 2
    assert res["avg_win_perc"] == 16.111
    assert res["total_num_losing_trades"] == 0
    assert pd.isna(res["avg_loss_perc"])
    assert res["best_trade_perc"] == 0.2222
    assert res["min_trade_perc"] == 0.1
    assert res["median_trade_perc"] == 0.1611
    assert res["mean_trade_perc"] == 0.1611
    assert res["num_trades"] == 3
    assert res["win_perc"] == 66.667
    assert res["loss_perc"] == 0.0
    assert res["equity_final"] == 100
    assert res["max_drawdown"] == 90
    assert res["total_fees"] == 0.0
    assert res["first_tic"] == "2018-04-17 04:03:04"
    assert res["last_tic"] == "2018-04-17 04:11:03"
    assert res["total_tics"] == 9
    assert type(res["test_duration"]) is float
    assert len(trade_df.index) == 3
