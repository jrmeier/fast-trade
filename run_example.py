# flake8: noqa
from fast_trade import run_backtest
import json

strategy = {
   "name": "example",
   "chart_period": "6h",
   "start": "",
   "stop": "",
   "exit_on_end": False,
   "enter": [
     [
       "close",
       ">",
       "short"
     ]
   ],
   "exit": [
     [
       "close",
       "<",
       "long"
     ],
   ],
   "indicators": [
     {
       "name": "short",
       "func": "ta.ema",
       "args": [
         21
       ],
       "df": "close"
     },
     {
       "name": "long",
       "func": "ta.ema",
       "args": [
         21
       ],
       "df": "close"
     },

   ]
}

if __name__ == "__main__":
  datafile_path = "./BTCUSDT.csv.txt"
  
  result = run_backtest(strategy, datafile_path)

  summary = result["summary"]
  df = result["df"]

