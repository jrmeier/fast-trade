import pytest
import polars as pl
import datetime

from fast_trade.build_data_frame import (
    build_data_frame,
    detect_time_unit,
    load_basic_df_from_csv,
    apply_transformers_to_dataframe,
    apply_charting_to_df,
    prepare_df,
    process_res_df,
)
from fast_trade.utils import ensure_date_column, infer_frequency

MOCK_DATA_PATH = "./test/ohlcv_data.csv.txt"


def mock_df():
    """The csv fixture with its epoch date column turned into datetimes."""
    return ensure_date_column(pl.read_csv(MOCK_DATA_PATH))


def test_detect_time_unit_s():
    mock_timestring = 1595115901734
    result = detect_time_unit(mock_timestring)

    assert result == "ms"


def test_detect_time_unit_ms():
    mock_timestring = 1595115901
    result = detect_time_unit(mock_timestring)

    assert result == "s"


def test_load_basic_df_from_csv_str_1():
    result_df = load_basic_df_from_csv(MOCK_DATA_PATH)
    header = result_df.columns
    assert "close" in header
    assert "open" in header
    assert "high" in header
    assert "low" in header
    assert "volume" in header

    assert header[0] == "date"
    assert isinstance(result_df.schema["date"], pl.Datetime)


def test_load_basic_df_from_csv_list_1():
    result_df = load_basic_df_from_csv(MOCK_DATA_PATH)

    expected_line = [0.01, 0.025, 0.01, 0.01404, 3117.0]

    assert list(result_df.drop("date").row(1)) == expected_line


def test_load_basic_df_from_csv_str_error_1():
    mock_data_path = "./test/SomeFakeNews.csv.txt"

    with pytest.raises(Exception, match=r"File not found:*"):
        load_basic_df_from_csv(mock_data_path)


def test_apply_transformers_to_dataframe_1_ind():
    mock_transformers = [
        {"transformer": "sma", "name": "example_transformer_name", "args": [3]}
    ]

    result_df = apply_transformers_to_dataframe(mock_df(), mock_transformers)

    header = result_df.columns

    assert "example_transformer_name" in header
    assert "FAKE_transformer_name" not in header


def test_apply_transformers_to_dataframe_no_args():
    mock_transformers = [{"transformer": "rsi", "name": "rsi", "args": []}]

    result_df = apply_transformers_to_dataframe(mock_df(), mock_transformers)

    assert "rsi" in result_df.columns


def test_apply_transformers_to_dataframe_no_args_multi_col():
    mock_transformers = [{"transformer": "wto", "name": "wto", "args": []}]

    result_df = apply_transformers_to_dataframe(mock_df(), mock_transformers)
    assert "wto_wto_wt1" in result_df.columns
    assert "wto_wto_wt2" in result_df.columns


def test_apply_transformers_to_dataframe_freq():
    mock_transformers = [
        {
            "transformer": "sma",
            "name": "example_transformer_name",
            "args": [3],
            "freq": "3Min",
        }
    ]

    result_df = apply_transformers_to_dataframe(mock_df(), mock_transformers)

    assert "example_transformer_name" in result_df.columns
    assert infer_frequency(result_df) == "1Min"


def test_apply_charting_to_df_1():
    mock_freq = "2Min"
    mock_start_time = "2018-04-17"
    mock_stop_time = ""

    result_df = apply_charting_to_df(
        mock_df(), mock_freq, mock_start_time, mock_stop_time
    )
    dates = result_df.get_column("date")

    assert (dates[2] - dates[1]).total_seconds() == 120
    assert (dates[4] - dates[1]).total_seconds() == 360


def test_apply_charting_to_df_2():
    mock_freq = "1Min"
    mock_start_time = "2018-04-17 04:00:00"
    mock_stop_time = "2018-04-17 04:10:00"

    past_stop_time = datetime.datetime.strptime(
        "2018-04-17 04:11:00", "%Y-%m-%d %H:%M:%S"
    )
    result_df = apply_charting_to_df(
        mock_df(), mock_freq, mock_start_time, mock_stop_time
    )

    assert result_df.get_column("date")[-1] < past_stop_time


