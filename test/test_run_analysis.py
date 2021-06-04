import pytest
import pandas as pd
import random
from fast_trade.run_analysis import (
    calculate_new_account_value_on_enter,
    convert_base_to_aux,
    convert_aux_to_base,
    apply_logic_to_df,
    enter_position,
    exit_position,
    calculate_fee,
)


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


def test_calculate_fee():
    mock_price = 100
    mock_comission = 0.02

    fee = calculate_fee(mock_price, mock_comission)

    assert fee == 0.02


def test_calculate_fee_again():
    mock_price = 200
    mock_comission = 0.1

    fee = calculate_fee(mock_price, mock_comission)

    assert fee == 0.2


def test_calculate_fee_no_comission():
    mock_price = 100
    mock_comission = 0.00

    fee = calculate_fee(mock_price, mock_comission)

    assert fee == 0.0


def test_enter_position_1():
    mock_account_value_list = []
    mock_lot_size = 1
    mock_account_value = 1000
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 100.0
    assert fee == 0.0
    assert new_account_value == 0


def test_enter_position_2():
    mock_account_value_list = [1000]
    mock_account_value = 0
    mock_lot_size = 1
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 100.0
    assert fee == 0.0
    assert new_account_value == 0


def test_enter_position_3():
    mock_account_value_list = [1000, 0, 1100]
    mock_account_value = 1100
    mock_lot_size = 1
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 110.0
    assert fee == 0.0
    assert new_account_value == 0


def test_enter_position_lot_size():
    mock_account_value_list = [1000, 0, 1100]
    mock_account_value = 1100
    mock_lot_size = 0.5
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 55.0
    assert fee == 0.0
    assert new_account_value == 0


def test_enter_position_comission():
    mock_account_value_list = []
    mock_lot_size = 1
    mock_account_value = 1000
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0.02

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 99.98
    assert fee == 0.02
    assert new_account_value == 0


def test_enter_position_comission_and_lot_size():
    mock_account_value_list = []
    mock_lot_size = 0.1
    mock_account_value = 1000
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0.02

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 9.998
    assert fee == 0.002
    assert new_account_value == 0


def test_exit_position_basic():
    mock_account_value_list = [1000, 0]
    mock_aux = 100
    mock_close = 11
    mock_comission = 0

    in_trade, new_aux, new_account_value, fee = exit_position(
        mock_account_value_list, mock_close, mock_aux, mock_comission
    )

    assert in_trade is False
    assert new_aux == 0
    assert fee == 0.0
    assert new_account_value == 1100


def test_exit_position_without_account_value():
    # There should always be an account available if we are exiting the trade.
    mock_account_value_list = []
    mock_aux = 100
    mock_close = 11
    mock_comission = 0

    with pytest.raises(IndexError):
        exit_position(mock_account_value_list, mock_close, mock_aux, mock_comission)


def test_exit_position_as_second_tick():
    mock_account_value_list = [500]
    mock_aux = 100
    mock_close = 11
    mock_comission = 0

    in_trade, new_aux, new_account_value, fee = exit_position(
        mock_account_value_list, mock_close, mock_aux, mock_comission
    )

    assert in_trade is False
    assert new_aux == 0
    assert fee == 0.0
    assert new_account_value == 1600


def test_calculate_new_account_value_on_enter_basic():
    mock_aux = 100
    mock_close = 10
    mock_fee = 0.0
    mock_base_transaction_amount = 1000

    new_account_value = calculate_new_account_value_on_enter(
        mock_aux, mock_close, mock_fee, mock_base_transaction_amount
    )

    assert new_account_value == 0


def test_calculate_new_account_value_on_enter_with_fee():
    mock_aux = 100
    mock_close = 10
    mock_fee = 0.01
    mock_base_transaction_amount = 1000

    new_account_value = calculate_new_account_value_on_enter(
        mock_aux, mock_close, mock_fee, mock_base_transaction_amount
    )

    assert new_account_value == 0


# def test_apply_logic_to_df_1():
#     mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
#         "date"
#     )

#     mock_df.index = pd.to_datetime(mock_df.index, unit="s")
#     mock_backtest = {"base_balance": 1000, "exit_on_end": True, "comission": 0.00}

#     mock_df["action"] = ["e", "h", "x", "x", "x", "e", "x", "h", "h"]

#     print("df: ", mock_df)
#     df = apply_logic_to_df(mock_df, mock_backtest)
#     # print(mock_df)

#     print("DF: ", df)
#     assert list(df.adj_account_value.values) == [
#         1000.0,
#         1000.0,
#         2296.0,
#         2296.0,
#         2296.0,
#         2296.0,
#         2274.32014388,
#         2274.32014388,
#         2274.32014388,
#     ]


# def test_apply_logic_to_df_2():
#     mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
#         "date"
#     )
#     mock_df.index = pd.to_datetime(mock_df.index, unit="s")

#     mock_backtest = {"base_balance": 1000, "exit_on_end": True, "comission": 0.00}
#     mock_df["action"] = ["e", "h", "h", "x", "h", "h", "e", "h", "h"]

#     df = apply_logic_to_df(mock_df, mock_backtest)

#     assert list(df.aux.values) == [
#         100000.0,
#         100000.0,
#         100000.0,
#         100000.0,
#         100000.0,
#         100000.0,
#         96232.41034952,
#         96232.41034952,
#         96232.41034952,
#         96232.41034949,
#     ]

#     assert list(df.account_value.values) == [
#         1000.0,
#         1000.0,
#         1000.0,
#         2120.0,
#         2120.0,
#         2120.0,
#         2120.0,
#         2120.0,
#         2120.0,
#         2120.0,
#     ]
