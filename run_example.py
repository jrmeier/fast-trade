# flake8: noqa
from fast_trade import run_backtest, build_data_frame
import matplotlib.pyplot as plt
import pandas as pd
import json
import os


if __name__ == "__main__":
    ohlcv_path = ["/Users/jedmeier/Projects/fast-trade/BTCUSDT.csv"]

    with open("./example_strat_2.json", "r") as json_file:
        strategy = json.load(json_file)


    strategy['chart_period'] = "1h"
    res = run_backtest(strategy, ohlcv_path)

    summary = res['summary']

    print(json.dumps(summary, indent=2))