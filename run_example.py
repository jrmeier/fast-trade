# flake8: noqa
from fast_trade import run_backtest
from fast_trade.cli_helpers import save

strategy = {
    "chart_period": "15T",
    "enter": [["close", ">", "mid"]],
    "exit": [["close", "<", "short"]],
    "exit_on_end": True,
    "commission": 0.001,
    "id": "b25101fa-636d-4537-aa9c-b62bb9fd5c13",
    "indicators": [
        {"args": [12], "df": "close", "func": "ta.zlema", "name": "short"},
        {"args": [14], "df": "close", "func": "ta.zlema", "name": "mid"},
        {"args": [28], "df": "close", "func": "ta.zlema", "name": "long"},
    ],
    "start": "2020-09-01",
    "name": "generated",
}

if __name__ == "__main__":
    datafile = "./BTCUSDT.csv.txt"

    test = run_backtest(strategy, ohlcv_path=datafile)
    print(test["summary"])
    # save(test, strategy)
