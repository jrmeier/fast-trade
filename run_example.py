# flake8: noqa
from fast_trade import run_backtest
import matplotlib.pyplot as plt
import pandas as pd
import json
import os


if __name__ == "__main__":
    # csv_path = "/Users/jedmeier/binance_2020_04_16/BTCUSDT.csv"
    # ohlcv_path = "/Users/jedmeier/2017_standard/BTCUSDT.csv"
    ohlcv_path = "/Users/jedmeier/binance_06_08/BTCUSDT.csv"
    # print(csv_path)
    # ~/binance_2020_04_16/BTCUSDT.csv
    with open("./example_strat_2.json", "r") as json_file:
        strategy = json.load(json_file)

    # 1514771281
    # 1575150241610
    strategy["chart_period"] = "1h"
    strategy["start"] = "2019-01-01 00:00:00"
    strategy["stop"] = "2020-05-09 00:00:00"

    res = run_backtest(ohlcv_path, strategy)
    df = res['df']

    print(df.tail(n=20))
    print(json.dumps(res["summary"], indent=2))
    # print(df)
    # plt.figure()
    # print(res)


