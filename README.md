# Fast Trade

[![License: LGPL v3](https://img.shields.io/github/license/jrmeier/fast-trade)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/fast-trade.svg?style=flat-square)](https://pypi.org/project/fast-trade/)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/download/releases/3.7.0/)
[![Python application](https://github.com/jrmeier/fast-trade/workflows/Python%20application/badge.svg)](https://github.com/jrmeier/fast-trade/actions)

A library built with backtest portability and performance in mind for backtest trading strategies. There is also an [Archive](#Archive), which can be used to download compatible kline data from Binance (.com or .us) and Coinbase into sqlite databases..

## Motivations
If backests are fast, strategies are cheap.

## Beta Testing

I'm using this library to build a whole platform (data management, backesting, scanners, signals, etc) via Jupyter Notebooks and a discord bot, and I'm looking for beta testers. If you like this library, send me an email at fasttrade@jedm.dev or join the discord [https://discord.gg/Y8ypD3dcgs](https://discord.gg/Y8ypD3dcgs)

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

## Install

```bash
pip install fast-trade
```

## Usage

[strategy.json](./strategy.json) for an example strategy. The basic idea is you describe the "datapoints" then compare them in the "logics". The "datapoints" describe the technical analysis functions to run, and the "logics" describe the logic to use to determine when to enter and exit trades.

Example backtest script

```python
from fast_trade import run_backtest, validate_backtest

backtest = {
    "base_balance": 1000, # start with a balance of 1000
    "freq": "5Min", # time period selected on the chard
    "chart_start": "2021-08-30 18:00:00", # when to start the chart
    "chart_stop": "2021-09-06 16:39:00", # when to stop the chart
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
    "rules": [["sharpe_ratio", ">", 0.5]], # use rules to filter out backtests that didnt perform well
    "trailing_stop_loss": 0.05, # optional trailing stop loss 
    "exit_on_end": False, # at then end of the backtest, if true, the trade will exit
}
# backtests can also come from urls
# backtest = "https://raw.githubusercontent.com/jrmeier/fast-trade/master/sma_strategy.json"

# returns a mirror of the object, with errors if any
print(validate_backtest(backtest))

# returns the summary object and the dataframe
result = run_backtest(backtest)

summary = result["summary"]
df = result["df"]
trade_log_df = result["trade_df"]

print(summary)
print(df.head())
```


## CLI

You can also use the package from the command line. Each command's specific help feature can be viewed by running `ft <command> -h`.

List the commands and their help.
`ft -h`

### Basic usage

This will download the last month of data for BTCUSD from binance.us and store in a `ft_archive/` directory as a sqlite database.

`ft download BTCUSD binanceus`

This will backtest a file with a strategy. By default, it will only show a summary of the backtest. However, if you want to save the results, add the `--save` flag and it will go the `saved_backtests/` directory.

`ft backtest ./strategy.json`

You can validate a backtest before you run it. This doesn't help with the data, but does help with the logic.
`ft validate stategy.json`

### Backteset Modifiers

Modifying the `freq`

`ft backtest ./strategy.json --mods freq 1H`

Modifying the `freq` and the `trailing_stop_loss`

`ft backtest ./strategy.json --mods freq 1H trailing_stop_loss .05`

Saving a test result
This generates creates the `saved_backtest` directory (if it doesn't exist), then inside of there, is another directory with a timestamp, with a chart, the backtest file, the summary, and the raw dataframe as a csv.
`ft backtest ./strategy.json --save`

### Archive
You can download data directly from the CoinbaseAPI and BinanceAPI without registering for an API key.

Get a list of assets available for download from the given exchange. Defaults to binanceus.

`ft assets --exchange=EXCHANGE`

Download a single asset from the given exchange. Defaults to binanceus.
`ft download SYMBOL EXCHANGE`

Download the last 30 days of BTCUSDT from binance.us
`ft download BTCUSDT binanceus`

`ft download SYMBOL --archive ARCHIVE_PATH --start START_DATE --end END_DATE --exchange=EXCHANGE`

Update the archive. Brings the archive up to date with the latest data for each symbol.

```ft update_archive```

This update all the existing items in the archive, downloading the latest data for each symbol.


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
  "return_perc": 10.093,
  "sharpe_ratio": 0.893,
  "buy_and_hold_perc": 2.086,
  "median_trade_len": 4200.0,
  "mean_trade_len": 7341.7,
  "max_trade_held": 54300.0,
  "min_trade_len": 300.0,
  "total_num_winning_trades": 136.0,
  "total_num_losing_trades": 371.0,
  "avg_win_perc": 0.142,
  "avg_loss_perc": -0.021,
  "best_trade_perc": 0.012,
  "min_trade_perc": -0.0025,
  "median_trade_perc": -0.0001,
  "mean_trade_perc": 0.0002,
  "num_trades": 507,
  "win_perc": 26.824,
  "loss_perc": 73.176,
  "equity_peak": 1127.147,
  "equity_final": 1112.254,
  "max_drawdown": 985.676,
  "total_fees": 26.662,
  "first_tic": "2024-11-27 01:15:00",
  "last_tic": "2025-01-09 03:10:00",
  "total_tics": 12408,
  "perc_missing": 0.0,
  "total_missing": 0,
  "test_duration": 0.302,
  "num_of_enter_signals": 718,
  "num_of_exit_signals": 5564,
  "num_of_hold_signals": 6126,
  "market_adjusted_return": 8.007,
  "position_metrics": {
    "avg_position_size": 0.011,
    "max_position_size": 0.012,
    "avg_position_duration": 18.327,
    "total_commission_impact": 2.397
  },
  "trade_quality": {
    "profit_factor": 2.522,
    "avg_win_loss_ratio": 6.881,
    "largest_winning_trade": 0.012,
    "largest_losing_trade": -0.003
  },
  "market_exposure": {
    "time_in_market_pct": 37.516,
    "avg_trade_duration": 18.327
  },
  "effective_trades": {
    "num_profitable_after_commission": 0,
    "num_unprofitable_after_commission": 507,
    "commission_drag_pct": 2.397
  },
  "drawdown_metrics": {
    "max_drawdown_pct": -11.578,
    "avg_drawdown_pct": -3.07,
    "max_drawdown_duration": 6178.0,
    "avg_drawdown_duration": 137.977,
    "current_drawdown": -1.457
  },
  "risk_metrics": {
    "sortino_ratio": 0.006,
    "calmar_ratio": 0.0,
    "value_at_risk_95": -0.002,
    "annualized_volatility": 0.018,
    "downside_deviation": 0.001
  },
  "trade_streaks": {
    "current_streak": 371,
    "max_win_streak": 1,
    "max_loss_streak": 19,
    "avg_win_streak": 1.0,
    "avg_loss_streak": 2.708
  },
  "time_analysis": {
    "best_day": 0.0,
    "worst_day": 0.0,
    "avg_daily_return": 0.0,
    "daily_return_std": 0.0,
    "profitable_days_pct": 0.0,
    "best_month": 0.0,
    "worst_month": 0.0,
    "avg_monthly_return": 0.0,
    "monthly_return_std": 0.0,
    "profitable_months_pct": 0.0
  },
  "rules": {
    "all": true,
    "any": true,
    "results": [
      true
    ]
  },
  "strategy": {
    "any_enter": [],
    "any_exit": [],
    "freq": "5Min",
    "comission": 0.01,
    "symbol": "BTCUSDT",
    "exchange": "binanceus",
    "datapoints": [
      {
        "args": [
          9
        ],
        "name": "zlema",
        "transformer": "zlema"
      },
      {
        "args": [
          99
        ],
        "name": "zlema_1",
        "transformer": "zlema"
      }
    ],
    "enter": [
      [
        "zlema",
        ">",
        "close",
        4
      ]
    ],
    "exit": [
      [
        "zlema_1",
        "<",
        "close",
        2
      ]
    ],
    "start_date": "2024-11-01",
    "exit_on_end": false,
    "trailing_stop_loss": null,
    "rules": [
      [
        "return_perc",
        ">",
        0.05
      ]
    ],
    "base_balance": 1000,
    "lot_size_perc": 1.0,
    "max_lot_size": 0
  }
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
- freq:
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

- rules: list
  - optional
  - default: `None`
  - description: This is a list of rules to filter out backtests that didnt perform well. See [Rules](#Rules) for more information.

## Simple Moving Average Cross example

This is an example of a simple moving average cross backtest.

```python
{
    "base_balance": 1000,
    "freq": "5T",
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

Each `logic` is contains a single `if` statement. The two variables are the first and last item in the list, with the operator to compare them `>`, `<`, `=`, `>=`, or `<=`.

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
If true, thats an enter signal, if false, thats an exit signal.

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

Datapoints are user defined technical indicators. You can select a defined [transformer](##Transformer) function to apply the technical analysis. They can reference data and calculate the new values to be referenced inside of any of the logics.

- name:
  - string, required
  - description: a string for quick reference of the datapoint
- transformer:
  - string, required
  - description: a string of the transformer function to use
- args:
  - list, required
  - description: a list of arguments to pass to the transformer function
- freq:
  - string, optional
  - description: a string of the frequency to sample the data at, default is the freq in the backtest

Simple SMA example

```python
      {
         "name": "sma_short", # transformer name
         "transformer": "sma", # technical analysis function to be used
         "args": [20], # arguments to pass to the function, for multiple args, add a "," behind each
         "freq": "1Min" # optional, default is the freq in the backtest
      }
```

## Transfomers (Technical Indicators)

See [TRANSFORMER_README.md](TRANSFORMER_README.md) for a list of supported indicators. For the most details, see the actual implementation in [fast_trade/finta.py](fast_trade/finta.py).

Note:
  
If a transfomer function returns multiple series, fast-trade will name concate the name of the series with the name of the transfomer function and whatever the returned name is It will be lowercased and maybe not what you expect. See the specific transformer for more details in[./fast_trade/finta.py](fast_trade/finta.py).

Example:

The `bbands` function returns three series, one for the upper band and one for the lower band. The name of the series will be `bbands_bb_upper`,`bbands_bb_middle`, and `bbands_bb_lower`.

`bbands` returns 3 columns `bb_upper`, `bb_middle`, and `bb_lower` so the series to reference in the logic will be `{transformer_name}_bbands_bb_upper`, `{transformer_name}_bbands_bb_middle`, and `{transformer_name}_bbands_bb_lower`.

## Rules

Rules are used to filter out backtests that didnt perform well. They are based on the summary object keys. This is usefuly for quickly filtering out backtests that didnt perform well.

Rules can use dotted notation to access nested dictionaries.

Example:

```python
[
  ["sharpe_ratio", ">", 0.5],
  ["win_perc", ">", 0.5],
  ["loss_perc", "<", 0.5],
  ["trade_streaks.avg_win_streak", ">", 2]
]
```

## Supported Indicators

See [finta/README.md](FINTA_README.md) for a list of supported indicators.
