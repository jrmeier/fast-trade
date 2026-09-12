import polars as pl

from fast_trade.calculate_perc_missing import calculate_perc_missing
from fast_trade.frames import to_polars
from fast_trade.summary.helpers import (
    NUMERIC_ERRORS,
    clean_float,
    finite,
    run_lengths,
)

TRADING_DAYS_PER_YEAR = 252


def calculate_market_adjusted_returns(df, return_perc, buy_and_hold_perc):
    """Calculate returns relative to the underlying asset's movement"""
    return float(round(return_perc - buy_and_hold_perc, 3))


def calculate_position_metrics(df):
    """Calculate metrics that show how individual positions performed"""
    df = to_polars(df)

    try:
        in_trade = df["in_trade"].fill_null(False).cast(pl.Boolean)
        position_sizes = finite(df["aux"].filter(in_trade))

        avg_pos_size = clean_float(position_sizes.mean(), 3)
        max_pos_size = clean_float(position_sizes.max(), 3)
        avg_pos_duration = clean_float(run_lengths(in_trade).mean(), 3)
        commission_impact = clean_float(
            df["fee"].sum() / df["adj_account_value"][-1] * 100, 3
        )
    except NUMERIC_ERRORS:
        avg_pos_size = 0.0
        max_pos_size = 0.0
        avg_pos_duration = 0.0
        commission_impact = 0.0

    return {
        "avg_position_size": avg_pos_size,
        "max_position_size": max_pos_size,
        "avg_position_duration": avg_pos_duration,
        "total_commission_impact": commission_impact,
    }


def calculate_market_exposure(df):
    """Calculate metrics about market exposure"""
    df = to_polars(df)

    try:
        in_trade = df["in_trade"].fill_null(False).cast(pl.Boolean)
        durations = run_lengths(in_trade)
        time_in_market = clean_float(in_trade.sum() / len(df) * 100, 3)
        avg_duration = clean_float(durations.mean(), 3) if len(durations) else 0.0
    except NUMERIC_ERRORS:
        time_in_market = 0.0
        avg_duration = 0.0

    return {
        "time_in_market_pct": time_in_market,
        "avg_trade_duration": avg_duration,
    }


def calculate_drawdown_metrics(df):
    """Calculate detailed drawdown metrics"""
    df = to_polars(df)

    try:
        equity = df["adj_account_value"]
        drawdowns = equity / equity.cum_max() - 1.0
        durations = run_lengths(drawdowns < 0)

        return {
            "max_drawdown_pct": clean_float(drawdowns.min() * 100, 3),
            "avg_drawdown_pct": clean_float(drawdowns.mean() * 100, 3),
            "max_drawdown_duration": clean_float(durations.max(), 3),
            "avg_drawdown_duration": clean_float(durations.mean(), 3),
            "current_drawdown": clean_float(drawdowns[-1] * 100, 3),
        }
    except NUMERIC_ERRORS:
        return {
            "max_drawdown_pct": 0.0,
            "avg_drawdown_pct": 0.0,
            "max_drawdown_duration": 0.0,
            "avg_drawdown_duration": 0.0,
            "current_drawdown": 0.0,
        }


def calculate_risk_metrics(df):
    """Calculate risk-adjusted return metrics"""
    df = to_polars(df)

    try:
        returns = finite(df["adj_account_value_change_perc"])
        negative_returns = returns.filter(returns < 0)

        downside_std = clean_float(negative_returns.std())
        avg_return = clean_float(returns.mean())
        sortino_ratio = clean_float(avg_return / downside_std, 3) if downside_std else 0.0

        equity = df["adj_account_value"]
        drawdowns = equity / equity.cum_max() - 1.0
        max_drawdown = abs(clean_float(drawdowns.min()))
        calmar_ratio = clean_float(avg_return / max_drawdown, 3) if max_drawdown else 0.0

        return {
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "value_at_risk_95": clean_float(
                returns.quantile(0.05, interpolation="linear"), 3
            ),
            "annualized_volatility": clean_float(
                clean_float(returns.std()) * (TRADING_DAYS_PER_YEAR**0.5), 3
            ),
            "downside_deviation": clean_float(downside_std, 3),
        }
    except NUMERIC_ERRORS:
        return {
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "value_at_risk_95": 0.0,
            "annualized_volatility": 0.0,
            "downside_deviation": 0.0,
        }


