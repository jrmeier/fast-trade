# Fast Trade ![Python application](https://github.com/jrmeier/fast-trade/workflows/Python%20application/badge.svg)

A library to do back-testing on currency data with generated strategies quickly and easily. The data comes from this project [crypto-data](https://github.com/jrmeier/crypto-data). 

## Data

If you're looking for some data, here is roughly every minute of 2018 of every pair from binance. Here is the each file [individually zipped](https://drive.google.com/file/d/16eoeNLTUVC9ydoMfVtjxxfLPKurGW05M/view?usp=sharing) and here is the [entire directory zipped, with each file as a zip](https://drive.google.com/file/d/16eoeNLTUVC9ydoMfVtjxxfLPKurGW05M/view?usp=sharing). If you have any questions, please email me at fast_trade (at) jedm.dev. I also have data every minute since December 2019 to now, shoot me an email if you'd like access.

## Goals

- run in less than 30s on average hardware
- headless
- extensible

## Features

- Extremely fast backtesting
- ability to build complex strategies
- ability to reproduce strategies since they are just a json file
- can interface easily as an API, ex. put a web server in front and its an API

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

## CLI

You can also use the package from the command line.

```ft help```

To run a backtest, the csv datafile needs to be passed in, along with the strategy file. On the command line, anything passed in can be overwritten with an argument and value. For example, the chart_period can be overwritten from the strat file by just passing it in. This will print out a summary of the backtest

Basic usage

```ft backtest --csv=./path/to/datafile --strat=./path/to/strat.json```

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
