from fast_trade import run_backtest
import json

if __name__ == "__main__":
    csv_path = "/Users/jedmeier/2017_standard/BTCUSDT.csv"
    with open("./example_strat_2.json", "r") as json_file:
        strategy = json.load(json_file)

    res, df = run_backtest(csv_path, strategy)
    print(json.dumps(res, indent=2))
