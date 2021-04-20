# flake8: noqa
from fast_trade import run_backtest
from fast_trade.validate_backtest import validate_backtest
import datetime
import json

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
#     "datapoints": [
#         {
#             "args": [

#             ],
#             "name": "rsi_dp",
#             "transformer": "rsi"
#         }
#     ],
#     "enter": [
#         [
#             "rsi_dp",
#             "<",
#             30,
#         ]
#     ],
#     "exit": [
#             [
#                 "rsi_dp",
#                 ">",
#                 70,
#             ]
#     ],
#     "exit_on_end": False,
#     # "start": "2019-12-01 15:29:00",
#     # "stop": "2021-03-08 15:29:00",
#     "trailing_stop_loss": 0.05   # 5% stoploss
# }

backtest = {
    "any_enter": [],
    "any_exit": [],
    "chart_period": "15Min",
    "comission": 0,
    "datapoints": [
        {
            "args": [
                    14
            ],
            "name": "er",
            "transformer": "er"
        },
        {
            "args": [
                13
            ],
            "name": "zlema",
            "transformer": "zlema"
        }
    ],
    "enter": [
        [
            "zlema",
            ">",
            "close",
            1
        ]
    ],
    "exit": [
            [
                "er",
                "<",
                0,
                1
            ]
    ],
    "exit_on_end": False,
    "start": "2021-01-01 22:30:00",
    "stop": "2021-03-11 23:30:59",
    "trailing_stop_loss": 0
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv"
    datafile = "./archive/BTCUSDT_2021.csv"
    # test = run_backtest(backtest, ohlcv_path=datafile, summary=True)
    # print(test["summary"])
    errors = validate_backtest(backtest)

    print(errors)
