import datetime
import numpy as np


def create_trade_log(df):
    trade_log = df.reset_index()
    trade_log = (
        trade_log.groupby(
            (trade_log["in_trade"] != trade_log["in_trade"].shift()).cumsum()
        )
        .first()
        .set_index("date")
    )

    return trade_log


def build_summary(df, perf_start_time, strategy):
    print("building the summary")
    # Not yet implimented
    # Exposure [%]                            94.29
    # Max. Drawdown [%]                      -33.61
    # Avg. Drawdown [%]                       -5.68
    # Max. Drawdown Duration      689 days 00:00:00
    # Avg. Drawdown Duration       41 days 00:00:00
    # Expectancy [%]                           6.92
    # SQN                                      1.77
    # Sharpe Ratio                             0.22
    # Sortino Ratio                            0.54
    # Calmar Ratio                             0.07

    print("done making trade log")

    trade_log = create_trade_log(df)

    trade_time_held_series = trade_log.index.to_series().diff()
    mean_trade_time_held = trade_time_held_series.mean()
    max_trade_time_held = trade_time_held_series.max()
    min_trade_time_held = trade_time_held_series.min()
    median_time_held = trade_time_held_series.median()

    print(trade_time_held_series["2020-07-07 21:07:01.208"].iloc)
    print(
        trade_time_held_series[trade_time_held_series == trade_time_held_series.min()]
    )
    trade_perc_series = trade_log.replace([np.inf, -np.inf], np.nan)

    max_trade_perc = trade_perc_series.max().aux_perc_change * 100
    min_trade_perc = trade_perc_series.min().aux_perc_change * 100
    mean_trade_perc = trade_perc_series.mean().aux_perc_change * 100
    median_trade_perc = trade_perc_series.median().aux_perc_change * 100

    win_trades = trade_log[trade_log.aux_perc_change >= 0]
    loss_trades = trade_log[trade_log.aux_perc_change < 0]

    total_trades = len(trade_log)

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

    equity_peak = df["aux"].max()

    equity_final = df.iloc[-1]["aux"]

    perf_stop_time = datetime.datetime.utcnow()
    start_date = df.index[0]
    end_date = df.index[-1]
    loss_perc = (len(loss_trades) / total_trades) * 100

    buy_and_hold_perc = 100 - df.iloc[0].close / (df.iloc[-1].close / 100)
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
        "equity_peak": float(equity_peak),
        "equity_final": float(equity_final),
        "first_tic": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "last_tic": end_date.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tics": len(df.index),
        "test_duration": (perf_stop_time - perf_start_time).total_seconds(),
    }

    return summary, trade_log
