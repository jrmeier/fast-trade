from fast_trade import run_backtest
import pandas as pd
import json

if __name__ == "__main__":
    csv_path = "/Users/jedmeier/2017_standard/BTCUSDT.csv"
    with open("./example_strat_2.json", "r") as json_file:
        strategy = json.load(json_file)
    
    strategy['chart_period'] = "15m"
    timeframe = {"start": "2018-01-01 00:00:00", "stop": "2019-12-07 00:00:00"}
    res, df = run_backtest(csv_path, strategy, timeframe)
    print(json.dumps(res, indent=2))