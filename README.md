# Fast Trade

A library to do back-testing on currency data with generated strategies quickly and easily. The data comes from this project [crypto-data](https://github.com/jrmeier/crypto-data). One this that is missing is determining if the stratey was successful or not. All this libary produces is a log of what decision this strategy would make at this time. It provides no way to "score" the strategy. That's being worked on but isn't implimented yet.

## Data

If you're looking for some data, here is almost every minute of 2017 of every pair from binance. Here is the each file [individually zipped] (https://drive.google.com/file/d/16eoeNLTUVC9ydoMfVtjxxfLPKurGW05M/view?usp=sharing) and here is the [entire directory zipped, with each file as a zip](https://drive.google.com/file/d/16eoeNLTUVC9ydoMfVtjxxfLPKurGW05M/view?usp=sharing). If you have any questions, please email me at fast_trade (at) jedm.dev.

## Goals

- run in less than 30s
- outputs in the form of JSON or CSV
- headless

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
         "mid"
      ]
   ],
   "indicators": [
      {
         "ref": "short",
         "name": "ta.ema",
         "timeperiod": 21,
         "df": "close"
      },
      {
         "ref": "mid",
         "name": "ta.ema",
         "timeperiod": 42,
         "df": "close"
      },
      {
         "ref": "long",
         "name": "ta.ema",
         "timeperiod": 84,
         "df": "close"
      }
   ]
}
```

### Indicators

```javascript
      {
         "ref": "short", // indicator to be referred to
         "name": "ta.ema", // technical analysis function name to be used
         "timeperiod": 21, // number of ticks to process
         "df": "close" // which column of the dataframe to look at
      }
```

### Enter / Exit

```javascript
   "enter": [
      [
         "close", // part of the dataframe to compare to
         ">", // logic to use to compare
         "short" // the ref from the defined indicator
      ]
   ]
```
