# flake8: noqa
from fast_trade import run_backtest
from fast_trade.cli_helpers import save
import datetime


strategy = {
    "chart_period": "3T",
    "enter": [["price_action_1", ">", 3]],
    "exit": [["price_action_2", "<", 1]],
    "exit_on_end": False,
    "commission": 0.001,
    "indicators": [
        {"args": [80], "df": "close", "func": "ta.roc", "name": "price_action_1"},
        {"args": [10], "df": "close", "func": "ta.roc", "name": "price_action_2"},
    ],
    "start": "2020-02-01",
    "stop": "2020-02-10",
    "name": "generated",
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv.txt"
    datafile = (
        "/Users/jedmeier/Projects/fast-trade-candlesticks/gi_zip_toss/BTCUSDT_2020.csv"
    )
    tmp_start = datetime.datetime.utcnow()
    test = run_backtest(strategy, ohlcv_path=datafile, summary=False)
    tmp_stop = datetime.datetime.utcnow()
    # print(test["summary"])
    print(test["df"])
    # print(test)
