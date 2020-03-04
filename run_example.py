from fast_trade import run_backtest
import pandas as pd
import json

if __name__ == "__main__":
    csv_path = "/Users/jedmeier/2017_standard/XLMBTC.csv"
    with open("./example_strat_2.json", "r") as json_file:
        strategy = json.load(json_file)

    strategy["chart_period"] = "1h"
    strategy["start"] = "2018-01-01 00:00:00"
    strategy["stop"] = "2018-05-25 00:00:00"
    res, df = run_backtest(csv_path, strategy)
    print(json.dumps(res, indent=2))
    # print(res, df)
    # print(res)
