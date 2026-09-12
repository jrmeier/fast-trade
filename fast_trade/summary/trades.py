import datetime

import polars as pl

from fast_trade.frames import to_polars
from fast_trade.summary.helpers import (
    NUMERIC_ERRORS,
    clean_float,
    finite,
    replace_non_finite,
    run_ids,
)

ZERO_DELTA = datetime.timedelta(0)
# Trade timestamps come from different exchanges and archives, so gaps are
# rounded to the nearest 10 seconds to keep summaries stable.
TIME_HELD_ROUNDING_SECONDS = 10


def calculate_trade_quality(trade_log_df):
    """Calculate metrics that show trade quality beyond win/loss"""
    trade_log_df = to_polars(trade_log_df)

    try:
        changes = finite(trade_log_df["adj_account_value_change_perc"])
    except NUMERIC_ERRORS:
        changes = pl.Series("adj_account_value_change_perc", [], dtype=pl.Float64)

    wins = changes.filter(changes > 0)
    losses = changes.filter(changes < 0)

    try:
        profit_factor = abs(wins.sum() / losses.sum())
    except NUMERIC_ERRORS:
        profit_factor = 0

    try:
        win_loss_ratio = abs(wins.mean() / losses.mean())
    except NUMERIC_ERRORS:
        win_loss_ratio = 0

    return {
        "profit_factor": clean_float(profit_factor, 3),
        "avg_win_loss_ratio": clean_float(win_loss_ratio, 3),
        "largest_winning_trade": clean_float(changes.max(), 3),
        "largest_losing_trade": clean_float(changes.min(), 3),
    }


def calculate_effective_trades(df, trade_log_df):
    """Calculate trade metrics accounting for commission"""
    df = to_polars(df)
    trade_log_df = to_polars(trade_log_df)

    if trade_log_df.is_empty():
        return {
            "num_profitable_after_commission": 0,
            "num_unprofitable_after_commission": 0,
            "commission_drag_pct": 0.0,
        }

    trade_fees = _trade_fees(df, trade_log_df)
    if "adj_account_value_change" in trade_log_df.columns:
        pnl = trade_log_df["adj_account_value_change"].fill_null(0.0)
    else:
        pnl = pl.zeros(trade_log_df.height, dtype=pl.Float64, eager=True)

    profitable_trades = int((pnl > trade_fees).sum())

    final_equity = clean_float(df["adj_account_value"][-1]) if "adj_account_value" in df.columns else 0.0
    total_fees = clean_float(df["fee"].sum()) if "fee" in df.columns else 0.0
    commission_impact = total_fees / final_equity * 100 if final_equity else 0.0

    return {
        "num_profitable_after_commission": profitable_trades,
        "num_unprofitable_after_commission": int(trade_log_df.height - profitable_trades),
        "commission_drag_pct": clean_float(commission_impact, 3),
    }


def _trade_fees(df: pl.DataFrame, trade_log_df: pl.DataFrame) -> pl.Series:
    """Fees charged on each logged trade, matched on date when needed."""
    if "fee" in trade_log_df.columns:
        return trade_log_df["fee"].fill_null(0.0)

    if "fee" in df.columns and "date" in df.columns and "date" in trade_log_df.columns:
        fee_by_date = dict(zip(df["date"].to_list(), df["fee"].to_list()))
        return pl.Series(
            "fee",
            [clean_float(fee_by_date.get(date)) for date in trade_log_df["date"].to_list()],
            dtype=pl.Float64,
        )

    return pl.zeros(trade_log_df.height, dtype=pl.Float64, eager=True)


def create_trade_log(df):
    """Find all rows when a trade was entered or exited"""
    df = to_polars(df)
    if df.is_empty() or "in_trade" not in df.columns:
        return df

    in_trade = df["in_trade"].fill_null(False).cast(pl.Boolean)
    trade_log_df = (
        df.with_columns(_trade_run=run_ids(in_trade))
        .group_by("_trade_run", maintain_order=True)
        .first()
        .drop("_trade_run")
    )
    trade_log_df = replace_non_finite(trade_log_df)

    if "adj_account_value_change" in trade_log_df.columns:
        # A null change means the value is unknown rather than flat, so keep it.
        trade_log_df = trade_log_df.filter(
            (pl.col("adj_account_value_change") != 0).fill_null(True)
        )

    return trade_log_df


def summarize_time_held(trade_log_df):
    """Mean, max, min, and median time between logged trades"""
    trade_log_df = to_polars(trade_log_df)
    if trade_log_df.is_empty() or "date" not in trade_log_df.columns:
        return (ZERO_DELTA, ZERO_DELTA, ZERO_DELTA, ZERO_DELTA)

    dates = trade_log_df["date"]
    if dates.dtype not in (pl.Date, pl.Datetime):
        dates = dates.cast(pl.Datetime, strict=False)

    deltas = dates.diff().drop_nulls()
    if deltas.is_empty():
        return (ZERO_DELTA, ZERO_DELTA, ZERO_DELTA, ZERO_DELTA)

    seconds = deltas.dt.total_seconds().cast(pl.Float64)
    seconds = (seconds / TIME_HELD_ROUNDING_SECONDS).round() * TIME_HELD_ROUNDING_SECONDS

    return (
        datetime.timedelta(seconds=clean_float(seconds.mean())),
        datetime.timedelta(seconds=clean_float(seconds.max())),
        datetime.timedelta(seconds=clean_float(seconds.min())),
        datetime.timedelta(seconds=clean_float(seconds.median())),
    )


def summarize_trade_perc(trade_log_df):
    """Calculate trade percentages with protection against NaN values"""
    trade_log_df = to_polars(trade_log_df)

    try:
        changes = finite(trade_log_df["adj_account_value_change_perc"])
    except NUMERIC_ERRORS:
        changes = pl.Series("adj_account_value_change_perc", [], dtype=pl.Float64)

    return (
        clean_float(changes.max(), 4),
        clean_float(changes.min(), 4),
        clean_float(changes.mean(), 4),
        clean_float(changes.median(), 4),
    )


def summarize_trades(trades, total_trades):
    """Calculate trade summaries with protection against NaN values"""
    trades = to_polars(trades)

    try:
        avg_perc = clean_float(finite(trades["adj_account_value_change_perc"]).mean()) * 100
    except NUMERIC_ERRORS:
        avg_perc = 0.0

    perc = trades.height / total_trades * 100 if total_trades else 0.0

    return (
        int(trades.height),
        clean_float(avg_perc, 3),
        clean_float(perc, 3),
    )
