# flake8: noqa
from fast_trade.build_data_frame import prepare_df
from fast_trade import run_backtest
from fast_trade.validate_backtest import validate_backtest
from fast_trade.check_missing_dates import check_missing_dates
import datetime
import json
import pandas as pd
import matplotlib.pyplot as plt

ds1 = "2020-06-01"
s1 = 1590969600
ms1 = 1590969600000

ds2 = "2020-07-10"
s2 = 1594339200
ms2 = 1594339200000

# if(rsi > 70 | rsi < 30) :

# result = myprediction(data)

# switch(result):

# case 0: hold

# case 1: sell

# case 2: buy
backtest = {
    "any_enter": [],
    "any_exit": [],
    "chart_period": "1H",
    "comission": 0.00,
    "base_balance": 100000,
    "lot_size": 0.6,
    "datapoints": [{"args": [], "name": "rsi_dp", "transformer": "rsi"}],
    "enter": [
        [
            "rsi_dp",
            "<",
            30,
        ]
    ],
    "exit": [
        [
            "rsi_dp",
            ">",
            70,
        ]
    ],
    "exit_on_end": False,
    "max_lot_size": 0
    # "start": "2019-12-01 15:29:00",
    # "stop": "2021-03-08 15:29:00",
    # "trailing_stop_loss": 0.05,  # 5% stoploss
}

# backtest = {
#     "any_enter": [],
#     "any_exit": [],
#     # "chart_period": "37Min",
#     "chart_period": "11Min",
#     "comission": 0.01,
#     "datapoints": [
#         {"args": [14], "name": "er", "transformer": "er"},
#         {"args": [14], "name": "zlema_1", "transformer": "zlema"},
#         {"args": [66], "name": "zlema_2", "transformer": "zlema"},
#     ],
#     "enter": [["zlema_1", ">", "close", 1]],
#     "exit": [["zlema_2", "<", "close", 1]],
#     "exit_on_end": False,
#     # "start": "2021-01-01 22:30:00",
#     # "stop": "2021-03-11 23:30:59",
#     "trailing_stop_loss": 0.05,
#     # "max_lot_size": 1000,
#     "lot_size": 1,
#     "base_balance": 500,
# }
# backtest = {
#     "any_enter": [],
#     "any_exit": [],
#     "chart_period": "30Min",
#     "comission": 0.001,
#     "datapoints": [{"args": [22], "name": "hma", "transformer": "hma"}],
#     "enter": [["close", "<", "hma", 1]],
#     "exit": [["close", ">", "hma", 1]],
#     "exit_on_end": False,
#     "start": "2021-05-01 23:03:00",
#     # "stop": "2021-06-01 00:03:00",
#     "trailing_stop_loss": None,
# }
if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv"
    # datafile = "./archive/BTCUSDT_2021.csv"
    datafile = "/Users/jedmeier/Desktop/BTCUSDT_ALL/BTCUSDT_2021.csv"
    # datafile = "/Users/jedmeier/Desktop/BTCUSDT_2021_06_12.csv"
    # datafile = "./archive/BCHUSDT_2021.csv"

    # df = pd.read_csv(datafile)

    # df.index = pd.to_datetime(df.date, unit="s")
    # print(df)
    # check_missing_dates(df)
    # with open("./example_backtest.json", "r") as backtest_file:
    #     backtest = json.load(backtest_file)
    # print(backtest)
    # backtest["start"] = "2021-03-01"
    # backtest["stop"] = "2021-05-01"

    # backtest["chart_period"] = "1Min"
    test = run_backtest(backtest, datafile, summary=True)
    # print(test)
    df = test["trade_df"]

    print(df)
    print(json.dumps(test["summary"], indent=2))
