from datetime import datetime
import pandas as pd
import numpy as np
from pandas.core.base import DataError
from fast_trade.calculate_perc_missing import calculate_perc_missing


def test_calculate_perc_missing_none_missing():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )

    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)

    assert perc_missinng == 0.0
    assert total_missing == 0


def test_calculate_perc_missing_some_missing():
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True)
    # mock_df.index = pd.to_datetime(mock_df.date, unit="s")
    # print(mock_df.iloc[0].name)
    print(mock_df.iloc[0].date)
    # wtf = mock_df.index.get_loc(pd.to_datetime(1523938263, unit="s"))

    # print(mock_df.iloc[wtf])
    mock_df.close = [np.nan, np.nan, 2, 3, 4, 5, 6, 7, 8]
    # print(mock_df["1523937784"])
    # mock_df[1523937784].close = np.nan
    [perc_missinng, total_missing] = calculate_perc_missing(mock_df)
    #
    assert perc_missinng == 22.22
    assert total_missing == 2
    # print(perc_missinng)
    # assert True is False
