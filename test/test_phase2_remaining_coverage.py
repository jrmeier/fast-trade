"""Targeted tests for remaining uncovered branches."""

from collections import namedtuple
from unittest import mock

import pandas as pd
import pytest

from fast_trade.build_data_frame import apply_charting_to_df, build_data_frame, infer_frequency, prepare_df
from fast_trade.logic_utils import build_mask
from fast_trade.run_backtest import (
    _compile_field_accessor,
    _take_action_compiled,
    compile_action_logic,
    process_logic_and_generate_actions,
    run_backtest,
    run_backtest_chunked,
    run_backtests_parallel,
    take_action,
)
from fast_trade.summary.metrics import (
    calculate_buy_and_hold_perc,
    calculate_market_exposure,
    calculate_position_metrics,
    calculate_return_perc,
    calculate_shape_ratio,
    calculate_trade_streaks,
)
from fast_trade.summary.trades import calculate_trade_quality
from fast_trade.validate_backtest import validate_backtest, validate_backtest_with_df


def _ohlcv():
    df = pd.read_csv("./test/ohlcv_data.csv.txt").set_index("date")
    df.index = pd.to_datetime(df.index, unit="s")
    return df


def test_build_mask_column_column_operators():
    df = pd.DataFrame(
        {"a": [1, 2, 3], "b": [2, 2, 4]},
        index=pd.date_range("2024-01-01", periods=3, freq="h"),
    )
    for op in [">", "<", "=", "!=", ">=", "<="]:
        mask = build_mask(df, [["a", op, "b"]], combine_any=False)
        assert len(mask) == 3
    bad_op = build_mask(df, [["a", "~", "b"]], combine_any=False)
    assert not bad_op.any()


def test_build_data_frame_empty_after_load():
    bt = {"freq": "1Min", "start": "", "stop": "", "datapoints": []}
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    empty.index.name = "date"
    with mock.patch("fast_trade.build_data_frame.load_basic_df_from_csv", return_value=empty):
        with pytest.raises(Exception, match="Dataframe is empty"):
            build_data_frame(bt, "ignored.csv")


def test_prepare_df_uses_chart_period_when_freq_missing():
    df = _ohlcv()
    bt = {
        "chart_period": "1Min",
        "start": "",
        "stop": "",
        "datapoints": [{"name": "ema", "transformer": "ema", "args": []}],
    }
    with mock.patch("fast_trade.build_data_frame.infer_frequency", return_value="1Min"):
        out = prepare_df(df, bt)
    assert "ema" in out.columns


def test_apply_charting_date_column_path():
    df = pd.read_csv("./test/ohlcv_data.csv.txt")
    out = apply_charting_to_df(df, "1Min", "", "")
    assert isinstance(out.index, pd.DatetimeIndex)


def test_infer_frequency_requires_datetime_index():
    with pytest.raises(ValueError, match="DatetimeIndex"):
        infer_frequency(pd.DataFrame({"close": [1, 2]}))


def test_run_backtest_chart_period_and_no_int_periods():
    df = _ohlcv()
    bt = {
        "base_balance": 1000,
        "chart_period": "1Min",
        "start": "2018-04-17T04:05:00",
        "stop": "",
        "comission": 0.0,
        "lot_size": 1.0,
        "datapoints": [{"name": "ema", "transformer": "ema", "args": [3]}],
        "enter": [["volume", ">", 10000]],
        "exit": [["volume", ">", 170000]],
        "any_enter": [],
        "any_exit": [],
    }
    with mock.patch("fast_trade.build_data_frame.infer_frequency", return_value="1Min"), mock.patch(
        "fast_trade.run_backtest.get_kline", return_value=df.copy()
    ) as get_kline:
        run_backtest(bt, df=pd.DataFrame())
    assert get_kline.called


