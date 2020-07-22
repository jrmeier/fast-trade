# Fast Trade

[![License: LGPL v3](https://img.shields.io/github/license/jrmeier/fast-trade)](https://img.shields.io/github/license/jrmeier/fast-trade)
[![PyPI](https://img.shields.io/pypi/v/fast-trade.svg?style=flat-square)](https://img.shields.io/pypi/v/fast-trade.svg?style=flat-square)
[![](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/download/releases/3.7.0/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
![Python application](https://github.com/jrmeier/fast-trade/workflows/Python%20application/badge.svg)

A library built with strategy portability and performance in mind for back-test trading strategies.

## Motivations

Strategies are cheap. This is the main motivation behind fast-trade. Since a strategy is just a JSON object, strategies can be created, stored, modified, versioned, and re-run easily. 

## Data

The data comes from this project [crypto-data](https://github.com/jrmeier/crypto-data).

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
       "",
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

Available Indicators (graciously stolen from https://github.com/peerchemist/finta)

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
