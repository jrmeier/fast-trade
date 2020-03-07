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

## Testing

```bash
python -m pytest
```

Available Indicators (graciously stolen from https://github.com/peerchemist/finta)

## Output

The output its a tuple. The first object is a summary all the inputs and a summary of a performace of the model. It's all the information to run the simulation again. The second object is a Pandas Dataframe, which contains all of the data used in the simulation. This can be used to chart store.

Example output:

```python
{
  "return_perc": 3.935,
  "mean_trade_len": "0 days 01:13:07.368421",
  "max_trade_held": "0 days 07:55:59",
  "min_trade_len": "0 days 00:07:59",
  "best_trade_perc": 5.979,
  "min_trade_perc": -3.144,
  "mean": 0.074,
  "num_trades": 58,
  "win_perc": 63.793,
  "loss_perc": 34.483,
  "equity_peak": 1098.39686619,
  "equity_final": 1044.52219673,
  "equity_peak_unit": 1098.39686619,
  "first_tic": "2018-05-01 00:00:03",
  "last_tic": "2018-05-03 23:57:03",
  "total_tics": 1081,
  "test_duration": "0:00:00.406570"
},
DataFrame(...)
)
```

## Strategy

The real goal of this project is to get to the point where these strategies can be generated and tested quickly and then be easily iterated on.

Below is an example of a very simple strategey. Basically, indicators are used to build a list of indicators to look at which must all be true to produce an enter or exit status for that tick. This can use any of the indicators [build_data_frame.py](/fast_trade/build_data_frame.py)


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
