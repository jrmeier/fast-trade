# flake8: noqa
from fast_trade import run_backtest
import matplotlib.pyplot as plt
import pandas as pd
import json
import os


if __name__ == "__main__":
    # csv_path = "/Users/jedmeier/binance_2020_04_16/BTCUSDT.csv"
    # ohlcv_path = "/Users/jedmeier/2017_standard/BTCUSDT.csv"
    # ohlcv_path = "/Users/jedmeier/binance_06_08/BTCUSDT.csv"
    ohlcv_path = "/Users/jedmeier/Projects/fast-trade/BTCUSDT.csv"
    # print(csv_path)
    # ~/binance_2020_04_16/BTCUSDT.csv
    with open("./example_strat_2.json", "r") as json_file:
        strategy = json.load(json_file)

    # 1514771281
    # 1575150241610
    strategy["chart_period"] = "4h"
    strategy["start"] = "2020-04-15 00:00:00"
    strategy["stop"] = "2020-07-15 00:00:00"
    # strategy["base_balance"] = 100
    strategy["exit_on_end"] = False
    res = run_backtest(strategy, ohlcv_path)
    df = res["df"]
    # print(res)
    print(df.tail(n=100))
    # print(res['summary'])
    print(json.dumps(res["summary"], indent=2))
    # print(df)
    # print(res)