def calculate_trade_streaks(trade_log_df):
    """Calculate winning and losing streaks"""
    empty = {
        "current_streak": 0,
        "max_win_streak": 0,
        "max_loss_streak": 0,
        "avg_win_streak": 0.0,
        "avg_loss_streak": 0.0,
    }
    trade_log_df = to_polars(trade_log_df)
    if trade_log_df.is_empty():
        return empty

    try:
        wins = (trade_log_df["adj_account_value_change_perc"] > 0).fill_null(False)
        if len(wins) == 0:
            return empty

        win_streaks = run_lengths(wins)
        loss_streaks = run_lengths(~wins)

        last_value = wins[-1]
        current_streak = 0
        for value in reversed(wins.to_list()):
            if value == last_value:
                current_streak += 1
            else:
                break

        return {
            "current_streak": int(current_streak),
            "max_win_streak": int(clean_float(win_streaks.max())),
            "max_loss_streak": int(clean_float(loss_streaks.max())),
            "avg_win_streak": clean_float(win_streaks.mean(), 3),
            "avg_loss_streak": clean_float(loss_streaks.mean(), 3),
        }
    except NUMERIC_ERRORS:
        return empty


def calculate_time_analysis(df):
    """Calculate time-based performance metrics"""
    df = to_polars(df)

    try:
        equity = df.select(["date", "adj_account_value"]).sort("date")
        daily_returns = _resampled_returns(equity, "1d")
        monthly_returns = _resampled_returns(equity, "1mo")

        return {
            "best_day": clean_float(daily_returns.max() * 100, 3),
            "worst_day": clean_float(daily_returns.min() * 100, 3),
            "avg_daily_return": clean_float(daily_returns.mean() * 100, 3),
            "daily_return_std": clean_float(clean_float(daily_returns.std()) * 100, 3),
            "profitable_days_pct": clean_float(_positive_perc(daily_returns), 3),
            "best_month": clean_float(monthly_returns.max() * 100, 3),
            "worst_month": clean_float(monthly_returns.min() * 100, 3),
            "avg_monthly_return": clean_float(monthly_returns.mean() * 100, 3),
            "monthly_return_std": clean_float(
                clean_float(monthly_returns.std()) * 100, 3
            ),
            "profitable_months_pct": clean_float(_positive_perc(monthly_returns), 3),
        }
    except NUMERIC_ERRORS:
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


def _resampled_returns(equity: pl.DataFrame, every: str) -> pl.Series:
    """Period over period returns of the last equity value in each period."""
    periods = equity.group_by_dynamic("date", every=every).agg(
        pl.col("adj_account_value").last()
    )
    return finite(periods["adj_account_value"].pct_change())


def _positive_perc(returns: pl.Series) -> float:
    if len(returns) == 0:
        return 0.0
    return (returns > 0).sum() / len(returns) * 100


def calculate_return_perc(trade_log_df):
    """Calculate return percentage with protection against NaN values"""
    trade_log_df = to_polars(trade_log_df)
    if trade_log_df.is_empty():
        return 0.0

    try:
        equity = trade_log_df["adj_account_value"]
        if equity[0]:
            first_val = float(equity[0])
            last_val = float(equity[-1])
            if last_val == 0:
                return 0.0
            return clean_float(100 - (first_val / last_val) * 100, 3)
    except NUMERIC_ERRORS:
        return 0.0
    return 0.0


def calculate_buy_and_hold_perc(df):
    """Calculate buy and hold percentage with protection against NaN values"""
    df = to_polars(df)

    try:
        close = df["close"]
        first_close = float(close[0])
        last_close = float(close[-1])
        if last_close == 0:
            return 0.0
        return clean_float((1 - (first_close / last_close)) * 100, 3)
    except NUMERIC_ERRORS:
        return 0.0


def calculate_shape_ratio(df):
    """Calculate Sharpe ratio with protection against NaN values"""
    df = to_polars(df)

    try:
        returns = finite(df["adj_account_value_change_perc"])
        mean_return = returns.mean()
        std_return = returns.std()
        if mean_return is None or not std_return:
            return 0.0
        sharpe_ratio = (len(df) ** 0.5) * (mean_return / std_return)
        return clean_float(sharpe_ratio, 3)
    except NUMERIC_ERRORS:
        return 0.0


def calculate_perc_missing_safe(df):
    """Wrapper to keep calculate_perc_missing behavior explicit."""
    return calculate_perc_missing(df)
