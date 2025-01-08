# flake8: noqa
from fast_trade import run_backtest
from fast_trade.archive.db_helpers import get_kline

strategy = {
    "base_balance": 1000,
    "freq": "1h",
    "start_date": "2024-06-01",
    "end_date": "2024-12-31",
    "comission": 0.1,
    "datapoints": [
        {
            "args": [20],
            "transformer": "rolling_max",
            "name": "highest_high",
            "column": "high",
        },
        {
            "args": [15],
            "transformer": "rolling_min",
            "name": "lowest_low",
            "column": "low",
        },
    ],
    "enter": [["high", ">=", "highest_high"]],
    "exit": [["close", "<=", "lowest_low"]],
    "exit_on_end": True,
    "exchange": "binanceus",
    "symbol": "BTCUSDT",
}

if __name__ == "__main__":
    # get the dataframe
    # df = get_kline("BTCUSDT", "binanceus", start="2024-09-01", end="2024-12-31")
    # print(df)
    res = run_backtest(strategy)
    print(res.get("summary"))
    # print(res.keys())
    print(res.get("df"))

    # start = "2024-12-19 22:23:00"
    # stop = "2024-12-30 00:00:00"

    # print(res.tail())