def test_process_logic_non_vectorized_path_with_progress():
    df = _ohlcv()
    backtest = {
        "enter": [["volume", ">", "close"]],
        "exit": [],
        "any_enter": [],
        "any_exit": [],
        "trailing_stop_loss": 0,
    }
    progress = []
    with mock.patch("fast_trade.run_backtest.can_vectorize_logic", return_value=False):
        out = process_logic_and_generate_actions(df, backtest, progress_callback=progress.append)
    assert "action" in out.columns
    assert progress


def test_compile_field_accessor_bool_and_take_action_none_frames():
    assert _compile_field_accessor(True) == (False, True)
    compiled = compile_action_logic(
        {"enter": [["close", ">", 1]], "exit": [], "any_enter": [], "any_exit": [], "trailing_stop_loss": False}
    )
    Row = namedtuple("Row", "close")
    row = Row(5)
    assert _take_action_compiled(row, compiled["enter"], last_frames=None) is True
    assert take_action(row, [["close", ">", 1]], last_frames=None) is True


def test_run_backtests_parallel_default_processes():
    df = _ohlcv()
    bt = {
        "base_balance": 1000,
        "freq": "1Min",
        "start": "",
        "stop": "",
        "datapoints": [],
        "enter": [["volume", ">", 10000]],
        "exit": [["volume", ">", 170000]],
        "any_enter": [],
        "any_exit": [],
    }
    results = run_backtests_parallel([bt], df=df.copy(), n_processes=None)
    assert len(results) == 1


def test_run_backtest_chunked_summary_false_and_defaults():
    df = _ohlcv()
    bt = {
        "base_balance": 1000,
        "freq": "1Min",
        "start": "",
        "stop": "",
        "datapoints": [],
        "enter": [["volume", ">", 10000]],
        "exit": [["volume", ">", 170000]],
        "any_enter": [],
        "any_exit": [],
    }
    result = run_backtest_chunked(bt, df=df.copy(), summary=False, chunk_size=None)
    assert "test_duration" in result["summary"]
    assert result["trade_df"].empty


def test_run_backtest_chunked_loads_empty_df_path():
    df = _ohlcv()
    bt = {
        "base_balance": 1000,
        "chart_period": "1Min",
        "start": "2018-04-17T04:05:00",
        "symbol": "BTC",
        "exchange": "test",
        "datapoints": [{"name": "ema", "transformer": "ema", "args": []}],
        "enter": [["volume", ">", 10000]],
        "exit": [["volume", ">", 170000]],
        "any_enter": [],
        "any_exit": [],
    }
    with mock.patch("fast_trade.build_data_frame.infer_frequency", return_value="1Min"), mock.patch(
        "fast_trade.run_backtest.get_kline", return_value=df.copy()
    ):
        result = run_backtest_chunked(bt, df=pd.DataFrame(), chunk_size=4)
    assert "summary" in result


def test_compile_field_accessor_fallback_type():
    assert _compile_field_accessor(None) == (False, None)


def test_take_action_compiled_require_any_continue():
    compiled = compile_action_logic(
        {
            "enter": [],
            "any_enter": [["close", ">", 100, 2], ["volume", ">", 0]],
            "exit": [],
            "any_exit": [],
            "trailing_stop_loss": False,
        }
    )
    Row = namedtuple("Row", "close volume")
    row = Row(5, 10)
    assert _take_action_compiled(row, compiled["any_enter"], last_frames=[row], require_any=True) is True


def test_metrics_return_buy_hold_sharpe_exceptions():
    tl = pd.DataFrame({"adj_account_value": ["bad", "values"]})
    assert calculate_return_perc(tl) == 0.0

    assert calculate_buy_and_hold_perc(pd.DataFrame({"close": ["bad", "data"]})) == 0.0

    with mock.patch.object(pd.Series, "mean", side_effect=ValueError("boom")):
        assert calculate_shape_ratio(
            pd.DataFrame({"adj_account_value_change_perc": [0.1, 0.2]})
        ) == 0.0

    df = pd.DataFrame(
        {"in_trade": [True], "aux": [1.0], "fee": [1.0], "adj_account_value": [100.0]}
    )
    with mock.patch("fast_trade.summary.metrics.round", side_effect=ValueError("boom")):
        res = calculate_position_metrics(df)
    assert res["avg_position_size"] == 0.0
    assert res["total_commission_impact"] == 0.0


