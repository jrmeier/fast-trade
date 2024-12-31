# flake8: noqa
from fast_trade.build_data_frame import prepare_df
from fast_trade import run_backtest
from fast_trade.validate_backtest import validate_backtest
from fast_trade.calculate_perc_missing import calculate_perc_missing
import datetime
import json
import pandas as pd
import matplotlib.pyplot as plt
from fast_trade.build_data_frame import apply_transformers_to_dataframe
from fast_trade.archive.db_helpers import get_kline


ds1 = "2020-06-01"
s1 = 1590969600
ms1 = 1590969600000

ds2 = "2020-07-10"
s2 = 1594339200
ms2 = 1594339200000

strategy = {
    "any_enter": [],
    "any_exit": [],
    "freq": "5Min",
    "comission": 0.01,
    "datapoints": [
        # {"args": [11], "name": "zlema_1", "transformer": "zlema", "freq": "15Min"},
        # {"args": [11], "name": "zlema_2", "transformer": "zlema", "freq": "15Min"},
        {"args": [11], "name": "zlema_1", "transformer": "zlema"},
        {"args": [11], "name": "zlema_2", "transformer": "zlema", "freq": "15Min"},
    ],
    "enter": [["zlema_1", ">", "close", 4]],
    "exit": [["zlema_2", "<", "close", 1]],
    "exit_on_end": False,
    "start": "2021-01-01 22:30:00",
    "stop": "2021-03-11 23:30:59",
    "trailing_stop_loss": 0.05,
    "max_lot_size": 1000,
    "lot_size": 1,
    "base_balance": 500,
}
if __name__ == "__main__":
    df = get_kline("BTCUSDT", "binanceus")
    from fast_trade.build_data_frame import apply_charting_to_df

    start = "2024-12-19 22:23:00"
    stop = "2024-12-30 00:00:00"
    df = apply_charting_to_df(df, strategy["freq"], start, stop)
    # print(df.index.freq)
    # df.index = pd.to_datetime(df.index, unit="s")
    # print(df)
    res = apply_transformers_to_dataframe(df, strategy["datapoints"])

    print(res.tail())
