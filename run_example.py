# flake8: noqa
from fast_trade import run_backtest, prepare_df
import pandas as pd
import json
import datetime
from generate_strategy import generate_strategy

strategy = {
    "chart_period": "1m",
    "enter": [["close", ">", "mid"]],
    "exit": [["close", "<", "short"]],
    "exit_on_end": False,
    "commission": 0.001,
    "id": "b25101fa-636d-4537-aa9c-b62bb9fd5c13",
    "indicators": [
        {"args": [12], "df": "close", "func": "ta.zlema", "name": "short"},
        {"args": [14], "df": "close", "func": "ta.zlema", "name": "mid"},
        {"args": [28], "df": "close", "func": "ta.zlema", "name": "long"},
    ],
    # "start": "2020-07-15",
    "name": "generated",
}

if __name__ == "__main__":
    datafile = "./BTCUSDT.csv.txt"

    # strat = generate_strategy()
    # strat["start"] = "2020-01-15"
    test = run_backtest(strategy, ohlcv_path=datafile)

    df = test["df"]

    print(test["summary"])
    print(df)
