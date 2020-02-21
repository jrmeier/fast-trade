from fast_trade import run_backtest
import json
import os

# def run_backtest(csv_path, strategy, timerange={}, starting_aux_bal=1000):


if __name__ == "__main__":
    csv_path = "./BTCUSDT.csv"

    with open("./example_strat.json", "r") as strat_file:
        strategy = json.load(strat_file)


    res, df = run_backtest(csv_path, strategy)
    # print(res)
    print(json.dumps(res,indent=2))
