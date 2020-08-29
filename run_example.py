# flake8: noqa
from fast_trade import run_backtest, prepare_df
import pandas as pd
import json

strategy = {
  "chart_period": "5m",
  "enter": [
    [
      "close",
      ">",
      "mid"
    ]
  ],
  "exit": [
    [
      "close",
      "<",
      "short"
    ]
  ],
  "exit_on_end": True,
  "id": "b25101fa-636d-4537-aa9c-b62bb9fd5c13",
  "indicators": [
    {
      "args": [
        12
      ],
      "df": "close",
      "func": "ta.zlema",
      "name": "short"
    },
    {
      "args": [
        14
      ],
      "df": "close",
      "func": "ta.zlema",
      "name": "mid"
    },
    {
      "args": [
        28
      ],
      "df": "close",
      "func": "ta.zlema",
      "name": "long"
    }
  ],
  "name": "generated"
}

if __name__ == "__main__":
  datafile = "./BTCUSDT.csv.txt"
  df = pd.read_csv(datafile, parse_dates=True)
  df = prepare_df(df, strategy)
  
  test1 = run_backtest(strategy, df=df)
  # test2 = run_backtest(strategy, ohlcv_path=datafile)



  print("test1: ",test1["summary"])
  # print("test2: ",test2["summary"])

  # print(df)
