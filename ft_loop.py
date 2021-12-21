"""
FastTrade Loop
Loops through all coins using the same backtest strategy

Requirements:
List of coin symbols
Historical .csv data for each coin in list
Coin symbols in .csv name ( BTCUSDT_1m.csv )

"""

from fast_trade import run_backtest, validate_backtest
from fast_trade.build_summary import build_summary
import pandas as pd
import pprint

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', 1200)
summary_list = []
all_coin_summary = []

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
				{"args": [52], "transformer": "sma", "name": "sma52"},
				{"args": [200], "transformer": "sma", "name": "sma200"},
				#{"args": [1.01], "transformer": "tp", "name": "tp"},

			],
			"enter": 		[
				["sma50", ">", "sma200"]


			],

			"exit":			[
				["sma50", "<", "sma200"],
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


coin_list = open('../coins_binance_usdt.txt', 'r').readlines()
for coin in coin_list:
	coin = coin.split()
	for element in coin:
		symbol = element

		summary_name = f"{symbol}_summary"
		df_name = f"{symbol}_df"
		trade_df_name = f"{symbol}_df"

	datafile_path = f"../historical/{symbol}_1m_1 Dec 2021.csv"

	# returns a mirror of the object, with errors if any
	#print(f"Validate: \n")
	#pprint.pprint(validate_backtest(backtest))


	# returns the summary object and the dataframe
	failed = 0
	try:
		result = run_backtest(backtest, datafile_path)
	except Exception as e:
		print(f"{symbol} error")
		failed += 1
		continue


	summary_name = result["summary"]
	df_name = result["df"]
	trade_df_name = result["trade_df"]


	# print(f"Summary:")
	# pprint.pprint(summary)
	#print(f"{df_name.tail(1)}\n\n")
	# print(f"{df['close'].max()} {df['close'].min()}")

	# try:
	# 	print(trade_df_name.tail(1))
	# except Exception as e:
	# 	print(f"{e}")
	summary_list.append(summary_name)

	print(	f"Quick View\n"
			  f"Symbol: 			{symbol}\n"
			  f"Start Balance:\n"
			  f"End Balance:        {summary_name['equity_final']}\n"
			  f"Peak Balance:       {summary_name['equity_peak']}\n"
			  f"Strategy Return:    {summary_name['return_perc']}\n"
			  f"Buy and Hold:       {summary_name['buy_and_hold_perc']}\n"
			  f"Trades:             {summary_name['num_trades']}\n"
			  f"Win:                {summary_name['total_num_winning_trades']}\n"
			  f"Lose:               {summary_name['total_num_losing_trades']}\n")

#print(summary_list)
tpr_win = 0
tpr_lose = 0
for item in summary_list:
	if item['return_perc'] > 0:
		tpr_win += 1
	else:
		tpr_lose += 1

win_ratio = (tpr_win / (tpr_win+tpr_lose)) * 100
if win_ratio < 40:
	conclusion = 'sucks'
if 51 <  win_ratio > 40:
	conclusion = "might break even"
if 70 < win_ratio > 52:
	conclusion = "has potential"
if 90 < win_ratio > 70:
	conclusion = "looks really good"
if win_ratio > 90:
	conclusion = "is going to make you incredibly rich, please send me a copy!"
print(f"Winning Coins: {tpr_win}\n"
	  f"Losing Coins: {tpr_lose}\n"
	  f"Win ratio: {win_ratio:.2f}%")

print(f"This strategy {conclusion}")