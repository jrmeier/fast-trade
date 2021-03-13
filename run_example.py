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
            "name": "sma_shorst"
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
        ["close", ">", "sma_long_wrong"],
        ["close", ">", "sma_short"]
    ],
    "exit": [
        ["close", "<", "sma_short"],
        ["close", "<", 5]
    ],
    "trailing_stop_loss": 0.05,
    "exit_on_end": False,
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv"
    datafile = "./BTCUSDT.csv"
    tmp_start = datetime.datetime.utcnow()
    # backtest = generate_backtest()
    # print("backtest: ",json.dumps(backtest, indent=2)
    # test = run_backtest(backtest, ohlcv_path=datafile, summary=True)
    res = validate_backtest(backtest)
    print(res)
    # print(backtest["enter"])
    # print(test["trade_df"]) .
    # print(json.dumps(test["summary"], indent=2))
