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
#     "commission": 0.001,
#     "indicators": [
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
    "base_balance": 10000.0,
    "chart_period": "15T",
    "chart_start": 1596293700000,
    "chart_stop": 1614095742000,
    "comission": 0.01,
    "created_at": 1615422604619,
    "indicators": [
        {
            "args": [
                10
            ],
            "df": "BTCUSD",
            "func": "rsi",
            "name": "BTCUSD_rsi"
        },
        {
            "args": [
                7
            ],
            "df": "BTCUSD",
            "func": "zlema",
            "name": "zlema_close"
        },
        {
            "args": [
                22, 22
            ],
            "df": "BTCUSD",
            "func":"chandelier",
            "name": "stop_loss"
        }
    ],
    "enter": [
        [
            "zlema_close",
            ">",
            "close",
            3,
        ]
    ],
    "exit": [
        [
            "stop_loss_short",
            "<",
            "close"
        ]
    ],
    "trailing_stop_loss": .20,
    "exit_on_end": True,
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv.txt"
    datafile = (
        "/Users/jedmeier/Projects/fast-trade/BTCUSDT.csv.txt"
    )
    tmp_start = datetime.datetime.utcnow()
    test = run_backtest(backtest, ohlcv_path=datafile, summary=True)
    # print(test["df"])
    print(test["trade_df"])
    print(json.dumps(test["summary"], indent=2))
