# Fast Trade

[![License: LGPL v3](https://img.shields.io/github/license/jrmeier/fast-trade)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/fast-trade.svg?style=flat-square)](https://pypi.org/project/fast-trade/)
[![](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/download/releases/3.7.0/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Python application](https://github.com/jrmeier/fast-trade/workflows/Python%20application/badge.svg)](https://github.com/jrmeier/fast-trade/actions)

A library built with strategy portability and performance in mind for back-test trading strategies.

## Motivations

Strategies are cheap. This is the main motivation behind fast-trade. Since a strategy is just a JSON object, strategies can be created, stored, modified, versioned, and re-run easily. Ideally, a strategy could be generated and tested quickly; fast-trade is just the library to handle that.

## Indicators

Available Indicators (https://github.com/peerchemist/finta)

Custom indicators can be added by setting a function name in the [indicator_map](https://github.com/jrmeier/fast-trade/blob/master/fast_trade/build_data_frame.py#L141), then setting that equal to a function that takes in a dataframe as the first argument and whatever arguments passed in.

## Data
Data is expected to come with `ohlc` candlestick data in a csv file.

Example file format
```csv
date,close,open,high,low,volume
1575150241610,7525.50000000,7699.25000000,7810.00000000,7441.00000000,46477.74085300
1575150301160,7529.99000000,7693.41000000,7810.00000000,7441.00000000,46475.81690400
1575150361151,7528.93000000,7693.12000000,7810.00000000,7441.00000000,46473.78656500
1575150421124,7532.01000000,7696.08000000,7810.00000000,7441.00000000,46466.46236100
1575150481623,7530.04000000,7710.00000000,7810.00000000,7441.00000000,46455.85758200
1575150541200,7532.07000000,7720.16000000,7810.00000000,7441.00000000,46448.47469000
1575150601026,7533.69000000,7723.27000000,7810.00000000,7441.00000000,46432.03855300
1575150661595,7533.06000000,7714.92000000,7810.00000000,7441.00000000,46407.97286100
1575150721337,7529.04000000,7708.14000000,7810.00000000,7441.00000000,46409.79564500
```

A dataframe can also be passed to `run_backtest(...)` function such as `run_backtest(strategy, df=<your data frame>)`.

I've been using this project to collect and store tick data [crypto-data](https://github.com/jrmeier/crypto-data).

## Install

```bash
pip install fast-trade
```

Or

```bash
python -m venv .fast_trade
source .fast_trade/bin/activate
pip install -r requirements.txt
```

## Usage

```python
from fast_trade import run_backtest

strategy = {
   "name": "example",
   "chart_period": "1h",
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
         50
       ],
       "df": "close"
     },

   ]
}

datafile_path = "./BTCUSDT.csv.txt"

# returns the summary object and the dataframe
result = run_backtest(strategy, datafile_path)

summary = result["summaray"]
df = result["df"]

print(summary)
print(df.head())
```

## CLI

You can also use the package from the command line.

```ft help```

To run a backtest, the csv datafile needs to be passed in, along with the strategy file. On the command line, anything passed in can be overwritten with an argument and value. For example, the chart_period can be overwritten from the strat file by just passing it in. This will print out a summary of the backtest

Basic usage

```ft backtest --csv=./BTCUSDT.csv --strat=./example_strat.json```

Modifying the ```chart_period```

```ft backtest --csv=./datafile.csv --strat=./strat.json --chart_period=1h```

Saving a test result
This generates creates the `saved_backtest` directory (if it doesn't exist), then inside of there, is another directory with a timestamp, with a chart, the strategy file, the summary, and the raw dataframe as a csv.

```ft backtest --csv=./datafile.csv --strat=./strat.json --save```

Viewing a plot of the result

```ft backtest --csv=./datafile.csv --strat=./strat.json --plot```

## Testing

```bash
python -m pytest
```

## Output

The output its a dictionary. The summary is a summary all the inputs and of the performace of the model. It's all the information to run the simulation again. The df is a Pandas Dataframe, which contains all of the data used in the simulation.

Example output:

```python
{
  "summary":
    {
      "return_perc": -6.478, # total return percentage
      "meadian_trade_len: ""
      "mean_trade_len": 147445.013888888, # mean trade length, in seconds
      "max_trade_held": 619920.0, # longest trade held length, in seconds
      "min_trade_len": 28799.0, # shortest trade held length, in seconds
      "best_trade_perc": 13.611,
      "min_trade_perc": -18.355,
      "mean": 0.083,
      "num_trades": 73,
      "win_perc": 58.904,
      "loss_perc": 39.726,
      "equity_peak": 1117.3126272,
      "equity_final": 935.2209955,
      "equity_peak_unit": 1117.3126272,
      "first_tic": "2018-01-01 01:48:01",
      "last_tic": "2018-05-03 22:43:02",
      "total_tics": 720,
      "test_duration": 0.420136
    },
    "df": DataFrame(...)
}
```

## Strategy

The real goal of this project is to get to the point where these strategies can be generated and tested quickly and then be easily iterated on.

Below is an example of a very simple strategey. Basically, indicators are used to build a list of indicators to look at which must all be true to produce an enter or exit status for that tick.


```python
{
   "name": "example",
   "chart_period": "4m",
   "start": "2018-05-01 00:00:00",
   "stop": "2018-05-04 00:00:00",
   "enter": [
     [
       "close",
       ">",
       "short"
     ],
     [
       "rsi",
       ">",
       30
     ]
   ],
   "exit": [
     [
       "close",
       "<",
       "long"
     ],
     [
       "rsi",
       "<",
       70
     ]
   ],
   "indicators": [
     {
       "name": "short",
       "func": "ta.zlema",
       "args": [
         7
       ],
       "df": "close"
     },
     {
       "name": "long",
       "func": "ta.zlema",
       "args": [
         150
       ],
       "df": "close"
     },
     {
       "name": "rsi",
       "func": "ta.rsi",
       "args": [
         14
       ],
       "df": "close"
     }
   ]
}
```

### Indicators

```python
      {
         "name": "short", # indicator name
         "func": "ta.zlema", # technical analysis function to be used
         "args": [12], # arguments to pass to the function
         "df": "close" # which column of the dataframe to look at
      }
```

### Enter / Exit

```python
   "enter": [ # all must be true to enter or exit
      [
         "close", # column of the dataframe to compare to
         ">", # logic to use to compare
         "short" # the name from the defined indicator
      ]
   ]
```
