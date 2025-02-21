# flake8: noqa
from fast_trade import run_backtest, prepare_df
from fast_trade.validate_backtest import validate_backtest
from fast_trade.archive.db_helpers import get_kline
import datetime

strategy = {
    "freq": "5Min",
    "any_enter": [],
    "any_exit": [],
    "enter": [
        ["rsi", "<", 30],
        ["bbands_bbands_bb_lower", ">", "close"],
    ],
    "exit": [
        ["rsi", ">", 70],
        ["bbands_bbands_bb_upper", "<", "close"],
    ],
    "datapoints": [
        {"name": "ema", "transformer": "ema", "args": [5]},
        {"name": "sma", "transformer": "sma", "args": [20]},
        {"name": "rsi", "transformer": "rsi", "args": [14]},
        {"name": "obv", "transformer": "obv", "args": []},
        {"name": "bbands", "transformer": "bbands", "args": [20, 2]},
    ],
    "base_balance": 1000.0,
    "exit_on_end": False,
    "comission": 0.0,
    "trailing_stop_loss": 0.0,
    "lot_size_perc": 1.0,
    "max_lot_size": 0.0,
    "start_date": datetime.datetime(2024, 10, 1, 0, 0),
    "end_date": datetime.datetime(2025, 2, 26, 0, 0),
    "rules": None,
    "symbol": "BTC-USDT",
    "exchange": "coinbase",
}

if __name__ == "__main__":
    # get the dataframe
    # print(res)
    df = get_kline(
        "BTCUSDT", "binanceus", start_date="2025-01-01", end_date="2025-01-31"
    )
    prepped = prepare_df(df, strategy)
    # res = validate_backtest(strategy)
    # print(res)
    # print("errors: ", res)
    # print(res.get("df").columns)
    res = run_backtest(strategy)
    import pprint

    pprint.pprint(res.get("summary"))
