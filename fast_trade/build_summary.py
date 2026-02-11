import datetime
import warnings

import numpy as np
import pandas as pd

from .calculate_perc_missing import calculate_perc_missing


def calculate_market_adjusted_returns(df, return_perc, buy_and_hold_perc):
    """Calculate returns relative to the underlying asset's movement"""
    return float(round(return_perc - buy_and_hold_perc, 3))


def calculate_position_metrics(df):
    """Calculate metrics that show how individual positions performed"""
    in_trade_groups = df[df.in_trade].groupby(
        (df.in_trade != df.in_trade.shift()).cumsum()
    )

    try:
        avg_pos_size = float(round(df[df.in_trade].aux.mean(), 3))
        max_pos_size = float(round(df[df.in_trade].aux.max(), 3))
        avg_pos_duration = float(round(in_trade_groups.size().mean(), 3))
        commission_impact = float(
            round(df.fee.sum() / df.iloc[-1].adj_account_value * 100, 3)
        )
    except (ZeroDivisionError, ValueError):
        avg_pos_size = 0.0
        max_pos_size = 0.0
        avg_pos_duration = 0.0
        commission_impact = 0.0

    return {
        "avg_position_size": 0.0 if pd.isna(avg_pos_size) else avg_pos_size,
        "max_position_size": 0.0 if pd.isna(max_pos_size) else max_pos_size,
        "avg_position_duration": 0.0 if pd.isna(avg_pos_duration) else avg_pos_duration,
        "total_commission_impact": (
            0.0 if pd.isna(commission_impact) else commission_impact
        ),
    }


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
        "profit_factor": (
            0.0 if pd.isna(profit_factor) else float(round(profit_factor, 3))
        ),
        "avg_win_loss_ratio": (
            0.0 if pd.isna(win_loss_ratio) else float(round(win_loss_ratio, 3))
        ),
        "largest_winning_trade": 0.0 if pd.isna(largest_win) else largest_win,
        "largest_losing_trade": 0.0 if pd.isna(largest_loss) else largest_loss,
    }


def calculate_market_exposure(df):
    """Calculate metrics about market exposure"""
    try:
        in_trade_duration = (
            df[df.in_trade]
            .groupby((df.in_trade != df.in_trade.shift()).cumsum())
            .size()
        )
        time_in_market = float(round((df.in_trade.sum() / len(df)) * 100, 3))
        avg_duration = (
            float(round(in_trade_duration.mean(), 3))
            if not in_trade_duration.empty
            else 0
        )
    except (ZeroDivisionError, ValueError):
        time_in_market = 0.0
        avg_duration = 0.0

    return {
        "time_in_market_pct": 0.0 if pd.isna(time_in_market) else time_in_market,
        "avg_trade_duration": 0.0 if pd.isna(avg_duration) else avg_duration,
    }


def calculate_effective_trades(df, trade_log_df):
    """Calculate trade metrics accounting for commission

    Notes
    -----
    Compare absolute trade P&L (adj_account_value_change) to absolute fees.
    Comparing percentages to currency fees is incorrect.
    """
    # Get the fee values for the trade log indices
    trade_fees = df.loc[trade_log_df.index, "fee"]

    # Use absolute change for profit-after-fee comparison
    pnl = trade_log_df.get("adj_account_value_change")
    if pnl is None:
        # Fallback: derive from percentage if absolute not present
        pnl = (
            trade_log_df.get("adj_account_value_change_perc", 0)
            * df.loc[trade_log_df.index, "adj_account_value"].shift(fill_value=0)
        )

    profitable_trades = trade_log_df[pnl > trade_fees]
    unprofitable_trades = trade_log_df[pnl <= trade_fees]

    try:
        commission_impact = df.fee.sum() / df.iloc[-1].adj_account_value * 100
    except Exception:
        commission_impact = 0.0

    return {
        "num_profitable_after_commission": int(len(profitable_trades)),
        "num_unprofitable_after_commission": int(len(unprofitable_trades)),
        "commission_drag_pct": float(round(commission_impact, 3)),
    }


