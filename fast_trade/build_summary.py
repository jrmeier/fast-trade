import datetime
import warnings

import numpy as np
import pandas as pd

from fast_trade.calculate_perc_missing import calculate_perc_missing
from fast_trade.summary import (
    calculate_buy_and_hold_perc,
    calculate_drawdown_metrics,
    calculate_effective_trades,
    calculate_market_adjusted_returns,
    calculate_market_exposure,
    calculate_position_metrics,
    calculate_return_perc,
    calculate_risk_metrics,
    calculate_shape_ratio,
    calculate_time_analysis,
    calculate_trade_quality,
    calculate_trade_streaks,
    create_trade_log,
    summarize_time_held,
    summarize_trade_perc,
    summarize_trades,
)

__all__ = [
    "calculate_buy_and_hold_perc",
    "calculate_drawdown_metrics",
    "calculate_effective_trades",
    "calculate_market_adjusted_returns",
    "calculate_market_exposure",
    "calculate_position_metrics",
    "calculate_return_perc",
    "calculate_risk_metrics",
    "calculate_shape_ratio",
    "calculate_time_analysis",
    "calculate_trade_quality",
    "calculate_trade_streaks",
    "create_trade_log",
    "summarize_time_held",
    "summarize_trade_perc",
    "summarize_trades",
    "build_summary",
]


def build_summary(df, performance_start_time):
    equity_peak = round(df["account_value"].max(), 3)
    equity_final = round(df.iloc[-1]["adj_account_value"], 3)
    max_drawdown = round(df["adj_account_value"].min(), 3)

    performance_stop_time = datetime.datetime.utcnow()
    start_date = df.index[0]
    end_date = df.index[-1]

    total_enter = len(df[df.action == "e"]) + len(df[df.action == "ae"])
    total_exit = len(df[df.action == "x"]) + len(df[df.action == "ax"])
    total_hold = len(df[df.action == "h"])

    trade_log_df = create_trade_log(df)
    total_trades = len(trade_log_df.index)

    (
        mean_trade_time_held,
        max_trade_time_held,
        min_trade_time_held,
        median_time_held,
    ) = summarize_time_held(trade_log_df)

    (
        max_trade_perc,
        min_trade_perc,
        mean_trade_perc,
        median_trade_perc,
    ) = summarize_trade_perc(trade_log_df)

    total_fees = round(df.fee.sum(), 3)
    win_trades = trade_log_df[trade_log_df.adj_account_value_change_perc > 0]
    loss_trades = trade_log_df[trade_log_df.adj_account_value_change_perc < 0]

    (total_num_winning_trades, avg_win_perc, win_perc) = summarize_trades(
        win_trades, total_trades
    )
    (total_num_losing_trades, avg_loss_perc, loss_perc) = summarize_trades(
        loss_trades, total_trades
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return_perc = calculate_return_perc(df)
        sharpe_ratio = calculate_shape_ratio(df)
        buy_and_hold_perc = calculate_buy_and_hold_perc(df)

        market_adjusted_return = calculate_market_adjusted_returns(
            df, return_perc, buy_and_hold_perc
        )
        position_metrics = calculate_position_metrics(df)
        trade_quality = calculate_trade_quality(trade_log_df)
        market_exposure = calculate_market_exposure(df)
        effective_trades = calculate_effective_trades(df, trade_log_df)

        drawdown_metrics = calculate_drawdown_metrics(df)
        risk_metrics = calculate_risk_metrics(df)
        trade_streaks = calculate_trade_streaks(trade_log_df)
        time_analysis = calculate_time_analysis(df)

        performance_stop_time = datetime.datetime.utcnow()

        [perc_missing, total_missing_dates] = calculate_perc_missing(df)

    if isinstance(median_time_held, datetime.timedelta):
        median_time_held = round(median_time_held.total_seconds(), 3)
        mean_trade_time_held = round(mean_trade_time_held.total_seconds(), 3)
        max_trade_time_held = round(max_trade_time_held.total_seconds(), 3)
        min_trade_time_held = round(min_trade_time_held.total_seconds(), 3)
    else:
        median_time_held = 0
        mean_trade_time_held = 0
        max_trade_time_held = 0
        min_trade_time_held = 0

    summary = {
        "return_perc": float(return_perc if not pd.isna(return_perc) else 0),
        "sharpe_ratio": float(sharpe_ratio if not pd.isna(sharpe_ratio) else 0),
        "buy_and_hold_perc": float(buy_and_hold_perc if not pd.isna(buy_and_hold_perc) else 0),
        "median_trade_len": median_time_held if not pd.isna(median_time_held) else 0,
        "mean_trade_len": mean_trade_time_held if not pd.isna(mean_trade_time_held) else 0,
        "max_trade_held": max_trade_time_held if not pd.isna(max_trade_time_held) else 0,
        "min_trade_len": min_trade_time_held if not pd.isna(min_trade_time_held) else 0,
        "total_num_winning_trades": float(
            total_num_winning_trades if not pd.isna(total_num_winning_trades) else 0
        ),
        "total_num_losing_trades": float(
            total_num_losing_trades if not pd.isna(total_num_losing_trades) else 0
        ),
        "avg_win_perc": float(avg_win_perc if not pd.isna(avg_win_perc) else 0),
        "avg_loss_perc": float(avg_loss_perc if not pd.isna(avg_loss_perc) else 0),
        "best_trade_perc": float(max_trade_perc if not pd.isna(max_trade_perc) else 0),
        "min_trade_perc": float(min_trade_perc if not pd.isna(min_trade_perc) else 0),
        "median_trade_perc": float(median_trade_perc if not pd.isna(median_trade_perc) else 0),
        "mean_trade_perc": float(mean_trade_perc if not pd.isna(mean_trade_perc) else 0),
        "num_trades": int(total_trades if not pd.isna(total_trades) else 0),
        "win_perc": float(win_perc if not pd.isna(win_perc) else 0),
        "loss_perc": float(loss_perc if not pd.isna(loss_perc) else 0),
        "equity_peak": float(equity_peak if not pd.isna(equity_peak) else 0),
        "equity_final": float(equity_final if not pd.isna(equity_final) else 0),
        "max_drawdown": float(max_drawdown if not pd.isna(max_drawdown) else 0),
        "total_fees": float(total_fees if not pd.isna(total_fees) else 0),
        "first_tic": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "last_tic": end_date.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tics": len(df.index),
        "perc_missing": float(perc_missing if not pd.isna(perc_missing) else 0),
        "total_missing": int(total_missing_dates if not pd.isna(total_missing_dates) else 0),
        "test_duration": round((performance_stop_time - performance_start_time).total_seconds(), 3),
        "num_of_enter_signals": total_enter,
        "num_of_exit_signals": total_exit,
        "num_of_hold_signals": total_hold,
        "market_adjusted_return": market_adjusted_return,
        "position_metrics": position_metrics,
        "trade_quality": trade_quality,
        "market_exposure": market_exposure,
        "effective_trades": effective_trades,
        "drawdown_metrics": drawdown_metrics,
        "risk_metrics": risk_metrics,
        "trade_streaks": trade_streaks,
        "time_analysis": time_analysis,
    }

    return summary, trade_log_df
