# flake8: noqa
from fast_trade import run_backtest
import datetime
import json

ds1 = "2020-06-01"
s1 = 1590969600
ms1 = 1590969600000

ds2 = "2020-07-10"
s2 = 1594339200
ms2 = 1594339200000

# backtest = {
#     "chart_period": "1T",
#     "enter": [["price_action_1", ">", 2]],
#     "exit": [["price_action_2", "<", 1]],
#     "exit_on_end": False,
#     "comission": 0.001,
#     "datapoints": [
#         {"args": [60], "df": "close", "func": "ta.roc", "name": "price_action_1"},
#         {"args": [10], "df": "close", "func": "ta.roc", "name": "price_action_2"},
#         {"args": [10], "df": "close", "func": "stop_loss", "name": "stop_loss_1"},
#     ],
#     "start": "",
#     "stop": s2,
#     "name": "generated",
#     "stop_loss": [
#         ["close", ">=", "stop_loss_1"]
#     ]
# }
backtest = {
    "base_balance": 1000,
    "chart_period": "5T",
    "chart_start": "2020-08-30 18:00:00",
    "chart_stop": "2020-09-06 16:39:00",
    "comission": 0.01,
    "datapoints": [
        {
            "args": [
                30
            ],
            "transformer": "sma",
            "name": "sma_short"
        },
        {
            "args": [
                90
            ],
            "transformer": "sma",
            "name": "sma_long"
        },
    ],
    "enter": [
        ["close", ">", "sma_long"],
        ["close", ">", "sma_short"]
    ],
    "exit": [
        ["close", "<", "sma_short"]
    ],
    "trailing_stop_loss": 0.05,
    "exit_on_end": False,
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv.txt"
    datafile = "/Users/jedmeier/Projects/fast-trade/BTCUSDT.csv.txt"
    tmp_start = datetime.datetime.utcnow()
    test = run_backtest(backtest, ohlcv_path=datafile, summary=True)
    # print(test["df"])
    print(test["trade_df"])
    print(json.dumps(test["summary"], indent=2))
