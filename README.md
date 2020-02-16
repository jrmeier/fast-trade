# Fast Trade ![Python application](https://github.com/jrmeier/fast-trade/workflows/Python%20application/badge.svg)

A library to do back-testing on currency data with generated strategies quickly and easily. The data comes from this project [crypto-data](https://github.com/jrmeier/crypto-data). 

## Data

If you're looking for some data, here is almost every minute of 2018 of every pair from binance. Here is the each file [individually zipped](https://drive.google.com/file/d/16eoeNLTUVC9ydoMfVtjxxfLPKurGW05M/view?usp=sharing) and here is the [entire directory zipped, with each file as a zip](https://drive.google.com/file/d/16eoeNLTUVC9ydoMfVtjxxfLPKurGW05M/view?usp=sharing). If you have any questions, please email me at fast_trade (at) jedm.dev.

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
(
{
  "start_time": "2018-02-06 00:03:03",
  "time_time": "2018-02-06 23:59:03",
  "time_spent": "0:00:00.506799",
  "total_trades": 73,
  "total_tics": 288,
  "max_gain_perc": 6.589,
  "strategy": {
    "name": "example",
    "chart_period": "5m",
    "start": "",
    "stop": "",
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
        "func": "ta.ema",
        "args": [
          7
        ],
        "df": "close"
      },
      {
        "name": "mid",
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
  },
  "base_sum": {
    "start": 0,
    "end": 0.1392501,
    "max": 0.0
  },
  "aux_sum": {
    "start": 1000,
    "end": 0.0,
    "max": 1070.53608431
  }
},
DataFrame(...)
)
```

## Strategy

The real goal of this project is to get to the point where these strategies can be generated and tested quickly and then be easily iterated on.

Below is an example of a very simple strategey. Basically, indicators are used to build a list of indicators to look at which must all be true to produce an enter or exit status for that tick. This can use any of the indicators [build_data_frame.py](/fast_trade/build_data_frame.py)


```javascript
{
   "name": "example", // name or identifier of strategy
   "chart_period": "15m", // charting period
   "enter": [ // conditions required to ENTER a trade, all must be true
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
   "exit": [ // conditions required to EXIT a trade, all must be true
      [
         "close",
         "<",
         "mid"
      ],
      [
         "rsi",
         "<",
         60
      ]
   ],
   "indicators": [ // this is what you use in the enter/exit functions
      {
         "name": "short",
         "func": "ta.sma",
         "args": [7],
         "df": "close"
      },
      {
         "name": "mid",
         "func": "ta.sma",
         "args": [21],
         "df": "close"
      },
      {
         "name": "long",
         "func": "ta.sma",
         "args": [150],
         "df": "close"
      },
      {
         "name": "rsi",
         "func": "ta.rsi",
         "args": [14],
         "df": "close"
      }
   ]
}

```

### Indicators

```javascript
      {
         "name": "short", // indicator name
         "func": "ta.ema", // technical analysis function to be used
         "args": [12], // arguments to pass to the function
         "df": "close" // which column of the dataframe to look at
      }
```

### Enter / Exit

```javascript
   "enter": [
      [
         "close", // column of the dataframe to compare to
         ">", // logic to use to compare
         "short" // the name from the defined indicator
      ]
   ]
```
