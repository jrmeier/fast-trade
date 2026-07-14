"""Additional coverage tests for run_backtest.py entry points and edge branches."""

from collections import namedtuple
from unittest import mock

import pandas as pd
import pytest

from fast_trade.run_backtest import (
    BacktestKeyError,
    MissingData,
    _compile_field_accessor,
    _resolve_compiled_field,
    _take_action_compiled,
    apply_backtest_to_df,
    clean_field_type,
    compile_action_logic,
    extract_error_messages,
    prepare_new_backtest,
    process_logic_and_generate_actions,
    process_single_frame,
    process_single_logic,
    run_backtest,
    run_backtest_chunked,
    run_backtests_parallel,
    take_action,
)


def _ohlcv():
    df = pd.read_csv("./test/ohlcv_data.csv.txt").set_index("date")
    df.index = pd.to_datetime(df.index, unit="s")
    return df


def _valid_backtest(**overrides):
    bt = {
        "base_balance": 1000,
        "freq": "1Min",
        "start": "",
        "stop": "",
        "comission": 0.0,
        "lot_size": 1.0,
        "datapoints": [],
        "enter": [["volume", ">", 10000]],
        "exit": [["volume", ">", 170000]],
        "any_enter": [],
        "any_exit": [],
        "trailing_stop_loss": 0,
    }
    bt.update(overrides)
    return bt


def test_extract_error_messages_nested_dict_and_list():
    err = {
        "msgs": ["a"],
        "child": {"msgs": [{"nested": {"msgs": [123]}}]},
        "items": [{"msgs": ["b"]}],
    }
    text = extract_error_messages(err)
    assert "a" in text
    assert "123" in text
    assert "b" in text


def test_backtest_key_error_accepts_string():
    err = BacktestKeyError("single error")
    assert "-single error" in str(err)


def test_prepare_new_backtest_defaults_and_deprecated(capsys):
    raw = {
        "chart_start": "2024-01-01T00:00:00",
        "chart_stop": "2024-01-02T00:00:00",
        "lot_size": 0.5,
    }
    out = prepare_new_backtest(raw)
    assert out["base_balance"] == 1000
    assert out["lot_size_perc"] == 0.5
    assert out["start"] == "2024-01-01T00:00:00"
    assert out["stop"] == "2024-01-02T00:00:00"
    assert "chart_start" not in out
    captured = capsys.readouterr()
    assert "chart_start is deprecated" in captured.out
    assert "chart_stop is deprecated" in captured.out


def test_run_backtest_raises_on_validation_error():
    with pytest.raises(BacktestKeyError):
        run_backtest({"datapoints": [], "enter": [], "exit": []})


def test_run_backtest_missing_data_when_archive_empty():
    bt = _valid_backtest(
        symbol="BTCUSDT",
        exchange="binanceus",
        datapoints=[{"name": "sma", "transformer": "sma", "args": [3]}],
    )
    with mock.patch("fast_trade.run_backtest.get_kline", return_value=pd.DataFrame()):
        with pytest.raises(MissingData, match="No data found"):
            run_backtest(bt, df=pd.DataFrame())


def test_run_backtest_loads_archive_with_progress_and_start_offset():
    df = _ohlcv()
    bt = _valid_backtest(
        symbol="BTCUSDT",
        exchange="binanceus",
        start="2018-04-17T04:00:00",
        datapoints=[{"name": "sma", "transformer": "sma", "args": [3]}],
    )
    progress = []

    with mock.patch("fast_trade.run_backtest.get_kline", return_value=df.copy()) as get_kline:
        result = run_backtest(bt, progress_callback=progress.append)

    assert get_kline.called
    assert progress[0] == {"phase": "data", "percent": 0}
    assert progress[-1]["phase"] in {"data", "actions", "simulation"}
    assert "summary" in result


def test_run_backtest_summary_false_skips_trade_log():
    df = _ohlcv()
    result = run_backtest(_valid_backtest(), df=df.copy(), summary=False)
    assert "test_duration" in result["summary"]
    assert result["trade_df"].empty


