"""Additional build_data_frame and validate_backtest coverage."""

import datetime
from unittest import mock

import polars as pl
import pytest

from fast_trade.build_data_frame import (
    TransformerError,
    apply_charting_to_df,
    apply_transformers_to_dataframe,
    build_data_frame,
    detect_time_unit,
    infer_frequency,
    parse_date_bound,
    standardize_df,
)
from fast_trade.validate_backtest import (
    match_field_type_to_value,
    validate_backtest,
    validate_backtest_with_df,
)


def _ohlcv_df():
    """The csv fixture, date column still holding epoch seconds."""
    return pl.read_csv("./test/ohlcv_data.csv.txt")


def test_transformer_error_str():
    err = TransformerError("bad transformer")
    assert str(err) == "bad transformer"


def test_build_data_frame_empty_raises():
    bt = {"freq": "1Min", "start": "", "stop": "", "datapoints": []}
    with pytest.raises(Exception):
        build_data_frame(bt, "./test/empty.csv.txt")


def test_prepare_df_invalid_chart_period():
    bt = {"chart_period": "not_a_freq", "datapoints": []}
    with pytest.raises(ValueError, match="Invalid chart period"):
        from fast_trade.build_data_frame import prepare_df

        prepare_df(_ohlcv_df(), bt)


def test_prepare_df_uses_chart_period():
    from fast_trade.build_data_frame import prepare_df

    bt = {"chart_period": "3Min", "datapoints": []}
    out = prepare_df(_ohlcv_df(), bt)

    assert infer_frequency(out) == "3Min"


def test_apply_charting_no_date_column_raises():
    df = pl.DataFrame({"open": [1.0], "close": [1.0]})
    with pytest.raises(Exception, match="date column"):
        apply_charting_to_df(df, "1Min", "", "")


def test_apply_charting_converts_epoch_date_column():
    # date column is numeric epoch seconds, not datetime yet
    out = apply_charting_to_df(_ohlcv_df(), "1Min", "", "")
    assert isinstance(out.schema["date"], pl.Datetime)


def test_apply_transformers_requires_date_column():
    df = pl.DataFrame({"close": [1.0, 2.0]})
    with pytest.raises(Exception, match="date column"):
        apply_transformers_to_dataframe(df, [])


def test_apply_transformers_invalid_and_error():
    df = _ohlcv_df()
    with pytest.raises(ValueError, match="not a valid transformer"):
        apply_transformers_to_dataframe(df, [{"transformer": "nope", "name": "x", "args": []}])

    with mock.patch(
        "fast_trade.build_data_frame.transformers_map",
        {"sma": lambda *_a, **_k: (_ for _ in ()).throw(ValueError("boom"))},
    ):
        with pytest.raises(TransformerError, match="Error applying transformer"):
            apply_transformers_to_dataframe(df, [{"transformer": "sma", "name": "x", "args": [2]}])


def test_standardize_df_iso_dates_and_infer_frequency_branches():
    df = pl.DataFrame(
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
    assert isinstance(out.schema["date"], pl.Datetime)
    assert out.columns == ["date", "open", "high", "low", "close", "volume"]
    assert out.schema["open"] == pl.Float64

    base = datetime.datetime(2024, 1, 1)
    for delta, expected in [
        (datetime.timedelta(seconds=15), "15S"),
        (datetime.timedelta(minutes=7), "7Min"),
        (datetime.timedelta(hours=6), "6H"),
        (datetime.timedelta(days=2), "2D"),
    ]:
        frame = pl.DataFrame(
            {
                "date": [base, base + delta, base + delta * 2],
                "open": [1, 2, 3],
                "high": [2, 3, 4],
                "low": [0, 1, 2],
                "close": [1, 2, 3],
                "volume": [1, 2, 3],
            }
        )
        assert infer_frequency(frame) == expected

    single = pl.DataFrame({"date": [base], "close": [1]})
    assert infer_frequency(single) is None

    with pytest.raises(ValueError):
        infer_frequency(pl.DataFrame({"close": [1, 2, 3]}))

    assert detect_time_unit("not-a-ts") is None


def test_standardize_df_dedupes_and_requires_date():
    base = datetime.datetime(2024, 1, 1)
    df = pl.DataFrame(
        {
            "date": [base, base, base + datetime.timedelta(minutes=1)],
            "open": [1.0, 9.0, 2.0],
            "high": [1.0, 9.0, 2.0],
            "low": [1.0, 9.0, 2.0],
            "close": [1.0, 9.0, 2.0],
            "volume": [1.0, 9.0, 2.0],
        }
    )
    out = standardize_df(df)
    assert out.height == 2
    # the first row wins for duplicated dates
    assert out.get_column("close")[0] == 1.0

    with pytest.raises(Exception, match="date column"):
        standardize_df(pl.DataFrame({"close": [1.0]}))


def test_parse_date_bound_variants():
    assert parse_date_bound("") is None
    assert parse_date_bound(None) is None
    assert parse_date_bound("2024-03-04") == datetime.datetime(2024, 3, 4)
    assert parse_date_bound("2024-03-04", upper=True) == datetime.datetime(
        2024, 3, 4, 23, 59, 59, 999999
    )
    assert parse_date_bound("2024-03", upper=True) == datetime.datetime(
        2024, 3, 31, 23, 59, 59, 999999
    )
    assert parse_date_bound("2024-12", upper=True) == datetime.datetime(
        2024, 12, 31, 23, 59, 59, 999999
    )
    assert parse_date_bound("2024", upper=True) == datetime.datetime(
        2024, 12, 31, 23, 59, 59, 999999
    )
    assert parse_date_bound("2024") == datetime.datetime(2024, 1, 1)
    assert parse_date_bound(1523938200) == datetime.datetime(2018, 4, 17, 4, 10)
    assert parse_date_bound("1523938200") == datetime.datetime(2018, 4, 17, 4, 10)
    assert parse_date_bound(1523938200000) == datetime.datetime(2018, 4, 17, 4, 10)
    assert parse_date_bound(datetime.date(2024, 3, 4)) == datetime.datetime(2024, 3, 4)
    assert parse_date_bound(datetime.date(2024, 3, 4), upper=True) == datetime.datetime(
        2024, 3, 4, 23, 59, 59, 999999
    )
    assert parse_date_bound("2024/03/04") == datetime.datetime(2024, 3, 4)
    assert parse_date_bound("2024-03-04 05:06") == datetime.datetime(2024, 3, 4, 5, 6)

    with pytest.raises(ValueError, match="Could not parse date"):
        parse_date_bound("not a date")


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
    df = pl.DataFrame()
    with pytest.raises(Exception):
        validate_backtest_with_df(bt, df)

    df = pl.read_csv("./test/ohlcv_data.csv.txt")
    with pytest.raises(Exception, match="Datapoint"):
        validate_backtest_with_df(bt, df)

    df = df.with_columns(pl.lit(1.0).alias("sma_short"))
    validate_backtest_with_df(bt, df)  # no raise when column exists
