import datetime

import numpy as np
import polars as pl
import pytest

from fast_trade import run_analysis
from fast_trade.run_analysis import (
    calculate_new_account_value_on_enter,
    convert_base_to_aux,
    convert_aux_to_base,
    apply_logic_to_df,
    enter_position,
    exit_position,
    calculate_fee,
)
from fast_trade.run_backtest import apply_backtest_to_df, prepare_new_backtest


def _ohlcv_df():
    """OHLCV fixture as a Polars frame with an explicit date column."""
    return pl.read_csv("./test/ohlcv_data.csv.txt").with_columns(
        pl.from_epoch(pl.col("date"), time_unit="s")
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
    mock_comission = 0.01

    fee = calculate_fee(mock_price, mock_comission)

    assert fee == 0.01


def test_calculate_fee_again():
    mock_price = 200
    mock_comission = 0.1

    fee = calculate_fee(mock_price, mock_comission)

    assert fee == 0.2


def test_calculate_fee_larger():
    mock_order_size = 1000
    mock_comission = 0.1

    fee = calculate_fee(mock_order_size, mock_comission)

    assert fee == 1


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
    assert new_account_value == 550.0


def test_enter_position_comission():
    mock_account_value_list = []
    mock_lot_size = 1
    mock_account_value = 1000
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0.01

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 99.99

    assert fee == 0.01
    assert new_account_value == 0


def test_enter_position_comission_and_lot_size():
    mock_account_value_list = []
    mock_lot_size = 0.5
    mock_account_value = 1000
    mock_max_lot_size = 0
    mock_close = 10
    mock_comission = 0.01

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 49.995
    assert fee == 0.005
    assert new_account_value == 500


def test_enter_position_max_lot_size():
    mock_account_value_list = []
    mock_lot_size = 0.5
    mock_account_value = 1000
    mock_max_lot_size = 100
    mock_close = 10
    mock_comission = 0.01

    in_trade, new_aux, new_account_value, fee = enter_position(
        mock_account_value_list,
        mock_lot_size,
        mock_account_value,
        mock_max_lot_size,
        mock_close,
        mock_comission,
    )

    assert in_trade is True
    assert new_aux == 9.999
    assert fee == 0.001
    assert new_account_value == 900


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
    mock_base_transaction_amount = 1000
    mock_account_value_list = []
    mock_account_value = 1000

    new_account_value = calculate_new_account_value_on_enter(
        mock_base_transaction_amount, mock_account_value_list, mock_account_value
    )
    assert new_account_value == 0


def test_calculate_new_account_value_on_enter_with_account_vaue_list():
    mock_base_transaction_amount = 600
    mock_account_value_list = [1000]
    mock_account_value = 1000

    new_account_value = calculate_new_account_value_on_enter(
        mock_base_transaction_amount, mock_account_value_list, mock_account_value
    )

    assert new_account_value == 400


def test_apply_logic_to_df_simple():
    mock_backtest = {
        "base_balance": 1000,
        "exit_on_end": True,
        "comission": 0.00,
        "lot_size_perc": 1,
    }
    mock_df = _ohlcv_df().with_columns(
        pl.Series("action", ["e", "h", "x", "x", "x", "e", "x", "h", "h"])
    )

    df = apply_logic_to_df(mock_df, mock_backtest)

    assert df["in_trade"].to_list() == [
        True,
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
    ]

    assert df["account_value"].to_list() == [
        0.0,
        0.0,
        2296.0,
        2296.0,
        2296.0,
        0.0,
        2274.32014388,
        2274.32014388,
        2274.32014388,
    ]

    assert df["adj_account_value"].to_list() == [
        1000.0,
        1404.0,
        2296.0,
        2296.0,
        2296.0,
        2296.0,
        2274.32014388,
        2274.32014388,
        2274.32014388,
    ]

    assert df["fee"].sum() == 0.0
    # exit_on_end had nothing to close out, so no extra bar was added
    assert df.height == 9


def test_apply_logic_to_df_lot_size():
    mock_backtest = {
        "base_balance": 1000,
        "exit_on_end": True,
        "comission": 0.00,
        "lot_size_perc": 0.5,
    }
    mock_df = _ohlcv_df().with_columns(
        pl.Series("action", ["e", "h", "h", "x", "h", "h", "e", "h", "h"])
    )

    df = apply_logic_to_df(mock_df, mock_backtest)

    assert df["in_trade"].to_list() == [
        True,
        True,
        True,
        False,
        False,
        False,
        True,
        True,
        True,
        False,
    ]

    # Float path rounds once at the end; allow tiny float drift vs legacy per-fill round.
    assert df["adj_account_value"].to_list() == pytest.approx(
        [
            1000.0,
            1202.0,
            1648.0,
            1560.0,
            1560.0,
            1560.0,
            1560.0,
            1555.39718566,
            1539.81842941,
            1539.81842941,
        ],
        rel=1e-9,
        abs=1e-8,
    )

    # exit_on_end closed the open position on a bar one second after the last
    assert df.height == 10
    assert df["date"][-1] - df["date"][-2] == datetime.timedelta(seconds=1)


@pytest.mark.skipif(not run_analysis._HAS_NUMBA, reason="numba not installed")
def test_no_progress_callback_takes_numba_kernel(monkeypatch):
    """Without a callback the simulation must reach the compiled kernel."""
    calls = {"kernel": 0, "python": 0}
    real_kernel = run_analysis._simulate_account_path_kernel
    real_python = run_analysis._simulate_account_path_python

    def spy_kernel(*args, **kwargs):
        calls["kernel"] += 1
        return real_kernel(*args, **kwargs)

    def spy_python(*args, **kwargs):
        calls["python"] += 1
        return real_python(*args, **kwargs)

    monkeypatch.setattr(run_analysis, "_simulate_account_path_kernel", spy_kernel)
    monkeypatch.setattr(run_analysis, "_simulate_account_path_python", spy_python)

    backtest = {
        "base_balance": 1000,
        "comission": 0.1,
        "lot_size_perc": 1.0,
        "max_lot_size": 0.0,
        "enter": [["close", ">", 0]],
        "exit": [],
        "any_enter": [],
        "any_exit": [],
    }
    df = _ohlcv_df().with_columns(
        pl.Series("action", ["e", "h", "x", "x", "x", "e", "x", "h", "h"])
    )

    apply_backtest_to_df(df, backtest)
    assert calls == {"kernel": 1, "python": 0}

    events = []
    apply_backtest_to_df(df, backtest, progress_callback=events.append)
    assert calls == {"kernel": 1, "python": 1}
    assert {event["phase"] for event in events} == {"actions", "simulation"}


def test_kernel_and_python_simulations_agree():
    actions = pl.Series("action", ["e", "h", "x", "x", "x", "e", "x", "h", "h"])
    codes = run_analysis._encode_actions(actions.to_numpy())
    closes = _ohlcv_df()["close"].to_numpy().astype(float)

    kernel = run_analysis._simulate_account_path(
        action_codes=codes,
        close_prices=closes,
        base_balance=1000.0,
        comission=0.1,
        lot_size=0.75,
        max_lot_size=500.0,
        progress_callback=None,
    )
    python = run_analysis._simulate_account_path(
        action_codes=codes,
        close_prices=closes,
        base_balance=1000.0,
        comission=0.1,
        lot_size=0.75,
        max_lot_size=500.0,
        progress_callback=lambda payload: None,
    )

    for column in ["account_value", "aux", "fee", "adj_account_value"]:
        assert kernel[column] == pytest.approx(python[column], rel=1e-9, abs=1e-8)
    assert kernel["in_trade"].tolist() == python["in_trade"].tolist()


def test_null_lot_size_falls_back_to_defaults():
    """YAML `lot_size:` / `max_lot_size:` load as None and must not crash."""
    backtest = prepare_new_backtest(
        {
            "base_balance": 1000,
            "freq": "1Min",
            "lot_size": None,
            "max_lot_size": None,
            "enter": [],
            "exit": [],
        }
    )

    assert backtest["lot_size_perc"] == 1.0
    assert backtest["max_lot_size"] == 0.0

    df = _ohlcv_df().with_columns(
        pl.Series("action", ["e", "h", "x", "x", "x", "e", "x", "h", "h"])
    )
    out = apply_logic_to_df(df, backtest)
    assert out["adj_account_value"][0] == 1000.0


def test_max_lot_size_keeps_fractional_values():
    backtest = prepare_new_backtest(
        {
            "base_balance": 1000,
            "freq": "1Min",
            "max_lot_size": 0.5,
            "enter": [],
            "exit": [],
        }
    )

    assert backtest["max_lot_size"] == 0.5


def test_exit_on_end_appends_one_row_when_simulation_fails(monkeypatch):
    """Falling back to the row loop must not append the exit bar twice."""
    df = _ohlcv_df().with_columns(pl.Series("action", ["e"] + ["h"] * 8))
    backtest = {
        "base_balance": 1000,
        "exit_on_end": True,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0.0,
    }

    def broken_sim(**kwargs):
        # One value short, so attaching the columns raises and the row-by-row
        # fallback takes over after the exit bar has already been staged.
        n = len(kwargs["close_prices"]) - 1
        return {
            "in_trade": np.ones(n, dtype=bool),
            "account_value": np.zeros(n),
            "aux": np.ones(n),
            "fee": np.zeros(n),
            "adj_account_value": np.zeros(n),
        }

    monkeypatch.setattr(run_analysis, "_simulate_account_path", broken_sim)

    out = apply_logic_to_df(df, backtest)

    assert out.height == df.height + 1
    assert out["in_trade"].to_list()[-1] is False
