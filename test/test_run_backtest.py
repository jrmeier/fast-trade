from numpy import nan
from fast_trade.run_backtest import (
    prepare_new_backtest,
    process_logic_and_generate_actions,
    run_backtest,
    take_action,
    clean_field_type,
    process_single_logic,
    process_single_frame,
    determine_action,
    apply_backtest_to_df,
)

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

    res = take_action(mock_row, mock_backtest, last_frames=[mock_row])
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

    res = take_action(mock_row, mock_backtest, last_frames=[mock_row])

    assert res is False


def test_take_action_not_equal():
    mock_backtest = [["close", "!=", 0.0219]]
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

    res = take_action(mock_row, mock_backtest, last_frames=[mock_row])
    assert res is True


def test_take_action_no_res():
    # mock_backtest = [["close", "!=", 0.0219]]
    mock_backtest = []
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

    res = take_action(mock_row, mock_backtest, last_frames=[])
    assert res is False


def test_take_action_many_frames():
    mock_backtest = [["close", "=", 0.0212, 2]]
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

    mock_last_frames = [mock_row, mock_row]

    res = take_action(mock_row, mock_backtest, last_frames=mock_last_frames)
    assert res is True


def test_take_action_many_frames_fail():
    mock_backtest = [["close", "=", 0.0212, 3]]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row_1 = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    mock_row_2 = MockRow(
        date=1523937966,
        close=0.0219,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    mock_row_3 = MockRow(
        date=1523937999,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    mock_last_frames = [mock_row_1, mock_row_2, mock_row_3]

    res = take_action(mock_row_1, mock_backtest, last_frames=mock_last_frames)

    assert res is False


# WTF
def test_take_action_many_frames_diff():
    mock_backtest = [["close", "=", 0.0212, 3]]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row_1 = MockRow(
        date=1523937963,
        close=0.0214,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    mock_row_2 = MockRow(
        date=1523937966,
        close=0.0219,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    mock_row_3 = MockRow(
        date=1523937999,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
    )

    mock_last_frames = [mock_row_1, mock_row_2, mock_row_3]

    res = take_action(mock_row_1, mock_backtest, last_frames=mock_last_frames)

    assert res is False


def test_clean_field_type_num():
    mock_field = "mock_f1"
    MockRow = namedtuple("MockRow", "date close open high low volume short mock_f1")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
        mock_f1=50,
    )

    res = clean_field_type(mock_field, mock_row)

    assert res == 50


def test_clean_field_type_num_str():
    mock_field = "50"
    MockRow = namedtuple("MockRow", "date close open high low volume short mock_f1")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
        mock_f1=50,
    )

    res = clean_field_type(mock_field, mock_row)

    assert res == 50


def test_clean_field_type_float_str():
    mock_field = "50.0"
    MockRow = namedtuple("MockRow", "date close open high low volume short mock_f1")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.01,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
        mock_f1=50,
    )

    res = clean_field_type(mock_field, mock_row)

    assert res == 50


def test_clean_field_type_float():
    mock_field = 50.04
    MockRow = namedtuple("MockRow", "date close open high low volume short mock_f1")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0112,
        mock_f1=50.04,
    )

    res = clean_field_type(mock_field, mock_row)

    assert res == 50.04


def test_clean_field_type_no_row_bool():
    mock_field = True

    res = clean_field_type(mock_field)

    assert res is True


def test_clean_field_type_no_row():
    mock_field = None

    res = clean_field_type(mock_field)

    assert res is None


def test_process_single_logic():
    mock_logic = ["close", "<", "short"]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    res = process_single_logic(mock_logic, mock_row)

    assert res is True


def test_process_single_logic_false():
    mock_logic = ["close", "=", "short"]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    res = process_single_logic(mock_logic, mock_row)

    assert res is False


def test_process_single_logic_false_greater():
    mock_logic = ["close", ">", "short"]
    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    res = process_single_logic(mock_logic, mock_row)

    assert res is False


def process_single_frame_2(logics, row, require_any):
    results = []

    return_value = False
    for logic in logics:
        res = process_single_logic(logic, row)
        results.append(res)

    if len(results):
        if require_any:
            return_value = any(results)
        else:
            return_value = all(results)

    return return_value


def test_process_single_frame_require_any_false():
    mock_logics = [["close", ">", "short"], ["close", ">", "low"]]

    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )
    mock_require_any = False

    res = process_single_frame(mock_logics, mock_row, mock_require_any)

    assert res is False


