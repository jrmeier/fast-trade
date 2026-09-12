import math
import datetime

import polars as pl

from fast_trade.build_summary import (
    calculate_market_adjusted_returns,
    calculate_position_metrics,
    calculate_market_exposure,
    calculate_drawdown_metrics,
    calculate_risk_metrics,
    calculate_trade_streaks,
    calculate_time_analysis,
)


def _indexed(times):
    dates = [datetime.datetime.fromisoformat(value.replace("Z", "+00:00")) for value in times]
    return pl.DataFrame({"date": dates})


def test_calculate_market_adjusted_returns_simple():
    assert calculate_market_adjusted_returns(None, 12.345, 2.0) == 10.345


def test_calculate_position_metrics_core_fields():
    df = _indexed(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",
            "2025-01-01T00:03:00Z",
            "2025-01-01T00:04:00Z",
        ]
    )
    df = df.with_columns(
        pl.Series("in_trade", [False, True, True, False, True]),
        pl.Series("aux", [0.0, 0.01, 0.02, 0.0, 0.03]),
        pl.Series("fee", [0.0, 0.1, 0.1, 0.0, 0.2]),
        pl.Series("adj_account_value", [100, 101, 102, 103, 104]),
    )

    res = calculate_position_metrics(df)

    assert res["avg_position_size"] == 0.02
    assert res["max_position_size"] == 0.03
    assert res["avg_position_duration"] == 1.5  # groups [2, 1]
    assert round(res["total_commission_impact"], 3) == round(0.4 / 104 * 100, 3)


def test_calculate_market_exposure_time_and_duration():
    df = _indexed(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",
            "2025-01-01T00:03:00Z",
            "2025-01-01T00:04:00Z",
        ]
    )
    df = df.with_columns(pl.Series("in_trade", [False, True, True, False, True]))

    res = calculate_market_exposure(df)
    assert res["time_in_market_pct"] == 60.0
    assert res["avg_trade_duration"] == 1.5


def test_calculate_drawdown_metrics_core_values():
    df = _indexed(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",
            "2025-01-01T00:03:00Z",
            "2025-01-01T00:04:00Z",
        ]
    )
    df = df.with_columns(pl.Series("adj_account_value", [100, 110, 105, 90, 95]))

    res = calculate_drawdown_metrics(df)
    assert round(res["max_drawdown_pct"], 3) == -18.182
    assert round(res["current_drawdown"], 3) == -13.636
    assert res["max_drawdown_duration"] == 3.0
    assert res["avg_drawdown_duration"] == 3.0


def test_calculate_risk_metrics_values():
    df = _indexed(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",
            "2025-01-01T00:03:00Z",
        ]
    )
    df = df.with_columns(pl.Series("adj_account_value_change_perc", [0.0, 0.01, -0.02, 0.01]))
    # Provide an equity curve for calmar computation
    df = df.with_columns(
        ((1 + pl.col("adj_account_value_change_perc")).cum_prod() * 100).alias("adj_account_value")
    )

    res = calculate_risk_metrics(df)

    # Compute expected values mirroring implementation
    returns = df["adj_account_value_change_perc"]
    negative_returns = returns.filter(returns < 0)
    downside_std = negative_returns.std() if not negative_returns.is_empty() else 0.0
    avg_return = returns.mean()
    sortino = 0.0 if downside_std is None or not math.isfinite(downside_std) or downside_std == 0 else avg_return / downside_std
    equity = (1 + returns).cum_prod()
    dd = equity / equity.cum_max() - 1.0
    max_dd = abs(dd.min())
    calmar = 0.0 if max_dd == 0 else avg_return / max_dd

    assert round(res["sortino_ratio"], 3) == round(sortino, 3)
    assert round(res["calmar_ratio"], 3) == round(calmar, 3)
    assert round(res["value_at_risk_95"], 3) == round(returns.quantile(0.05, interpolation="linear"), 3)
    assert round(res["annualized_volatility"], 3) == round(returns.std() * (252 ** 0.5), 3)
    assert res["downside_deviation"] == 0.0


def test_calculate_trade_streaks_current_streak_is_contiguous():
    # Sequence: win, win, loss, loss, win, win -> last streak length should be 2
    trade_log_df = _indexed(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",
            "2025-01-01T00:03:00Z",
            "2025-01-01T00:04:00Z",
            "2025-01-01T00:05:00Z",
        ]
    ).with_columns(
        pl.Series("adj_account_value_change_perc", [0.1, 0.2, -0.1, -0.2, 0.05, 0.01])
    )
    res = calculate_trade_streaks(trade_log_df)
    assert res["current_streak"] == 2
    assert res["max_win_streak"] == 2
    assert res["max_loss_streak"] == 2


def test_calculate_time_analysis_daily_monthly():
    df = _indexed([
        "2025-01-30",
        "2025-01-31",
        "2025-02-01",
        "2025-02-02",
    ])
    df = df.with_columns(pl.Series("adj_account_value", [100, 110, 121, 121]))

    res = calculate_time_analysis(df.clone())

    # Daily last values: [100,110,121,121] -> daily returns: [nan, 0.1, 0.1, 0.0]
    # Metrics in percent
    assert res["best_day"] == 10.0
    assert res["worst_day"] == 0.0
    assert res["avg_daily_return"] == round(((0.1 + 0.1 + 0.0) / 3) * 100, 3)

    # Month-end last values: Jan 31=110, Feb 28=121 -> returns [nan, (121/110 -1)=0.1]
    assert res["best_month"] == 10.0
    assert res["worst_month"] == 10.0
    assert res["avg_monthly_return"] == 10.0