def test_run_backtest_evaluates_rules_in_summary():
    df = _ohlcv()
    rules = [["return_perc", ">", -1000]]
    result = run_backtest(_valid_backtest(rules=rules), df=df.copy())
    assert result["summary"]["rules"]["all"] is True


def test_compile_field_accessor_variants():
    assert _compile_field_accessor("42") == (False, 42)
    assert _compile_field_accessor("3.5") == (False, 3.5)
    assert _compile_field_accessor("close") == (True, "close")
    assert _compile_field_accessor(True) == (False, True)
    assert _compile_field_accessor(1.5) == (False, 1.5)


def test_resolve_compiled_field_dict_row():
    assert _resolve_compiled_field((True, "close"), {"close": 9.0}) == 9.0


def test_take_action_compiled_lookback_and_require_any():
    compiled = compile_action_logic(
        {
            "enter": [["close", ">", 10, 2]],
            "any_enter": [["volume", ">", 0, 1]],
            "exit": [],
            "any_exit": [],
            "trailing_stop_loss": False,
        }
    )
    Row = namedtuple("Row", "close volume")
    current = Row(5, 10)
    prior = Row(4, 1)
    assert _take_action_compiled(current, compiled["enter"], last_frames=[prior, prior]) is False
    assert _take_action_compiled(
        current, compiled["any_enter"], last_frames=[prior], require_any=True
    ) is True


def test_take_action_with_last_frames_and_require_any():
    Row = namedtuple("Row", "close volume")
    row = Row(5, 10)
    logics = [["close", ">", 1, 2]]
    assert take_action(row, logics, last_frames=[Row(4, 1)]) is False

    any_logics = [["close", ">", 100, 3], ["volume", ">", 0]]
    assert take_action(row, any_logics, last_frames=[row], require_any=True) is True
    assert take_action(row, [], last_frames=[]) is False
    assert take_action(row, [["volume", ">", 0]], last_frames=[]) is True


def test_process_single_logic_ge_le_and_frame_empty():
    Row = namedtuple("Row", "close")
    row = Row(5)
    assert process_single_logic(["close", ">=", 5], row) is True
    assert process_single_logic(["close", "<=", 5], row) is True
    assert process_single_frame([], row, False) is False


def test_clean_field_type_dict_row():
    assert clean_field_type("close", row={"close": 7}) == 7


def test_process_logic_vectorization_fallback():
    df = _ohlcv()
    backtest = _valid_backtest(enter=[["volume", ">", 10000]])
    progress = []

    with mock.patch("fast_trade.run_backtest.can_vectorize_logic", return_value=True), mock.patch(
        "fast_trade.run_backtest.vectorized_actions",
        side_effect=RuntimeError("vectorize failed"),
    ):
        out = process_logic_and_generate_actions(df, backtest, progress_callback=progress.append)

    assert "action" in out.columns
    assert progress


def test_apply_backtest_to_df_progress_phases():
    df = _ohlcv()
    backtest = prepare_new_backtest(_valid_backtest())
    progress = []
    out = apply_backtest_to_df(df, backtest, progress_callback=progress.append)
    phases = {p["phase"] for p in progress}
    assert "actions" in phases or "simulation" in phases
    assert out.index.name == "date"


def test_run_backtests_parallel_and_chunked():
    df = _ohlcv()
    bt = _valid_backtest()
    parallel = run_backtests_parallel([bt, bt], df=df.copy(), n_processes=1)
    assert len(parallel) == 2
    assert "summary" in parallel[0]

    chunked = run_backtest_chunked(bt, df=df.copy(), chunk_size=4)
    assert "summary" in chunked
    assert len(chunked["df"]) == len(df)


def test_run_backtest_chunked_empty_archive_raises():
    bt = _valid_backtest(
        symbol="X",
        exchange="Y",
        datapoints=[{"name": "sma", "transformer": "sma", "args": [2]}],
    )
    with mock.patch("fast_trade.run_backtest.get_kline", return_value=pd.DataFrame()):
        with pytest.raises(MissingData):
            run_backtest_chunked(bt, df=pd.DataFrame())


def test_run_backtest_chunked_validation_error():
    with pytest.raises(BacktestKeyError):
        run_backtest_chunked({"datapoints": [], "enter": [], "exit": []})
