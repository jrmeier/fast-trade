# flake8: noqa
from fast_trade import run_backtest
from fast_trade.cli_helpers import save

strategy = {
    "chart_period": "15T",
    "enter": [["close", ">", "long"]],
    "exit": [["close", "<", "short"]],
    "exit_on_end": False,
    "commission": 0.001,
    "id": "b25101fa-636d-4537-aa9c-b62bb9fd5c13",
    "indicators": [
        {"args": [12], "df": "close", "func": "ta.zlema", "name": "short"},
        {"args": [14], "df": "close", "func": "ta.zlema", "name": "mid"},
        {"args": [28], "df": "close", "func": "ta.zlema", "name": "long"},
    ],
    "start": "2020-02-01",
    "stop": "2020-06-01",
    "name": "generated",
}

if __name__ == "__main__":
    # datafile = "./BTCUSDT.csv.txt"
    datafile = (
        "/Users/jedmeier/Projects/fast-trade-candlesticks/gi_zip_toss/BTCUSDT_2020.csv"
    )

    test = run_backtest(strategy, ohlcv_path=datafile)
    # print(test["summary"])
    # print(test["df"])
    # save(test, strategy)
