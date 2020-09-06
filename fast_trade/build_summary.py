import datetime
import numpy as np


def create_trade_log(df):
    """Finds all the rows when a trade was entered or exited

    Parameters
    ----------
        df: dataframe, from process_dataframe

    Returns
    -------
        trade_log_df: dataframe, of when transactions took place
    """

    trade_log = df.reset_index()
    trade_log = trade_log.groupby(
        (trade_log["in_trade"] != trade_log["in_trade"].shift()).cumsum()
    ).first()
    if "date" in trade_log.columns:
        trade_log = trade_log.set_index("date")
    else:
        trade_log = trade_log.set_index("index")

    return trade_log


def build_summary(df, perf_start_time, strategy):
    # Not yet implimented
    # Expectancy [%]                           6.92
    # SQN                                      1.77
    # Sharpe Ratio                             0.22
    # Sortino Ratio                            0.54
    # Calmar Ratio                             0.07

    trade_log = create_trade_log(df)

    trade_time_held_series = trade_log.index.to_series().diff()
    mean_trade_time_held = trade_time_held_series.mean()
    max_trade_time_held = trade_time_held_series.max()
    min_trade_time_held = trade_time_held_series.min()
    median_time_held = trade_time_held_series.median()

    trade_perc_series = trade_log.replace([np.inf, -np.inf], np.nan)

    max_trade_perc = trade_perc_series.max().aux_perc_change
    min_trade_perc = trade_perc_series.min().aux_perc_change
    mean_trade_perc = trade_perc_series.mean().aux_perc_change
    median_trade_perc = trade_perc_series.median().aux_perc_change

    win_trades = trade_log[trade_log.aux_perc_change >= 0]
    loss_trades = trade_log[trade_log.aux_perc_change < 0]

    total_trades = len(trade_log.index)

    try:
        win_perc = (len(win_trades) / total_trades) * 100
    except ZeroDivisionError:
        win_perc = 0
    except TypeError:
        win_perc = 0
    try:
        loss_perc = (len(loss_trades) / total_trades) * 100
    except ZeroDivisionError:
        loss_perc = 0

    if trade_log.iloc[0].total_value and trade_log.iloc[-1].total_value:
        return_perc = 100 - trade_log.iloc[0].total_value / (
            trade_log.iloc[-1].total_value / 100
        )
    else:
        return_perc = 0

    equity_peak = df["total_value"].max()

    equity_final = df.iloc[-1]["total_value"]

    perf_stop_time = datetime.datetime.utcnow()
    start_date = df.index[0]
    end_date = df.index[-1]
    loss_perc = (len(loss_trades) / total_trades) * 100

    first_close = df.iloc[0].close
    last_close = df.iloc[-1].close

    buy_and_hold_perc = (1 - (first_close / last_close)) * 100
    summary = {
        "return_perc": round(return_perc, 3),
        "buy_and_hold_perc": round(buy_and_hold_perc, 3),
        "median_trade_len": median_time_held.total_seconds(),
        "mean_trade_len": mean_trade_time_held.total_seconds(),
        "max_trade_held": max_trade_time_held.total_seconds(),
        "min_trade_len": min_trade_time_held.total_seconds(),
        "best_trade_perc": round(max_trade_perc, 3),
        "min_trade_perc": round(min_trade_perc, 3),
        "median_trade_perc": round(median_trade_perc, 3),
        "mean_trade_perc": round(mean_trade_perc, 3),
        "num_trades": total_trades,
        "win_perc": round(win_perc, 3),
        "loss_perc": round(loss_perc, 3),
        "equity_peak": round(float(equity_peak), 3),
        "equity_final": round(float(equity_final), 3),
        "first_tic": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "last_tic": end_date.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tics": len(df.index),
        "test_duration": (perf_stop_time - perf_start_time).total_seconds(),
    }

    return summary, trade_log