def test_apply_charting_to_df_3():
    mock_freq = "1Min"
    mock_start_time = ""
    mock_stop_time = "2018-04-17 04:10:00"

    past_stop_time = datetime.datetime.strptime(
        "2018-04-17 04:11:00", "%Y-%m-%d %H:%M:%S"
    )
    result_df = apply_charting_to_df(
        mock_df(), mock_freq, mock_start_time, mock_stop_time
    )

    assert result_df.get_column("date")[0] < past_stop_time
    assert result_df.get_column("date")[-1] <= datetime.datetime(2018, 4, 17, 4, 10)


def test_apply_charting_to_df_stop_time_int():
    mock_freq = "1Min"
    mock_start_time = ""
    mock_stop_time = 1523938200

    past_stop_time = datetime.datetime.strptime(
        "2018-04-17 04:11:00", "%Y-%m-%d %H:%M:%S"
    )

    result_df = apply_charting_to_df(
        mock_df(), mock_freq, mock_start_time, mock_stop_time
    )

    assert result_df.get_column("date")[0] < past_stop_time
    assert result_df.get_column("date")[-1] <= datetime.datetime(2018, 4, 17, 4, 10)


def test_apply_charting_to_df_start_time_int():
    mock_freq = "1Min"
    mock_start_time = 1523938200
    mock_stop_time = ""

    result_df = apply_charting_to_df(
        mock_df(), mock_freq, mock_start_time, mock_stop_time
    )

    assert result_df.get_column("date")[0] >= datetime.datetime(2018, 4, 17, 4, 10)


def test_apply_charting_to_df_no_date_column():
    df = pl.DataFrame({"open": [1.0], "close": [1.0]})

    with pytest.raises(Exception, match="date column"):
        apply_charting_to_df(df, "1Min", "", "")


def test_process_res_df():
    df = mock_df()
    mock_ind = {"name": "ind_1", "transformer": "sma", "args": [3]}
    val1 = [0.0, 1, 2, 3, 4, 5, 6, 7, 8]
    val2 = [8.0, 7, 6, 5, 4, 3, 2, 1, 0]
    mock_trans_res = pl.DataFrame({"Val 1": val1, "Val 2": val2})

    res = process_res_df(df, mock_ind, mock_trans_res)

    assert list(res.get_column("ind_1_sma_val_1")) == val1
    assert list(res.get_column("ind_1_sma_val_2")) == val2


def test_process_res_df_aligns_on_dates():
    df = mock_df()
    mock_ind = {"name": "ind_1", "transformer": "sma", "args": [3]}
    dates = df.get_column("date")[::3]
    mock_trans_res = pl.DataFrame({"Val 1": [1.0, 2.0, 3.0]})

    res = process_res_df(df, mock_ind, mock_trans_res, dates)

    # only the rows the transformer ran against get a value
    assert list(res.get_column("ind_1_sma_val_1")) == [
        1.0,
        None,
        None,
        2.0,
        None,
        None,
        3.0,
        None,
        None,
    ]


def test_prepare_df():
    mock_backtest = {
        "freq": "1Min",
        "start": "",
        "stop": "",
        "trailing_stop_loss": 0.1,
        "datapoints": [{"name": "ind_1", "args": [], "transformer": "ema"}],
    }

    res = prepare_df(mock_df(), mock_backtest)

    assert "ind_1" in res.columns
    assert "trailing_stop_loss" in res.columns


def test_build_data_frame():
    mock_backtest = {
        "freq": "1Min",
        "start": "",
        "stop": "",
        "trailing_stop_loss": 0.01,
        "datapoints": [{"name": "indy_2", "args": [2], "transformer": "sma"}],
    }

    res = build_data_frame(mock_backtest, MOCK_DATA_PATH)

    assert isinstance(res, pl.DataFrame)
    assert "indy_2" in res.columns
    assert isinstance(res.schema["date"], pl.Datetime)


def test_build_data_frame_no_data():
    mock_backtest = {
        "freq": "1Min",
        "start": "",
        "stop": "",
        "trailing_stop_loss": 0.01,
        "datapoints": [{"name": "indy_2", "args": [2], "transformer": "sma"}],
    }

    mock_csv_path = "./test/empty.csv.txt"

    with pytest.raises(Exception, match="Dataframe is empty"):
        build_data_frame(mock_backtest, mock_csv_path)
