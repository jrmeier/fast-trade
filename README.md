# Fast Trade

A library to do back-testing on currency data with generated strategies quickly and easily. The data comes from this project [crypto-data](https://github.com/jrmeier/crypto-data). 

## Goals

- run in less than 30s on average hardware
- headless
- extensible

## Install

```bash
python -m venv .fast_trade
source .fast_trade/bin/activate
pip install -r requirements.txt
```

Available Indicators (graciously stolen from https://github.com/peerchemist/finta)

## Output

This creates a directory named run_DATE. In here, are a `RunSummary.json` which shows the run and how it performs, `NAME_strat.json`, which is the stategy that was used, and the logs from how each of those pairs performed. This tends to generate a largish amount of data, depending on how long you're backtesting for.

## Strategy

The real goal of this project is to get to the point where these strategies can be generated with a generative neural network and be specific to each cryptocurrency and any other patterns that may exist.

Below is an example of a very simple strategey. Basically, indicators are used to build a list of indicators to look at which must all be true to produce an enter or exit status for that tick. This can use any of the indicators listed in the [indicator_map.py](https://github.com/jrmeier/fast_trade/blob/master/fast_trade/indicator_map.py) file.


```json
{
   "name": "example",
   "enter": [
      [
         "close",
         ">",
         "mid"
      ],
      [
         "close",
         ">",
         "long"
      ]
   ],
   "exit": [
      [
         "close",
         "<",
         "short"
      ]
   ],
   "indicators": [
      {
         "name": "short",
         "func": "ta.ema",
         "timeperiod": "21m",
         "df": "close"
      },
      {
         "name": "mid",
         "func": "ta.ema",
         "timeperiod": "1h",
         "df": "close"
      },
      {
         "name": "long",
         "func": "ta.ema",
         "timeperiod": "4h",
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
         "timeperiod": "21m", // number of ticks to process. Default is minutes, but "d" (days) and "h" (hours) are avaliable
         "df": "close" // which column of the dataframe to look at
      }
```

### Enter / Exit

```javascript
   "enter": [
      [
         "close", // part of the dataframe to compare to
         ">", // logic to use to compare
         "short" // the name from the defined indicator
      ]
   ]
```