def calculate_drawdown_metrics(df):
    """Calculate detailed drawdown metrics"""
    try:
        rolling_max = df.adj_account_value.expanding().max()
        drawdowns = df.adj_account_value / rolling_max - 1.0

        max_drawdown = float(round(drawdowns.min() * 100, 3))
        avg_drawdown = float(round(drawdowns.mean() * 100, 3))

        # Calculate drawdown duration
        is_drawdown = drawdowns < 0
        drawdown_groups = (is_drawdown != is_drawdown.shift()).cumsum()[is_drawdown]
        durations = drawdown_groups.value_counts()

        max_duration = float(round(durations.max() if not durations.empty else 0, 3))
        avg_duration = float(round(durations.mean() if not durations.empty else 0, 3))

        return {
            "max_drawdown_pct": 0.0 if pd.isna(max_drawdown) else max_drawdown,
            "avg_drawdown_pct": 0.0 if pd.isna(avg_drawdown) else avg_drawdown,
            "max_drawdown_duration": 0.0 if pd.isna(max_duration) else max_duration,
            "avg_drawdown_duration": 0.0 if pd.isna(avg_duration) else avg_duration,
            "current_drawdown": float(round(drawdowns.iloc[-1] * 100, 3)),
        }
    except (ValueError, AttributeError):
        return {
            "max_drawdown_pct": 0.0,
            "avg_drawdown_pct": 0.0,
            "max_drawdown_duration": 0.0,
            "avg_drawdown_duration": 0.0,
            "current_drawdown": 0.0,
        }


def calculate_risk_metrics(df):
    """Calculate risk-adjusted return metrics"""
    try:
        returns = df.adj_account_value_change_perc

        # Sortino Ratio (like Sharpe but only for negative returns)
        negative_returns = returns[returns < 0]
        downside_std = float(
            negative_returns.std() if not negative_returns.empty else 0
        )
        avg_return = float(returns.mean())
        sortino_ratio = float(
            round(avg_return / downside_std if downside_std != 0 else 0, 3)
        )

        # Calmar Ratio (return / max drawdown)
        rolling_max = df.adj_account_value.expanding().max()
        drawdowns = df.adj_account_value / rolling_max - 1.0
        max_drawdown = abs(float(drawdowns.min()))
        calmar_ratio = float(
            round(avg_return / max_drawdown if max_drawdown != 0 else 0, 3)
        )

        # Value at Risk (95th percentile of losses)
        var_95 = float(round(returns.quantile(0.05), 3))

        return {
            "sortino_ratio": 0.0 if pd.isna(sortino_ratio) else sortino_ratio,
            "calmar_ratio": 0.0 if pd.isna(calmar_ratio) else calmar_ratio,
            "value_at_risk_95": 0.0 if pd.isna(var_95) else var_95,
            "annualized_volatility": float(round(returns.std() * (252**0.5), 3)),
            "downside_deviation": float(round(downside_std, 3)),
        }
    except (ValueError, AttributeError):
        return {
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "value_at_risk_95": 0.0,
            "annualized_volatility": 0.0,
            "downside_deviation": 0.0,
        }


def calculate_trade_streaks(trade_log_df):
    """Calculate winning and losing streaks"""
    try:
        trades = trade_log_df.adj_account_value_change_perc > 0
        streaks = (trades != trades.shift()).cumsum()

        win_streaks = streaks[trades]
        loss_streaks = streaks[~trades]

        win_streak_counts = win_streaks.value_counts()
        loss_streak_counts = loss_streaks.value_counts()

        # compute contiguous current streak length (win or loss)
        last_group = streaks.iloc[-1] if not trades.empty else None
        current_len = int((streaks == last_group).sum()) if last_group is not None else 0
        return {
            "current_streak": current_len,
            "max_win_streak": int(
                win_streak_counts.max() if not win_streak_counts.empty else 0
            ),
            "max_loss_streak": int(
                loss_streak_counts.max() if not loss_streak_counts.empty else 0
            ),
            "avg_win_streak": float(
                round(win_streak_counts.mean() if not win_streak_counts.empty else 0, 3)
            ),
            "avg_loss_streak": float(
                round(
                    loss_streak_counts.mean() if not loss_streak_counts.empty else 0, 3
                )
            ),
        }
    except (ValueError, AttributeError):
        return {
            "current_streak": 0,
            "max_win_streak": 0,
            "max_loss_streak": 0,
            "avg_win_streak": 0.0,
            "avg_loss_streak": 0.0,
        }


