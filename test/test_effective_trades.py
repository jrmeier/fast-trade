import pandas as pd
import datetime as dt

from fast_trade.build_summary import calculate_effective_trades


def _make_df_with_trades():
    # Create a simple dataframe with two exit events aligned to indices t2 and t4
    idx = pd.to_datetime(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",  # exit 1 (profit 2.0, fee 0.5)
            "2025-01-01T00:03:00Z",
            "2025-01-01T00:04:00Z",  # exit 2 (loss -1.0, fee 0.5)
        ]
    )

    df = pd.DataFrame(index=idx)
    df.index.name = "date"
    df["adj_account_value"] = [100, 102, 104, 103, 102]
    df["adj_account_value_change"] = df["adj_account_value"].diff().fillna(0)
    df["adj_account_value_change_perc"] = df["adj_account_value"].pct_change().fillna(0)
    df["fee"] = [0.0, 0.0, 0.5, 0.0, 0.5]

    # Trade log with the two exit events only (indices 2 and 4)
    trade_log_df = df.loc[[idx[2], idx[4]], [
        "adj_account_value",
        "adj_account_value_change",
        "adj_account_value_change_perc",
    ]]

    return df, trade_log_df


def test_calculate_effective_trades_uses_absolute_pnl_vs_fee():
    df, trade_log_df = _make_df_with_trades()

    res = calculate_effective_trades(df, trade_log_df)

    # First trade: +2.0 P&L vs 0.5 fee => profitable
    # Second trade: -1.0 P&L vs 0.5 fee => unprofitable
    assert res["num_profitable_after_commission"] == 1
    assert res["num_unprofitable_after_commission"] == 1


def test_calculate_effective_trades_commission_drag_pct():
    df, trade_log_df = _make_df_with_trades()
    res = calculate_effective_trades(df, trade_log_df)

    # Total fees = 1.0; last adj_account_value = 102 => 1/102 * 100
    assert round(res["commission_drag_pct"], 3) == round(1.0 / 102 * 100, 3)