def test_calculate_trade_streaks_empty_trades_series():
    trade_log = pd.DataFrame({"adj_account_value_change_perc": [0.1]})
    with mock.patch.object(pd.Series, "__gt__", return_value=pd.Series([], dtype=bool)):
        result = calculate_trade_streaks(trade_log)
    assert result["current_streak"] == 0
    assert result["max_win_streak"] == 0


def test_trade_quality_profit_factor_zero_division():
    only_wins = pd.DataFrame({"adj_account_value_change_perc": [1.0, 2.0]})
    with mock.patch.object(pd.Series, "sum", side_effect=ZeroDivisionError):
        q = calculate_trade_quality(only_wins)
    assert q["profit_factor"] == 0.0


def test_run_backtest_get_max_periods_no_int_args():
    df = _ohlcv()
    bt = {
        "base_balance": 1000,
        "freq": "1Min",
        "start": "2018-04-17T04:05:00",
        "symbol": "BTC",
        "exchange": "test",
        "datapoints": [{"name": "ema", "transformer": "ema", "args": []}],
        "enter": [["volume", ">", 10000]],
        "exit": [["volume", ">", 170000]],
        "any_enter": [],
        "any_exit": [],
    }
    with mock.patch("fast_trade.run_backtest.get_kline", return_value=df.copy()):
        run_backtest(bt, df=pd.DataFrame())


def test_validate_backtest_pos2_transformer_suffix_break():
    mirror = validate_backtest(
        {
            "datapoints": [{"transformer": "sma", "name": "sma", "args": [2]}],
            "enter": [["close", ">", "custom_macd"]],
            "exit": [],
            "start": "",
        }
    )
    assert mirror["enter"] is None


def test_metrics_and_trades_remaining_exception_paths():
    with mock.patch.object(pd.DataFrame, "__getitem__", side_effect=ValueError("boom")):
        assert calculate_market_exposure(
            pd.DataFrame({"in_trade": [True, False]})
        )["time_in_market_pct"] == 0.0

    with mock.patch.object(pd.Series, "shift", side_effect=KeyError):
        assert calculate_trade_streaks(
            pd.DataFrame({"adj_account_value_change_perc": [0.1]})
        )["current_streak"] == 0

    only_wins = pd.DataFrame({"adj_account_value_change_perc": [1.0, 2.0]})
    with mock.patch.object(pd.Series, "mean", side_effect=ZeroDivisionError):
        q = calculate_trade_quality(only_wins)
        assert q["avg_win_loss_ratio"] == 0.0

    mirror = validate_backtest(
        {
            "datapoints": [{"transformer": "sma", "name": "sma", "args": [2]}],
            "enter": [["bogus_field", ">", "also_bogus"]],
            "exit": [],
            "start": "",
        }
    )
    assert mirror["enter"]["error"] is True


def test_validate_backtest_transformer_suffix_and_with_df():
    dp = [{"transformer": "sma", "name": "sma_short", "args": [3]}]
    mirror = validate_backtest(
        {
            "datapoints": dp,
            "enter": [["close_macd", ">", "sma_short"]],
            "exit": [["close_signal", "<", "sma_short"]],
            "start": "",
        }
    )
    assert mirror["enter"] is None
    assert mirror["exit"] is None

    bt = {
        "datapoints": [{"transformer": "sma", "name": "prefix", "args": [2]}],
        "enter": [["close", ">", "prefix"]],
        "exit": [["close", "<", "prefix"]],
        "start": "",
    }
    df = _ohlcv()
    df["prefix_sma_value"] = 1.0
    validate_backtest_with_df(bt, df)

    bad_bt = {"datapoints": [], "enter": [], "exit": [], "start": ""}
    with mock.patch(
        "fast_trade.validate_backtest.validate_backtest",
        return_value={"has_error": True, "enter": True},
    ):
        with pytest.raises(Exception):
            validate_backtest_with_df(bad_bt, df)
