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

strategy = {
    "chart_period": "1T",
    "enter": [["price_action_1", ">", 2]],
    "exit": [["price_action_2", "<", 1]],
    "exit_on_end": False,
    "commission": 0.001,
    "indicators": [
        {"args": [60], "df": "close", "func": "ta.roc", "name": "price_action_1"},
        {"args": [10], "df": "close", "func": "ta.roc", "name": "price_action_2"},
    ],
    "start": "",
    "stop": s2,
    "name": "generated",
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv.txt"
    datafile = (
        "/Users/jedmeier/Projects/fast-trade-candlesticks/gi_zip_toss/BTCUSDT_2020.csv"
    )
    tmp_start = datetime.datetime.utcnow()
    test = run_backtest(strategy, ohlcv_path=datafile, summary=True)
    # print(test["df"])
    # print(test["trade_df"])
    print(json.dumps(test["summary"], indent=2))
