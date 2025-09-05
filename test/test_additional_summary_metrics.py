import math
import pandas as pd

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
    idx = pd.to_datetime(times)
    df = pd.DataFrame(index=idx)
    df.index.name = "date"
    return df


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
    df["in_trade"] = [False, True, True, False, True]
    df["aux"] = [0.0, 0.01, 0.02, 0.0, 0.03]
    df["fee"] = [0.0, 0.1, 0.1, 0.0, 0.2]
    df["adj_account_value"] = [100, 101, 102, 103, 104]

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
    df["in_trade"] = [False, True, True, False, True]

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
    df["adj_account_value"] = [100, 110, 105, 90, 95]

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
    df["adj_account_value_change_perc"] = [0.0, 0.01, -0.02, 0.01]
    # Provide an equity curve for calmar computation
    equity = (1 + df["adj_account_value_change_perc"]).cumprod() * 100
    df["adj_account_value"] = equity.values

    res = calculate_risk_metrics(df)

    # Compute expected values mirroring implementation
    returns = df["adj_account_value_change_perc"]
    negative_returns = returns[returns < 0]
    downside_std = negative_returns.std() if not negative_returns.empty else 0.0
    avg_return = returns.mean()
    import pandas as _pd  # alias to avoid shadowing
    sortino = 0.0 if (_pd.isna(downside_std) or downside_std == 0) else avg_return / downside_std
    # drawdown for calmar
    # fabricate an adj_account_value series consistent with returns is non-trivial,
    # but calmar uses avg_return / |max_drawdown| of equity; we can approximate by
    # creating a synthetic equity curve from returns for expectation here.
    # Instead, derive calmar using the implementation route for safety:
    # Build equity curve with cumulative product of (1+return)
    equity = (1 + returns).cumprod()
    rolling_max = equity.expanding().max()
    dd = equity / rolling_max - 1.0
    max_dd = abs(dd.min())
    calmar = 0.0 if max_dd == 0 else avg_return / max_dd

    assert round(res["sortino_ratio"], 3) == round(sortino, 3)
    assert round(res["calmar_ratio"], 3) == round(calmar, 3)
    assert round(res["value_at_risk_95"], 3) == round(returns.quantile(0.05), 3)
    assert round(res["annualized_volatility"], 3) == round(returns.std() * (252 ** 0.5), 3)
    if _pd.isna(downside_std):
        assert _pd.isna(res["downside_deviation"])  # single negative return -> NaN std
    else:
        assert round(res["downside_deviation"], 3) == round(downside_std, 3)


def test_calculate_trade_streaks_current_streak_is_contiguous():
    # Sequence: win, win, loss, loss, win, win -> last streak length should be 2
    idx = pd.to_datetime(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",
            "2025-01-01T00:03:00Z",
            "2025-01-01T00:04:00Z",
            "2025-01-01T00:05:00Z",
        ]
    )
    trade_log_df = pd.DataFrame(
        {"adj_account_value_change_perc": [0.1, 0.2, -0.1, -0.2, 0.05, 0.01]},
        index=idx,
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
    df["adj_account_value"] = [100, 110, 121, 121]

    res = calculate_time_analysis(df.copy())

    # Daily last values: [100,110,121,121] -> daily returns: [nan, 0.1, 0.1, 0.0]
    # Metrics in percent
    assert res["best_day"] == 10.0
    assert res["worst_day"] == 0.0
    assert res["avg_daily_return"] == round(((0.1 + 0.1 + 0.0) / 3) * 100, 3)

    # Month-end last values: Jan 31=110, Feb 28=121 -> returns [nan, (121/110 -1)=0.1]
    assert res["best_month"] == 10.0
    assert res["worst_month"] == 10.0
    assert res["avg_monthly_return"] == 10.0
