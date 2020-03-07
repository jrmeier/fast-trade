from fast_trade import run_backtest
import pandas as pd
import json

if __name__ == "__main__":
    csv_path = "/Users/jedmeier/2017_standard/XLMBTC.csv"
    with open("./example_strat_2.json", "r") as json_file:
        strategy = json.load(json_file)

    strategy["chart_period"] = "4m"
    strategy["start"] = "2018-05-01 00:00:00"
    strategy["stop"] = "2018-05-04 00:00:00"
    res, df = run_backtest(csv_path, strategy)
    print(json.dumps(res, indent=2))
    # print(df.tail(n=10))
    # df.to_csv("tmp.csv")
