# flake8: noqa
from fast_trade.build_data_frame import prepare_df
from fast_trade import run_backtest
from fast_trade.validate_backtest import validate_backtest
import datetime
import json
import pandas as pd

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
# backtest = {
#     "any_enter": [],
#     "any_exit": [],
#     "chart_period": "1H",
#     "comission": 0.00,
#     "base_balance": 100000,
#     "lot_size": 0.6,
#     "datapoints": [{"args": [], "name": "rsi_dp", "transformer": "rsi"}],
#     "enter": [
#         [
#             "rsi_dp",
#             "<",
#             30,
#         ]
#     ],
#     "exit": [
#         [
#             "rsi_dp",
#             ">",
#             70,
#         ]
#     ],
#     "exit_on_end": False,
#     "max_lot_size": 0
#     # "start": "2019-12-01 15:29:00",
#     # "stop": "2021-03-08 15:29:00",
#     # "trailing_stop_loss": 0.05,  # 5% stoploss
# }

backtest = {
    "any_enter": [],
    "any_exit": [],
    "chart_period": "1H",
    "comission": 0.01,
    "datapoints": [
        {"args": [14], "name": "er", "transformer": "er"},
        {"args": [35], "name": "zlema", "transformer": "sma"},
    ],
    "enter": [["zlema", ">", "close", 1]],
    "exit": [["zlema", "<", "close", 1]],
    "exit_on_end": False,
    # "start": "2021-01-01 22:30:00",
    # "stop": "2021-03-11 23:30:59",
    "trailing_stop_loss": 0,
    # "max_lot_size": 1000,
    "base_balance": 100,
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv"
    # datafile = "./archive/BTCUSDT_2021.csv"
    datafile = "/Users/jedmeier/Desktop/BTCUSDT_ALL/BTCUSDT_2020.csv"
    # datafile = "./AAPL.csv"
    # columns = ["date", "open", "high", "low", "close", "volume"]
    # df = pd.read_csv(datafile)
    # print(df.columns)
    # new_df = pd.DataFrame()
    # new_df["open"] = df.Open
    # new_df["high"] = df.High
    # new_df["low"] = df.Low
    # new_df["close"] = df.Close
    # new_df["volume"] = df.Volume
    # new_df.index = pd.to_datetime(df.Date, format="%Y-%M-%d")
    # new_df.index.name = "date"
    # df = prepare_df(new_df, backtest)
    # df.dropna()

    # print(df)
    # with open("./example_backtest.json", "r") as backtest_file:
    #     backtest = json.load(backtest_file)
    # print(backtest)
    # backtest["start"] = "2020-12-01"
    backtest["comission"] = 0.01
    # backtest["chart_period"] = "1Min"
    test = run_backtest(backtest, datafile, summary=True)
    # print(test)
    print(test.get("error"))
    print(json.dumps(test["summary"], indent=2))
    print(test["trade_df"])
    # print()
    # errors = validate_backtest(backtest)

    # print(errors)
