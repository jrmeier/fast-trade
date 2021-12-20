from fast_trade import run_backtest, validate_backtest
from fast_trade.build_summary import build_summary
import pandas as pd
import pprint

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', 1200)

backtest = {
	"name": "first test",
	"base_balance": 1000, # start with a balance of 1000
	"chart_period": "1Min", # time period selected on the chart
	"chart_start": "2021-12-01 00:00:00", # when to start the chart
	"chart_stop": "2021-12-14 18:00:00", # when to stop the chart
	"comission": 0.075, # a comission to pay per transaction

	# describes the data to use in the logic
	# ============================================================================
	# args are passed to the transformer function
	# e.g. SMA5 args [5], "transformer": "sma", "name": "sma_short"
	# enter and exit can have multiple arguments
	"datapoints": [
					{"args": [2], "transformer": "sma", "name": "sma2"},
					{"args": [3], "transformer": "sma", "name": "sma3"},
					{"args": [5], "transformer": "sma", "name": "sma5"},
					{"args": [8], "transformer": "sma", "name": "sma8"},
					{"args": [13], "transformer": "sma", "name": "sma13"},
					# Bodge way to see if ma50 is increasing - use ma50 > ma51
					{"args": [50], "transformer": "sma", "name": "sma50"},
					{"args": [51], "transformer": "sma", "name": "sma51"},
					#{"args": [1.01], "transformer": "tp", "name": "tp"},

					],
	"enter": 		[
					["sma5", ">", "sma8"],
					# ["sma8", ">", "sma13"],
					# ["sma50", ">", "sma51"],
					],

	"exit":			[
					#["sma5", "<", "sma13"],
					#["close", ">", "close + (close * tp)"],
					],

	# ============================================================================
	# build_data_frame line 73
	# run_backtest 74, 168, 176
	# run_analysis 66 "tp" to action options

	# "take_profit_amount": 0.01, # optional take profit test need to use 0.01 for 1% profit
	# ============================================================================
	"trailing_stop_loss": 0.05, # optional trailing stop loss

	"exit_on_end": False, # at then end of the backtest, if true, the trade will exit
}

# returns a mirror of the object, with errors if any
print(f"Validate: \n")
pprint.pprint(validate_backtest(backtest))

datafile_path = "../historical/AIONUSDT_1m_1 Dec 2021.csv"

# returns the summary object and the dataframe
result = run_backtest(backtest, datafile_path)


summary = result["summary"]
df = result["df"]
trade_df = result["trade_df"]

# print(f"Summary:")
# pprint.pprint(summary)
print(f"{df.tail(100)}\n\n")
print(f"{df['close'].max()} {df['close'].min()}")

try:
	print(trade_df.tail(25))
except Exception as e:
	print(f"{e}")
print(	f"Quick View\n"
		#f"Symbol: 			  {df['symbol']}"
		f"Start Balance:\n"
		f"End Balance:        {summary['equity_final']}\n"
		f"Peak Balance:       {summary['equity_peak']}\n"
		f"Strategy Return:    {summary['return_perc']}\n"
		f"Buy and Hold:       {summary['buy_and_hold_perc']}\n"
		f"Trades:             {summary['num_trades']}\n"
		f"Win:                {summary['total_num_winning_trades']}\n"
		f"Lose:               {summary['total_num_losing_trades']}\n")