def test_process_single_frame_require_any_true():
    mock_logics = [["close", ">", "short"], ["close", ">", "low"]]

    MockRow = namedtuple("MockRow", "date close open high low volume short")
    mock_row = MockRow(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )
    mock_require_any = True

    res = process_single_frame(mock_logics, mock_row, mock_require_any)

    assert res is True


def test_determine_action_1():
    MockFrame = namedtuple("MockFrame", "date close open high low volume short")
    mock_frame = MockFrame(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    mock_backtest = {
        "exit": [["close", "<", "short"]],
        "any_exit": [],
        "enter": [],
        "any_enter": [],
    }

    res = determine_action(mock_frame, mock_backtest, last_frames=[mock_frame])

    assert res == "x"


def test_determine_action_2():
    MockFrame = namedtuple("MockFrame", "date close open high low volume short")
    mock_frame = MockFrame(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    mock_backtest = {
        "exit": [["close", ">", "short"]],
        "any_exit": [],
        "enter": [],
        "any_enter": [],
    }

    res = determine_action(mock_frame, mock_backtest, last_frames=[mock_frame])

    assert res == "h"


def test_determine_action_2_any_exit():
    MockFrame = namedtuple("MockFrame", "date close open high low volume short")
    mock_frame = MockFrame(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    mock_backtest = {
        "exit": [],
        "any_exit": [["close", "<", "short"]],
        "enter": [],
        "any_enter": [],
    }

    res = determine_action(mock_frame, mock_backtest, last_frames=[mock_frame])

    assert res == "ax"


def test_determine_action_3_any_exit():
    MockFrame = namedtuple("MockFrame", "date close open high low volume short")
    mock_frame = MockFrame(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    mock_backtest = {
        "exit": [["close", ">", "short"]],
        "any_exit": [["close", "<", "short"]],
        "enter": [],
        "any_enter": [],
    }

    res = determine_action(mock_frame, mock_backtest, last_frames=[mock_frame])

    assert res == "ax"


def test_determine_action_1_trailing_stop_loss():
    MockFrame = namedtuple(
        "MockFrame", "date close open high low volume short trailing_stop_loss"
    )
    mock_frame = MockFrame(
        date=1523937963,
        close=0.0212,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
        trailing_stop_loss=10,
    )

    mock_backtest = {
        "exit": [["close", ">", "short"]],
        "any_exit": [["close", ">", "short"]],
        "enter": [],
        "any_enter": [],
        "trailing_stop_loss": 0.0213,
    }

    res = determine_action(mock_frame, mock_backtest, last_frames=[mock_frame])

    assert res == "tsl"


def test_determine_action_enter_1_mult():
    MockFrame = namedtuple("MockFrame", "date close open high low volume short")
    mock_frame = MockFrame(
        date=1523937963,
        close=0.0588,
        open=0.0133,
        high=0.125,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    mock_backtest = {
        "exit": [],
        "any_exit": [],
        "enter": [["close", ">", "short"], ["high", ">", "close"]],
        "any_enter": [],
    }

    res = determine_action(mock_frame, mock_backtest, last_frames=[mock_frame])

    assert res == "e"


def test_determine_action_any_enter():
    MockFrame = namedtuple("MockFrame", "date close open high low volume short")
    mock_frame = MockFrame(
        date=1523937963,
        close=0.0588,
        open=0.0133,
        high=0.025,
        low=0.01,
        volume=36898,
        short=0.0312,
    )

    mock_backtest = {
        "exit": [],
        "any_exit": [],
        "enter": [["close", ">", "19"]],
        "any_enter": [["close", ">", "short"], ["close", ">", 100]],
    }

    res = determine_action(mock_frame, mock_backtest, last_frames=[mock_frame])

    assert res == "ae"


def test_proccess_logic_and_actions_no_logics():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_backtest = {
        "exit": [],
        "any_exit": [],
        "enter": [],
        "any_enter": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)

    assert "h" in res.action.unique()


def test_proccess_logic_and_actions_single_enter():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_backtest = {
        "exit": [],
        "any_exit": [],
        "enter": [["volume", ">", 171000]],
        "any_enter": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)
    assert list(res.action.values) == ["h", "h", "h", "h", "h", "e", "e", "e", "e"]


def test_proccess_logic_and_actions_multi_enter():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    mock_backtest = {
        "exit": [],
        "any_exit": [],
        "enter": [["ind_1", "<", 9], ["ind_1", ">", 7]],
        "any_enter": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)

    assert list(res.action.values) == [
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "e",
        "h",
    ]


def test_proccess_logic_and_actions_single_any_enter():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    mock_backtest = {
        "exit": [],
        "any_exit": [],
        "enter": [],
        "any_enter": [["ind_1", ">", 8]],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)
    assert list(res.action.values) == [
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "ae",
    ]


def test_proccess_logic_and_actions_single_exit():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    mock_backtest = {
        "exit": [["ind_1", ">", 7]],
        "any_exit": [],
        "enter": [],
        "any_enter": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)
    assert list(res.action.values) == [
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "x",
        "x",
    ]


def test_proccess_logic_and_actions_single_any_exit():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_df["ind_1"] = [0, 0, 0, 0, 1, 1, 1, 0, 0]
    mock_backtest = {
        "exit": [],
        "any_exit": [["ind_1", "=", 1]],
        "enter": [],
        "any_enter": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)
    assert list(res.action) == [
        "h",
        "h",
        "h",
        "h",
        "ax",
        "ax",
        "ax",
        "h",
        "h",
    ]


def test_proccess_logic_and_actions_exit_enter():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [0, 1, 2, 4, 5, 5, 4, 4, 3]
    mock_backtest = {
        "exit": [["ind_1", "=", 4]],
        "any_exit": [],
        "enter": [["ind_1", "=", 5]],
        "any_enter": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)
    assert list(res.action.values) == [
        "h",
        "h",
        "h",
        "x",
        "e",
        "e",
        "x",
        "x",
        "h",
    ]


def test_proccess_logic_and_actions_multi_enter_exit():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    mock_backtest = {
        "exit": [["ind_1", ">", 8], ["ind_1", "<", 10]],
        "any_exit": [],
        "enter": [["ind_1", "<", 9], ["ind_1", ">", 7]],
        "any_enter": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)

    assert list(res.action.values) == [
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "e",
        "x",
    ]


def test_proccess_logic_and_actions_enter_exit_confirmations():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    mock_df["ind_2"] = [5, 5, 4, 2, 6, 4, 9, 9, 1]
    mock_backtest = {
        "enter": [["ind_1", "<", 2]],
        "any_enter": [],
        "exit": [["ind_2", ">", 8, 2]],
        "any_exit": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)
    print(res)

    assert list(res.action.values) == [
        "e",
        "e",
        "h",
        "h",
        "h",
        "h",
        "h",
        "x",
        "h",
    ]


def test_proccess_logic_and_actions_enter_exit_confirmations_multi():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    mock_df["ind_2"] = [5, 5, 4, 2, 6, 4, 9, 9, 1]
    mock_df["ind_3"] = [1, 1, 2, 3, 5, 9, 9, 9, 8]

    mock_backtest = {
        "enter": [["ind_1", "<", 2, 2]],
        "any_enter": [],
        "exit": [["ind_2", ">", 8, 2], ["ind_3", "<", 8, 3]],
        "any_exit": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)

    assert list(res.action.values) == [
        "h",
        "e",
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
        "h",
    ]


def test_proccess_logic_and_actions_enter_exit_confirmations_multi_2():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [5, 5, 5, 2, 6, 7, 9, 9, 1]

    mock_backtest = {
        "enter": [["ind_1", "=", 5, 2]],
        "any_enter": [],
        "exit": [["ind_1", ">", 6, 3]],
        "any_exit": [],
    }

    res = process_logic_and_generate_actions(mock_df, mock_backtest)

    print(res)
    assert list(res.action.values) == [
        "h",
        "e",
        "e",
        "h",
        "h",
        "h",
        "h",
        "x",
        "h",
    ]


def test_prepare_new_backtest_simple():
    mock_backtest = {"base_balance": 126, "exit_on_end": False, "comission": 0.022}

    res = prepare_new_backtest(mock_backtest)

    assert res["exit_on_end"] is False
    assert res["base_balance"] == 126
    assert res["comission"] != 0


def test_apply_backtest_to_df():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    # fake an indicator
    mock_df["ind_1"] = [5, 5, 5, 2, 6, 7, 9, 9, 1]

    mock_backtest = {
        "base_balance": 1000,
        "exit_on_end": False,
        "comission": 0.01,
        "lot_size_perc": 1,
        "enter": [["ind_1", "=", 5, 2]],
        "any_enter": [],
        "exit": [["ind_1", ">", 6, 3]],
        "any_exit": [],
    }

    res = apply_backtest_to_df(mock_df, mock_backtest)

    assert "adj_account_value_change_perc" in list(res.columns)
    assert "adj_account_value_change" in list(res.columns)
