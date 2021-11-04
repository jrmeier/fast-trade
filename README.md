# Fast Trade

[![License: LGPL v3](https://img.shields.io/github/license/jrmeier/fast-trade)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/fast-trade.svg?style=flat-square)](https://pypi.org/project/fast-trade/)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/download/releases/3.7.0/)
[![Python application](https://github.com/jrmeier/fast-trade/workflows/Python%20application/badge.svg)](https://github.com/jrmeier/fast-trade/actions)

A library built with backtest portability and performance in mind for backtest trading strategies. There is also a [DataDownloader](#DataDownloader), which can be used to download compatible kline data from Binance (.com or .us)

## Beta Testing
I'm using this library to build a platform (live data, charting, paper trading, etc.) and I'm looking for beta testers. If you like this library, send me an email at fasttrade@jedm.dev.

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

## Contributing

If you'd like to add a feature, fix a bug, or something else, please clone the repo and fork it. When you're ready, open a PR into this main repo.

To get started with local dev, clone the repo, set up a virtual env, source it, then install the dev requirements.

```bash
git clone git@github.com:<YOUR GIT USERNAME>/fast-trade.git
cd ./fast-trade
python -m venv .fast_trade
source .fast_trade/bin/activate
pip install -r dev_requirements.txt
```

To generate testing coverage, run

```bash
coverage run -m pytest
coverage report -m
```

## Motivations

Strategies are cheap. This is the main motivation behind fast-trade. Since a backtest is just a JSON object, strategies can be created, stored, modified, versioned, and re-run easily. Ideally, a backtest could be generated and tested quickly; fast-trade is just the library to handle that.
Fast Trade is also useful for quickly analyzing chart (`ohlcv`) data and downloading it.

## Transfomers (Technical Indicators)

Available transformer functions are from [FinTA](https://github.com/peerchemist/finta)

Custom datapoints can be added by setting a function name in the [datapoints](/fast_trade/transformers_map.py), then setting that equal to a function that takes in a dataframe as the first argument and whatever arguments passed in.

Note:
  
If a transfomer function returns multiple values, the will be datapoints with the `datapointName_respective column.

Example

Say we have a datapoint that uses the transformer `bbands`.

`bbands` returns 3 columns `upper_bb, middle_band, lower_bb`

So when we want to reference these in our logic, the names we use in the logics are `bbands_upper_bb`, `bbands_middle_bb`,`bbands_lower_bb`

## Data

[DataDownloader](#DataDownloader) for those details.

I use minute kline data, but end-of-day data can be used as well. If you set a lower `chart_period` than the actual data frequency, fast-trade will throw an `Exception`.

Datafiles are expected but come with `ohlcv` candlestick minute data in a csv file, but will not work as expected. Please open an issue if this is a problem for you.

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

A dataframe can also be passed to `run_backtest(...)` function such as `run_backtest(backtest, df=<your data frame>)`.

## Usage

Example Backtest

```python
from fast_trade import run_backtest, validate_backtest

{
    "base_balance": 1000, # start with a balance of 1000
    "chart_period": "5T", # time period selected on the chard
    "chart_start": "2020-08-30 18:00:00", # when to start the chart
    "chart_stop": "2020-09-06 16:39:00", # when to stop the chart
    "comission": 0.01, # a comission to pay per transaction 
    "datapoints": [ # describes the data to use in the logic
        {
            "args": [ # args are passed to the transformer function
                30
            ],
            "transformer": "sma", # technical analysis function to run
            "name": "sma_short" # reference point for use in logic
        },
        {
            "args": [
                90
            ],
            "transformer": "sma",
            "name": "sma_long"
        },
    ],
    "enter": [
      [
        "close", # field to reference, by default this is any column in the data file. Could also be a float or int
        ">", # operator to compare these to
        "sma_long" # name of datapoint that was prevously defined
      ],
      [
        "close",
        ">",
        "sma_short"
      ]
    ],
    "exit": [
      [
        "close",
        "<",
        "sma_short"
      ]
    ],
    "trailing_stop_loss": 0.05, # optional trailing stop loss 
    "exit_on_end": False, # at then end of the backtest, if true, the trade will exit
}

# returns a mirror of the object, with errors if any
print(validate_backtest(backtest))

datafile_path = "./BTCUSDT.csv"

# returns the summary object and the dataframe
result = run_backtest(backtest, datafile_path)

summary = result["summary"]
df = result["df"]
trade_log_df = result["trade_log]

print(summary)
print(df.head())
```

## CLI

You can also use the package from the command line.

`ft help`

### Basic usage

Validate a backtest

`ft validate --backtest=./example_backtest.json`

```json
{
  "base_balance": null,
  "chart_period": null,
  "chart_start": null,
  "chart_stop": null,
  "comission": null,
  "datapoints": null,
  "enter": {
    "error": true,
    "msgs": [
      "Datapoint \"closes\" referenced in enter logic not found in datapoints. Check datapoints and logic."
    ]
  },
  "exit": null,
  "any_enter": null,
  "any_exit": null,
  "trailing_stop_loss": null,
  "exit_on_end": null
}
```

Using a custom file

`ft backtest --data=./BTCUSDT.csv --backtest=./example_backtest.json`

Using an archive item managed by the DataDownloader. Just pass in the symbol instead of the path.

`ft backtest --data=BTCUSDT --backtest=./example_backtest.json`

Modifying the `chart_period`

`ft backtest --data=./datafile.csv --backtest=./backtest.json --chart_period=1h`

Saving a test result
This generates creates the `saved_backtest` directory (if it doesn't exist), then inside of there, is another directory with a timestamp, with a chart, the backtest file, the summary, and the raw dataframe as a csv.

`ft backtest --data=./datafile.csv --backtest=./backtest.json --save`

Viewing a plot of the result

`ft backtest --data=./datafile.csv --backtest=./backtest.json --plot`

### DataDownloader

Download 1 minute kline/ohlcv from Binance and store them in CSVs in the `archive` path. You can rerun this command to keep the files updated.
It may take awhile to download all of the data the first time, so be patient. It only need to download all of it once, then it will be updated from the most recent date.
Check out the file [update_symbol_data.py](/fast_trade/update_symbol_data.py) if you want to see how it works.

`ft download --symbol=SYMBOL --exchange=EXCHANGE --start=START --end=END --archive=ARCHIVE`

Defaults are:

```python

SYMBOL="BTCUSDT" # any symbol on the exchange
EXCHANGE="binance.com" # can be binance.us
START="2017-01-01" # the start date of when you want date. This default is the oldest for binance.com.
END='current date' # you'll probably never need this
ARCHIVE='./archive' # path the archive folder, which is where the CSVs are stored
```

Examples

downloads according to the defaults

`ft download`

download data for the symbol LTCBTC using the other defaults

`ft download --symbol=LTCBTC`

download data starting January 2021
`ft download --start=2021-01-01`

## Testing

```bash
python -m pytest
```

## Coverage

```bash
coverage run -m pytest
coverage report -m
```

## Output

The output its a dictionary. The summary is a summary all the inputs and of the performace of the model. The df is a Pandas Dataframe, which contains all of the data used in the simulation. And the `trade_df` is a subset of the `df` frame which just has all the rows when there was an event. The `backtest` object is also returned, with the details of how the backtest was run.

Example output:

```python
{
  "return_perc": -3.608,
  "sharpe_ratio": -0.018705921376959495,
  "buy_and_hold_perc": -13.661,
  "median_trade_len": 1260.0,
  "mean_trade_len": 1430.121951,
  "max_trade_held": 4680.0,
  "min_trade_len": 360.0,
  "total_num_winning_trades": 46,
  "total_num_losing_trades": 119,
  "avg_win_per": 0.134,
  "avg_loss_per": -0.081,
  "best_trade_perc": 0.592,
  "min_trade_perc": -2.588,
  "median_trade_perc": -0.01,
  "mean_trade_perc": -0.021,
  "num_trades": 165,
  "win_perc": 27.879,
  "loss_perc": 72.121,
  "equity_peak": 10053.901,
  "equity_final": 9651.792,
  "max_drawdown": 9651.792,
  "total_fees": 81.745,
  "first_tic": "2020-08-30 18:00:00",
  "last_tic": "2020-09-06 16:39:00",
  "total_tics": 3334,
  "test_duration": 0.199153
}
```

## Backtest

The real goal of this project is to get to the point where these strategies can be generated and tested quickly and then be easily iterated on.

Below is an example of a very simple strategey. Basically, datapoints are used to build a list of datapoints to look at which must all be true to produce an enter or exit status for that tick.

Backtests include all the instructions needed to run the backtest minus the data.

### Backtest Requirements

- name:
  - string, optional
  - default: `None`
  - description: a string for quick reference of the backtest
- chart_period:
  - string, optional
  - default: `"1Min"`
  - description: a charting period string. allowed values are "Min" (minute), "T" (minute), "D" (day),"H" (hour)
  - Ex.
    - "1Min" is 1 minute
    - "2H" is 2 hours
    - "5D" is 5 days
- start: string or timestamp
  - optional,
  - default: `""`
  - description: The time string of when to start the backtest with `%Y-%m-%d %H:%M:%S` date format or a timestamp. It will be tested
  - Ex.
    - `"2018-05-01 00:00:00"` May 1st, 2018 at midnight

- stop: sting or timestamp
  - optional
  - default: `""`
  - description: The time string of when to stop the backtest with `%Y-%m-%d %H:%M:%S` date format or a timestamp
  - Ex.
    - `"2020-12-28 00:08:00"` December 28th, 2020 at 8am.
    - `"2020-06-01"`June 6th, 2020
    - `1590969600` (seconds) June 6th, 2020
    - `1590969600000` (milliseconds) June 6th, 2020

- base_balance: float or int
  - optional
  - default: 1000
  - description: The starting balance of trade account. Usually $ or "base" coins for cryptocurrencies.

- comission: float
  - optional
  - default: 0.0
  - description: The "trading fee" per trade. This is subtracted per trade.

- enter: list,
  - required
  - default: `None`
  - description: a list of [Logic](#LogicDetail)'s with instructions to compare the data on each tick. EVERY logic item must return True to ENTER the  trade.

- any_enter: list,
  - optional
  - default: `None`
  - description: a list of [Logic](#LogicDetail)'s with instructions to compare the data on each tick. ANY LOGIC ITEM can return True to ENTER the trade.

- exit: list
  - required
  - default: `None`
  - description: a list of [Logic](#LogicDetail)'s with instructions to compare the data on each tick. EVERY LOGIC ITEM must return True to EXIT the trade.

- any_exit: list
  - optional
  - default: `None`
  - description: a list of [Logic](#LogicDetail)'s with instructions to compare the data on each tick. ANY LOGIC ITEM can return True to EXIT the trade.

- datapoints: list
  - optional
  - default: `None`
  - description: This describes how to create the datapoints. Each individual transformer has name that can be referenced in either the `enter` or `exit` logizs. For more information, see ([Datapoints](#Datapoints))

- trailing_stop_loss: float
  - optional
  - default `0`
  - description: This sets a trailing stop loss, so the trade will exit immediately, without considering any other action. It is the percentage ot follow for example, to set a stop loss of 5%, set `0.05`

## Simple Moving Average Cross example

This is an example of a simple moving average cross backtest.

```python
{
    "base_balance": 1000,
    "chart_period": "5T",
    "chart_start": "2020-08-30 18:00:00",
    "chart_stop": "2020-09-06 16:39:00",
    "comission": 0.01,
    "datapoints": [
        {
            "args": [
                30
            ],
            "transformer": "sma",
            "name": "sma_short"
        },
        {
            "args": [
                90
            ],
            "transformer": "sma",
            "name": "sma_long"
        },
    ],
    "enter": [
      ["close", ">", "sma_long"],
      ["close", ">", "sma_short"]
    ],
    "exit": [["close", "<", "sma_short"]],
    "trailing_stop_loss": 0.05,
    "exit_on_end": False,
}
```

### LogicDetail

Each `logic` is contains a single `if` statement. The two variables are the first and last item in the list, with the operator to compare them `>`, `<` `=`.

To think of this easily, just say it out loud.
Ex.

If the close (closing price) at X time is greater than the "short_sma" (custom datapoint), then return True, else return False.

```python
[
  "close", # datapoint or column in provided data
  ">", # operator for comparisson
  "sma_short" # datapoint or column in provided data
]
```

Valid datapoints:

- open
- high
- low
- close
- volume
- any [datapoint](#Datapoints) (see [LogicExample1](#LogicExample1))
- any additional columns in your data file or your dataframe (see [LogicExample2](#LogicExample2))

#### LogicExample1

```python
    [
      "close", # valid datapoint, always provided
      ">", # logic to use to compare
      "short" # valid custom datapoint, defined in datapoints
    ]
```

#### LogicExample2

```python
    [
      "rsi", # valid custom datapoint, should be defined in datapoints
      "<", # logic to use to compare
      70 # integer, float, or string 
    ]
```

#### Logic Lookbacks

Logic lookbacks allow you to confirm a signal by checking the last N periods.

```python
    [
      "rsi", # valid custom datapoint, should be defined in datapoints
      ">", # logic to use to compare
      30, # integer, float, or string
      2 # optional, default 0, LogicalLookback number of periods to confirm this signal
    ]
```

### Datapoints

Datapoints are user defined technical indicators. You can select a defined [transformer](#Transformer) function to apply the technical analysis. They can reference data and calculate the new values to be referenced inside of any of the logics.

Simple SMA example

```python
      {
         "name": "sma_short", # transformer name
         "transformer": "sma", # technical analysis function to be used
         "args": [20], # arguments to pass to the function, for multiple args, add a "," behind each
      }
```