def calculate_time_analysis(df):
    """Calculate time-based performance metrics"""
    try:
        # Convert index to datetime if it isn't already
        df.index = pd.to_datetime(df.index)

        # Daily returns
        daily_returns = df.adj_account_value.resample("D").last().pct_change()

        # Monthly returns
        monthly_returns = df.adj_account_value.resample("ME").last().pct_change()

        return {
            "best_day": float(round(daily_returns.max() * 100, 3)),
            "worst_day": float(round(daily_returns.min() * 100, 3)),
            "avg_daily_return": float(round(daily_returns.mean() * 100, 3)),
            "daily_return_std": float(round(daily_returns.std() * 100, 3)),
            "profitable_days_pct": float(round((daily_returns > 0).mean() * 100, 3)),
            "best_month": float(round(monthly_returns.max() * 100, 3)),
            "worst_month": float(round(monthly_returns.min() * 100, 3)),
            "avg_monthly_return": float(round(monthly_returns.mean() * 100, 3)),
            "monthly_return_std": float(round(monthly_returns.std() * 100, 3)),
            "profitable_months_pct": float(
                round((monthly_returns > 0).mean() * 100, 3)
            ),
        }
    except (ValueError, AttributeError):
        return {
            "best_day": 0.0,
            "worst_day": 0.0,
            "avg_daily_return": 0.0,
            "daily_return_std": 0.0,
            "profitable_days_pct": 0.0,
            "best_month": 0.0,
            "worst_month": 0.0,
            "avg_monthly_return": 0.0,
            "monthly_return_std": 0.0,
            "profitable_months_pct": 0.0,
        }


