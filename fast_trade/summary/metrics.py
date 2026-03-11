import warnings

import pandas as pd

from fast_trade.calculate_perc_missing import calculate_perc_missing


def calculate_market_adjusted_returns(df, return_perc, buy_and_hold_perc):
    """Calculate returns relative to the underlying asset's movement"""
    return float(round(return_perc - buy_and_hold_perc, 3))


def calculate_position_metrics(df):
    """Calculate metrics that show how individual positions performed"""
    in_trade_groups = df[df.in_trade].groupby((df.in_trade != df.in_trade.shift()).cumsum())

    try:
        avg_pos_size = float(round(df[df.in_trade].aux.mean(), 3))
        max_pos_size = float(round(df[df.in_trade].aux.max(), 3))
        avg_pos_duration = float(round(in_trade_groups.size().mean(), 3))
        commission_impact = float(round(df.fee.sum() / df.iloc[-1].adj_account_value * 100, 3))
    except (ZeroDivisionError, ValueError):
        avg_pos_size = 0.0
        max_pos_size = 0.0
        avg_pos_duration = 0.0
        commission_impact = 0.0

    return {
        "avg_position_size": 0.0 if pd.isna(avg_pos_size) else avg_pos_size,
        "max_position_size": 0.0 if pd.isna(max_pos_size) else max_pos_size,
        "avg_position_duration": 0.0 if pd.isna(avg_pos_duration) else avg_pos_duration,
        "total_commission_impact": 0.0 if pd.isna(commission_impact) else commission_impact,
    }


def calculate_market_exposure(df):
    """Calculate metrics about market exposure"""
    try:
        in_trade_duration = df[df.in_trade].groupby((df.in_trade != df.in_trade.shift()).cumsum()).size()
        time_in_market = float(round((df.in_trade.sum() / len(df)) * 100, 3))
        avg_duration = float(round(in_trade_duration.mean(), 3)) if not in_trade_duration.empty else 0
    except (ZeroDivisionError, ValueError):
        time_in_market = 0.0
        avg_duration = 0.0

    return {
        "time_in_market_pct": 0.0 if pd.isna(time_in_market) else time_in_market,
        "avg_trade_duration": 0.0 if pd.isna(avg_duration) else avg_duration,
    }


def calculate_drawdown_metrics(df):
    """Calculate detailed drawdown metrics"""
    try:
        rolling_max = df.adj_account_value.expanding().max()
        drawdowns = df.adj_account_value / rolling_max - 1.0

        max_drawdown = float(round(drawdowns.min() * 100, 3))
        avg_drawdown = float(round(drawdowns.mean() * 100, 3))

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

        negative_returns = returns[returns < 0]
        downside_std = float(negative_returns.std() if not negative_returns.empty else 0)
        avg_return = float(returns.mean())
        sortino_ratio = float(round(avg_return / downside_std if downside_std != 0 else 0, 3))

        rolling_max = df.adj_account_value.expanding().max()
        drawdowns = df.adj_account_value / rolling_max - 1.0
        max_drawdown = abs(float(drawdowns.min()))
        calmar_ratio = float(round(avg_return / max_drawdown if max_drawdown != 0 else 0, 3))

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

        # Count contiguous streak from the end
        last_val = trades.iloc[-1]
        current_streak = 0
        for val in reversed(trades.tolist()):
            if val == last_val:
                current_streak += 1
            else:
                break

        return {
            "current_streak": int(current_streak),
            "max_win_streak": int(win_streak_counts.max() if not win_streak_counts.empty else 0),
            "max_loss_streak": int(loss_streak_counts.max() if not loss_streak_counts.empty else 0),
            "avg_win_streak": float(
                round(win_streak_counts.mean() if not win_streak_counts.empty else 0, 3)
            ),
            "avg_loss_streak": float(
                round(loss_streak_counts.mean() if not loss_streak_counts.empty else 0, 3)
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
        df.index = pd.to_datetime(df.index)
        daily_returns = df.adj_account_value.resample("D").last().pct_change()
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
            "profitable_months_pct": float(round((monthly_returns > 0).mean() * 100, 3)),
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


def calculate_perc_missing_safe(df):
    """Wrapper to keep calculate_perc_missing behavior explicit."""
    return calculate_perc_missing(df)
