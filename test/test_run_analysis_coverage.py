"""Additional run_analysis coverage: exit_on_end, fees, progress, fallback."""

from unittest import mock

import numpy as np
import polars as pl
import pytest

from fast_trade.run_analysis import (
    _encode_actions,
    _simulate_account_path,
    apply_logic_to_df,
)


def _ohlcv():
    return pl.read_csv("./test/ohlcv_data.csv.txt").with_columns(
        pl.from_epoch(pl.col("date"), time_unit="s")
    )


def test_simulate_account_path_max_lot_size_and_progress():
    closes = np.array([10.0, 11.0, 12.0])
    progress = []
    sim = _simulate_account_path(
        action_codes=_encode_actions(np.array(["e", "h", "x"])),
        close_prices=closes,
        base_balance=1000.0,
        comission=0.0,
        lot_size=1.0,
        max_lot_size=100.0,
        progress_callback=progress.append,
    )
    # Capped at 100 notional -> 10 aux
    assert sim["aux"][0] == pytest.approx(10.0)
    assert sim["account_value"][0] == pytest.approx(900.0)
    assert progress[-1]["percent"] == 100


def test_apply_logic_exit_on_end_with_fees_appends_row():
    df = _ohlcv().head(3).with_columns(pl.Series("action", ["e", "h", "h"]))
    backtest = {
        "base_balance": 1000.0,
        "exit_on_end": True,
        "comission": 1.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0,
    }
    out = apply_logic_to_df(df, backtest)
    assert out.height == 4
    assert out["in_trade"][-1] is False
    assert out["fee"][-1] > 0


def test_apply_logic_fallback_exit_on_end_and_progress():
    df = _ohlcv().head(3).with_columns(pl.Series("action", ["e", "h", "h"]))
    backtest = {
        "base_balance": 1000.0,
        "exit_on_end": True,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0,
    }
    progress = []
    with mock.patch(
        "fast_trade.run_analysis._simulate_account_path",
        side_effect=RuntimeError("force fallback"),
    ):
        out = apply_logic_to_df(df, backtest, progress_callback=progress.append)

    assert out.height == 4
    assert out["in_trade"][-1] is False
    assert progress[-1]["percent"] == 100


def test_apply_logic_matches_between_vectorized_and_fallback():
    actions = ["e", "h", "x", "h", "e", "h", "x", "h", "h"]
    df = _ohlcv().with_columns(pl.Series("action", actions))
    backtest = {
        "base_balance": 1000.0,
        "exit_on_end": False,
        "comission": 0.5,
        "lot_size_perc": 0.75,
        "max_lot_size": 0,
    }

    vectorized = apply_logic_to_df(df, backtest)
    with mock.patch(
        "fast_trade.run_analysis._simulate_account_path",
        side_effect=RuntimeError("force fallback"),
    ):
        fallback = apply_logic_to_df(df, backtest)

    for column in ["aux", "account_value", "adj_account_value", "fee", "in_trade"]:
        assert vectorized[column].to_list() == pytest.approx(
            [float(value) for value in fallback[column].to_list()]
        )
