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

Available Indicators [FinTA](https://github.com/peerchemist/finta)

Custom indicators can be added by setting a function name in the [indicator_map](https://github.com/jrmeier/fast-trade/blob/master/fast_trade/build_data_frame.py#L141), then setting that equal to a function that takes in a dataframe as the first argument and whatever arguments passed in.

## Data

Data must be minute tick data. Indicators will give false results if the data isn't once a minute.

Datafiles are expected but come with `ohlc` candlestick minute data in a csv file, but will not work as expected. Please open an issue if this is a problem for you.

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
   "chart_period": "1H",
   "start": "",
   "stop": "",
   "exit_on_end": False,
   "commission": 0.001,
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

summary = result["summary"]
df = result["df"]
trade_log_df = result["trade_log]

print(summary)
print(df.head())
```

## CLI

You can also use the package from the command line.

`ft help`

To run a backtest, the csv datafile needs to be passed in, along with the strategy file. On the command line, anything passed in can be overwritten with an argument and value. For example, the chart_period can be overwritten from the strat file by just passing it in. This will print out a summary of the backtest

Basic usage

`ft backtest --csv=./BTCUSDT.csv --strat=./example_strat.json`

Modifying the `chart_period`

`ft backtest --csv=./datafile.csv --strat=./strat.json --chart_period=1h`

Saving a test result
This generates creates the `saved_backtest` directory (if it doesn't exist), then inside of there, is another directory with a timestamp, with a chart, the strategy file, the summary, and the raw dataframe as a csv.

`ft backtest --csv=./datafile.csv --strat=./strat.json --save`

Viewing a plot of the result

`ft backtest --csv=./datafile.csv --strat=./strat.json --plot`

## Testing

```bash
python -m pytest
```

## Output

The output its a dictionary. The summary is a summary all the inputs and of the performace of the model. The df is a Pandas Dataframe, which contains all of the data used in the simulation. And the `trade_df` is a subset of the `df` frame which just has all the rows when there was an event. The `strategy` object is also returned, with the details of how the backtest was run.

Example output:

```python
{
  "summary":
    {
      "return_perc": -6.478, # total return percentage
      "buy_and_hold_perc": 14.699, # the return perc if comparing the first price to the last price
      "median_trade_len": 29999.00115, # median length of trade, in seconds
      "mean_trade_len": 147445.013888888, # mean trade length, in seconds
      "max_trade_held": 619920.0, # longest trade held length, in seconds
      "min_trade_len": 28799.0, # shortest trade held length, in seconds
      "best_trade_perc": 13.611, # highest trade percent
      "min_trade_perc": -18.355, # lowest trade percent
      "mean_trade_perc": 0.083, # mean trade percentage
      "num_trades": 73, # number of trade
      "win_perc": 58.904, # amount of winning trade percentages
      "loss_perc": 39.726, # amount of losing trade percentages
      "equity_peak": 1117.3126272, # most amount of equity
      "equity_final": 935.2209955, # ending amount of equity
      "first_tic": "2018-01-01 01:48:01", # first tic date in the backtest
      "last_tic": "2018-05-03 22:43:02", # last tic date in the backtest
      "total_tics": 720, # total number of dates
      "test_duration": 0.420136 # amount of time test took
    },
    "df": DataFrame(...), # dataframe used in the backtest
    "trade_df": DateFrame(...), # a subset of the main dataframe only containing the rows with trades
    "strategy": {...}, # the strategy object
}
```

## Strategy

The real goal of this project is to get to the point where these strategies can be generated and tested quickly and then be easily iterated on.

Below is an example of a very simple strategey. Basically, indicators are used to build a list of indicators to look at which must all be true to produce an enter or exit status for that tick.

Strategies include all the instructions needed to run the backtest minus the data.

### Strategy Requirements

- name:
  - string, optional
  - default: `None`
  - description: a string for quick reference of the strategy
- chart_period:
  - string, optional
  - default: `"1Min"`
  - description: a charting period string. See [here](https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#dateoffset-objects) for allowed strings.
  - Ex.
    - "1Min" is 1 minute
    - "2H" is 2 hours
    - "5D" is 5 days
- start: string

  - optional,
  - default: `""`
  - description: The time string of when to start the backtest with `%Y-%m-%d %H:%M:%S` date format.
  - Ex.
    - `"2018-05-01 00:00:00"` May 1st, 2018 at midnight

- stop: string

  - optional
  - default: `""`
  - description: The time string of when to stop the backtest with `%Y-%m-%d %H:%M:%S` date format.
  - Ex.
    - `"2020-12-28 00:08:00"` December 28th, 2020 at 8am.

- base_balance: float

  - optional
  - default: 1000
  - description: The starting balance of trade account. Usually \$ or "base" coins for cryptocurrencies.

- commission: float

  - optional
  - defaut: 0.0
  - description: The "trading fee" per trade. This is subtracted per trade.

- enter: list,

  - required
  - default: `None`
  - description: This describes requirements the send a buy signal ("enter" a trade). There can be any number of items (what I'm calling "logiz") in here. Each `logiz` is contains a single `if` statement. The two variables are the first and last items in the list, with the operator to compare them `>`, `<` `=`.

- exit: list

  - required
  - default: `None`
  - description: This describes requirements the send a sell signal ("exit" a trade). There can be any number of items (what I'm calling "logiz") in here. Each `logiz` is contains a single `if` statement. The two variables are the first and last items in the list, with the operator to compare them `>`, `<` `=`.

- indicators: list
  - optional
  - default: `None`
  - description: This describes how to create the indicators. Each individual indicator has name that can be referenced in either the `enter` or `exit` logizs. For more information, see ([Indicators Detail](###IndicatorsDetail))

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

### IndicatorsDetail

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
