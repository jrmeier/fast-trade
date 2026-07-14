"""Additional build_data_frame and validate_backtest coverage."""

import datetime
from unittest import mock

import pandas as pd
import pytest

from fast_trade.build_data_frame import (
    TransformerError,
    apply_charting_to_df,
    apply_transformers_to_dataframe,
    build_data_frame,
    detect_time_unit,
    infer_frequency,
    standardize_df,
)
from fast_trade.validate_backtest import (
    match_field_type_to_value,
    validate_backtest,
    validate_backtest_with_df,
)


def test_transformer_error_str():
    err = TransformerError("bad transformer")
    assert str(err) == "bad transformer"


def test_build_data_frame_empty_raises():
    bt = {"freq": "1Min", "start": "", "stop": "", "datapoints": []}
    with pytest.raises(Exception):
        build_data_frame(bt, "./test/empty.csv.txt")


def test_prepare_df_invalid_chart_period():
    df = pd.read_csv("./test/ohlcv_data.csv.txt")
    df.index = pd.to_datetime(df["date"], unit="s")
    bt = {"chart_period": "not_a_freq", "datapoints": []}
    with mock.patch("fast_trade.build_data_frame.infer_frequency", return_value=None):
        with pytest.raises(ValueError, match="Invalid chart period"):
            from fast_trade.build_data_frame import prepare_df
            prepare_df(df, bt)


def test_apply_charting_no_date_column_raises():
    df = pd.DataFrame({"open": [1], "close": [1]})
    with pytest.raises(Exception, match="date column"):
        apply_charting_to_df(df, "1Min", "", "")


def test_apply_charting_index_without_date_column():
    df = pd.read_csv("./test/ohlcv_data.csv.txt")
    df = df.set_index("date")
    # index is numeric epoch seconds, not datetime yet
    out = apply_charting_to_df(df, "1Min", "", "")
    assert isinstance(out.index, pd.DatetimeIndex)


def test_apply_transformers_invalid_and_error():
    df = pd.read_csv("./test/ohlcv_data.csv.txt")
    df.index = pd.to_datetime(df["date"], unit="s")
    with pytest.raises(ValueError, match="not a valid transformer"):
        apply_transformers_to_dataframe(df, [{"transformer": "nope", "name": "x", "args": []}])

    with mock.patch(
        "fast_trade.build_data_frame.transformers_map",
        {"sma": lambda *_a, **_k: (_ for _ in ()).throw(ValueError("boom"))},
    ):
        with pytest.raises(TransformerError, match="Error applying transformer"):
            apply_transformers_to_dataframe(df, [{"transformer": "sma", "name": "x", "args": [2]}])


def test_standardize_df_iso_dates_and_infer_frequency_branches():
    df = pd.DataFrame(
        {
            "date": ["2024-01-01 00:00:00", "2024-01-01 00:01:00"],
            "open": [1, 2],
            "high": [2, 3],
            "low": [0.5, 1.5],
            "close": [1.5, 2.5],
            "volume": [10, 20],
            "ignore": [0, 0],
        }
    )
    out = standardize_df(df)
    assert isinstance(out.index, pd.DatetimeIndex)

    for delta, expected in [
        (pd.Timedelta(seconds=15), "15S"),
        (pd.Timedelta(minutes=7), "7Min"),
        (pd.Timedelta(hours=6), "6H"),
        (pd.Timedelta(days=2), "2D"),
    ]:
        base = pd.Timestamp("2024-01-01")
        idx = pd.DatetimeIndex(
            [base, base + delta, base + delta * 2]
        )
        frame = pd.DataFrame(
            {"open": [1, 2, 3], "high": [2, 3, 4], "low": [0, 1, 2],
             "close": [1, 2, 3], "volume": [1, 2, 3]},
            index=idx,
        )
        assert infer_frequency(frame) == expected

    idx = pd.date_range("2024-01-01", periods=3, freq="h")
    frame = pd.DataFrame(
        {"open": [1, 2, 3], "high": [2, 3, 4], "low": [0, 1, 2],
         "close": [1, 2, 3], "volume": [1, 2, 3]},
        index=idx,
    )
    assert infer_frequency(frame) == frame.index.freq

    assert detect_time_unit("not-a-ts") is None


def test_validate_backtest_deprecated_and_lot_size_and_logic_edges():
    mirror = validate_backtest({"start_date": "x", "end_date": "y"})
    assert mirror["start_date"]["error"] is True

    mirror = validate_backtest({"lot_size": 2})
    assert mirror["lot_size"]["error"] is True
    mirror = validate_backtest({"lot_size": -1})
    assert mirror["lot_size"]["error"] is True

    dp = [{"transformer": "sma", "name": "sma_short", "args": [3]}]
    mirror = validate_backtest(
        {
            "datapoints": dp,
            "enter": [["close_macd", ">", "sma_short"]],
            "exit": [["close", "!=", "sma_short", -1]],
            "any_enter": [],
            "any_exit": [],
        }
    )
    assert mirror["enter"] is None  # close_macd ends with _macd generated key
    assert mirror["exit"]["error"] is True


def test_match_field_type_to_value():
    assert match_field_type_to_value("12") == 12
    assert match_field_type_to_value("1.5") == 1.5
    assert match_field_type_to_value("abc") == "abc"


def test_validate_backtest_with_df_raises():
    bt = {
        "datapoints": [{"transformer": "sma", "name": "sma_short", "args": [3]}],
        "enter": [["close", ">", "sma_short"]],
        "exit": [["close", "<", "sma_short"]],
        "start": "",
    }
    df = pd.DataFrame()
    with pytest.raises(Exception):
        validate_backtest_with_df(bt, df)

    df = pd.read_csv("./test/ohlcv_data.csv.txt")
    df.index = pd.to_datetime(df["date"], unit="s")
    with pytest.raises(Exception, match="Datapoint"):
        validate_backtest_with_df(bt, df)

    df["sma_short"] = 1.0
    validate_backtest_with_df(bt, df)  # no raise when column exists
