import warnings

import numpy as np
import pandas as pd


def calculate_trade_quality(trade_log_df):
    """Calculate metrics that show trade quality beyond win/loss"""
    wins = trade_log_df[trade_log_df.adj_account_value_change_perc > 0]
    losses = trade_log_df[trade_log_df.adj_account_value_change_perc < 0]

    try:
        profit_factor = abs(
            wins.adj_account_value_change_perc.sum()
            / losses.adj_account_value_change_perc.sum()
        )
    except (ZeroDivisionError, ValueError):
        profit_factor = 0

    try:
        win_loss_ratio = abs(
            wins.adj_account_value_change_perc.mean()
            / losses.adj_account_value_change_perc.mean()
        )
    except (ZeroDivisionError, ValueError):
        win_loss_ratio = 0

    try:
        largest_win = float(round(trade_log_df.adj_account_value_change_perc.max(), 3))
        largest_loss = float(round(trade_log_df.adj_account_value_change_perc.min(), 3))
    except ValueError:
        largest_win = 0
        largest_loss = 0

    return {
        "profit_factor": 0.0 if pd.isna(profit_factor) else float(round(profit_factor, 3)),
        "avg_win_loss_ratio": 0.0 if pd.isna(win_loss_ratio) else float(round(win_loss_ratio, 3)),
        "largest_winning_trade": 0.0 if pd.isna(largest_win) else largest_win,
        "largest_losing_trade": 0.0 if pd.isna(largest_loss) else largest_loss,
    }


def calculate_effective_trades(df, trade_log_df):
    """Calculate trade metrics accounting for commission"""
    trade_fees = df.loc[trade_log_df.index, "fee"]
    pnl = trade_log_df.get("adj_account_value_change")
    if pnl is None:
        pnl = 0

    profitable_trades = trade_log_df[pnl > trade_fees]
    unprofitable_trades = trade_log_df[pnl <= trade_fees]
    commission_impact = df.fee.sum() / df.iloc[-1].adj_account_value * 100

    return {
        "num_profitable_after_commission": int(len(profitable_trades)),
        "num_unprofitable_after_commission": int(len(unprofitable_trades)),
        "commission_drag_pct": float(round(commission_impact, 3)),
    }


def create_trade_log(df):
    """Find all rows when a trade was entered or exited"""
    trade_log_df = df.reset_index()
    trade_log_df = trade_log_df.groupby(
        (trade_log_df["in_trade"] != trade_log_df["in_trade"].shift()).cumsum()
    ).first()

    if "date" in trade_log_df.columns:
        trade_log_df = trade_log_df.set_index("date")

    trade_log_df = trade_log_df.replace([np.inf, -np.inf], np.nan)
    trade_log_df = trade_log_df[trade_log_df.adj_account_value_change != 0]

    return trade_log_df


def summarize_time_held(trade_log_df):
    idx = pd.to_datetime(trade_log_df.index)
    idx = pd.Index(idx).sort_values()
    trade_time_held_series = pd.Series(idx).diff()
    mean_trade_time_held = trade_time_held_series.mean()
    max_trade_time_held = trade_time_held_series.max()
    min_trade_time_held = trade_time_held_series.min()
    median_time_held = trade_time_held_series.median()

    return (
        mean_trade_time_held,
        max_trade_time_held,
        min_trade_time_held,
        median_time_held,
    )


def summarize_trade_perc(trade_log_df: pd.DataFrame):
    """Calculate trade percentages with protection against NaN values"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        try:
            max_trade_perc = float(trade_log_df.adj_account_value_change_perc.max())
            min_trade_perc = float(trade_log_df.adj_account_value_change_perc.min())
            mean_trade_perc = float(trade_log_df.adj_account_value_change_perc.mean())
            median_trade_perc = float(trade_log_df.adj_account_value_change_perc.median())
        except ValueError:
            max_trade_perc = 0.0
            min_trade_perc = 0.0
            mean_trade_perc = 0.0
            median_trade_perc = 0.0

    return (
        0.0 if pd.isna(max_trade_perc) else float(round(max_trade_perc, 4)),
        0.0 if pd.isna(min_trade_perc) else float(round(min_trade_perc, 4)),
        0.0 if pd.isna(mean_trade_perc) else float(round(mean_trade_perc, 4)),
        0.0 if pd.isna(median_trade_perc) else float(round(median_trade_perc, 4)),
    )


def summarize_trades(trades: pd.DataFrame, total_trades):
    """Calculate trade summaries with protection against NaN values"""
    try:
        avg_perc = float(trades.adj_account_value_change_perc.mean() * 100)
        perc = float((len(trades.index) / total_trades) * 100) if total_trades > 0 else 0.0
    except (ZeroDivisionError, ValueError):
        avg_perc = 0.0
        perc = 0.0

    return (
        int(len(trades.index)),
        0.0 if pd.isna(avg_perc) else float(round(avg_perc, 3)),
        0.0 if pd.isna(perc) else float(round(perc, 3)),
    )