def build_summary(df, performance_start_time):
    # Not yet implimented
    # Expectancy [%]                           6.92
    # SQN                                      1.77
    # Sortino Ratio                            0.54
    # Calmar Ratio                             0.07

    # Do the easy stuff first
    equity_peak = round(df["account_value"].max(), 3)
    equity_final = round(df.iloc[-1]["adj_account_value"], 3)

    max_drawdown = round(df["adj_account_value"].min(), 3)

    performance_stop_time = datetime.datetime.utcnow()
    start_date = df.index[0]
    end_date = df.index[-1]
    # count the number enter, exit, and hold signals
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

        # Calculate all metrics
        market_adjusted_return = calculate_market_adjusted_returns(
            df, return_perc, buy_and_hold_perc
        )
        position_metrics = calculate_position_metrics(df)
        trade_quality = calculate_trade_quality(trade_log_df)
        market_exposure = calculate_market_exposure(df)
        effective_trades = calculate_effective_trades(df, trade_log_df)

        # New metrics
        drawdown_metrics = calculate_drawdown_metrics(df)
        risk_metrics = calculate_risk_metrics(df)
        trade_streaks = calculate_trade_streaks(trade_log_df)
        time_analysis = calculate_time_analysis(df)

        performance_stop_time = datetime.datetime.utcnow()

        [perc_missing, total_missing_dates] = calculate_perc_missing(df)

    # check if median_time_held is a timedelta object
    if isinstance(median_time_held, datetime.timedelta):
        median_time_held = median_time_held.total_seconds()
        median_time_held = round(median_time_held, 3)
        mean_trade_time_held = mean_trade_time_held.total_seconds()
        mean_trade_time_held = round(mean_trade_time_held, 3)
        max_trade_time_held = max_trade_time_held.total_seconds()
        max_trade_time_held = round(max_trade_time_held, 3)
        min_trade_time_held = min_trade_time_held.total_seconds()
        min_trade_time_held = round(min_trade_time_held, 3)
    else:
        median_time_held = 0
        mean_trade_time_held = 0
        max_trade_time_held = 0
        min_trade_time_held = 0

    summary = {
        # Original metrics
        "return_perc": float(return_perc if not pd.isna(return_perc) else 0),
        "sharpe_ratio": float(sharpe_ratio if not pd.isna(sharpe_ratio) else 0),  # BETA
        "buy_and_hold_perc": float(
            buy_and_hold_perc if not pd.isna(buy_and_hold_perc) else 0
        ),
        "median_trade_len": median_time_held if not pd.isna(median_time_held) else 0,
        "mean_trade_len": (
            mean_trade_time_held if not pd.isna(mean_trade_time_held) else 0
        ),
        "max_trade_held": (
            max_trade_time_held if not pd.isna(max_trade_time_held) else 0
        ),
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
        "median_trade_perc": float(
            median_trade_perc if not pd.isna(median_trade_perc) else 0
        ),
        "mean_trade_perc": float(
            mean_trade_perc if not pd.isna(mean_trade_perc) else 0
        ),
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
        "total_missing": int(
            total_missing_dates if not pd.isna(total_missing_dates) else 0
        ),
        "test_duration": round(
            (performance_stop_time - performance_start_time).total_seconds(), 3
        ),
        "num_of_enter_signals": total_enter,
        "num_of_exit_signals": total_exit,
        "num_of_hold_signals": total_hold,
        # New metrics
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


def create_trade_log(df):
    """Finds all the rows when a trade was entered or exited

    Parameters
    ----------
        df: dataframe, from process_dataframe

    Returns
    -------
        trade_log_df: dataframe, of when transactions took place
    """
    trade_log_df = df.reset_index()
    trade_log_df = trade_log_df.groupby(
        (trade_log_df["in_trade"] != trade_log_df["in_trade"].shift()).cumsum()
    ).first()

    if "date" in trade_log_df.columns:
        trade_log_df = trade_log_df.set_index("date")

    trade_log_df = trade_log_df.replace([np.inf, -np.inf], np.nan)

    # only get the records where the account value changed
    # this will exclude the "enter" trades since the adj_account_value doesn't change
    trade_log_df = trade_log_df[trade_log_df.adj_account_value_change != 0]

    return trade_log_df


def summarize_time_held(trade_log_df):
    trade_time_held_series = trade_log_df.index.to_series().diff()
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
            median_trade_perc = float(
                trade_log_df.adj_account_value_change_perc.median()
            )
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
        perc = (
            float((len(trades.index) / total_trades) * 100) if total_trades > 0 else 0.0
        )
    except (ZeroDivisionError, ValueError):
        avg_perc = 0.0
        perc = 0.0

    return (
        int(len(trades.index)),
        0.0 if pd.isna(avg_perc) else float(round(avg_perc, 3)),
        0.0 if pd.isna(perc) else float(round(perc, 3)),
    )


def calculate_return_perc(trade_log_df: pd.DataFrame):
    """Calculate return percentage with protection against NaN values"""
    if trade_log_df.empty:
        return 0.0
    try:
        if trade_log_df.iloc[0].adj_account_value:
            first_val = float(trade_log_df.iloc[0].adj_account_value)
            last_val = float(trade_log_df.iloc[-1].adj_account_value)
            if last_val == 0:
                return 0.0
            return_perc = 100 - (first_val / last_val) * 100
            return 0.0 if pd.isna(return_perc) else float(round(return_perc, 3))
    except (ZeroDivisionError, ValueError, AttributeError):
        return 0.0
    return 0.0


def calculate_buy_and_hold_perc(df):
    """Calculate buy and hold percentage with protection against NaN values"""
    try:
        first_close = float(df.iloc[0].close)
        last_close = float(df.iloc[-1].close)
        if last_close == 0:
            return 0.0
        buy_and_hold_perc = (1 - (first_close / last_close)) * 100
        return 0.0 if pd.isna(buy_and_hold_perc) else float(round(buy_and_hold_perc, 3))
    except (ZeroDivisionError, ValueError, AttributeError):
        return 0.0


def calculate_shape_ratio(df):
    """Calculate Sharpe ratio with protection against NaN values"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        try:
            mean_return = df["adj_account_value_change_perc"].mean()
            std_return = df["adj_account_value_change_perc"].std()
            if pd.isna(mean_return) or pd.isna(std_return) or std_return == 0:
                return 0.0
            sharpe_ratio = mean_return / std_return
            sharpe_ratio = (len(df.index) ** 0.5) * sharpe_ratio
            return 0.0 if pd.isna(sharpe_ratio) else float(round(sharpe_ratio, 3))
        except (ZeroDivisionError, ValueError):
            return 0.0
