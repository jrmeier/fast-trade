import datetime
import pandas as pd
from .build_data_frame import detect_time_unit


def build_summary(df, perf_start_time):

    # Not yet implimented
    # Exposure [%]                            94.29
    # Buy & Hold Return [%]                  703.46
    # Max. Drawdown [%]                      -33.61
    # Avg. Drawdown [%]                       -5.68
    # Max. Drawdown Duration      689 days 00:00:00
    # Avg. Drawdown Duration       41 days 00:00:00
    # Expectancy [%]                           6.92
    # SQN                                      1.77
    # Sharpe Ratio                             0.22
    # Sortino Ratio                            0.54
    # Calmar Ratio                             0.07
    time_unit = detect_time_unit(df.index[0])
    aux = df.drop_duplicates(subset="aux_balance", keep=False, inplace=False)
    trade_perc_series = aux.aux_balance.pct_change() * 100
    trade_time_held_series = pd.to_datetime(aux.aux_balance, unit=time_unit).diff()
    # return {}

    mean_trade_time_held = trade_time_held_series.mean()
    max_trade_time_held = trade_time_held_series.max()
    min_trade_time_held = trade_time_held_series.min()
    median_time_held = trade_time_held_series.median()

    max_trade_perc = trade_perc_series.max()
    min_trade_perc = trade_perc_series.min()
    mean_trade_perc = trade_perc_series.mean()
    median_trade_perc = trade_perc_series.median()

    win_trades = trade_perc_series[trade_perc_series > 0]
    loss_trades = trade_perc_series[trade_perc_series < 0]
    total_trades = len(aux)

    try:
        win_perc = (len(win_trades) / total_trades) * 100
    except ZeroDivisionError:
        win_perc = 0

    try:
        loss_perc = (len(loss_trades) / total_trades) * 100
    except ZeroDivisionError:
        loss_perc = 0

    try:
        return_perc = (aux.iloc[-1].aux_balance / aux.iloc[0].aux_balance) * 100 - 100
    except IndexError:
        return_perc = 0
    except ZeroDivisionError:
        return_perc = 0

    equity_peak = df["aux_balance"].max()

    equity_final = df.iloc[-1]["aux_balance"]

    perf_stop_time = datetime.datetime.utcnow()
    start_date = df.index[0]
    end_date = df.index[-1]

    summary = {
        "return_perc": round(return_perc, 3),
        "median_trade_len": median_time_held.total_seconds(),
        "mean_trade_len": mean_trade_time_held.total_seconds(),
        "max_trade_held": max_trade_time_held.total_seconds(),
        "min_trade_len": min_trade_time_held.total_seconds(),
        "best_trade_perc": round(max_trade_perc, 3),
        "min_trade_perc": round(min_trade_perc, 3),
        "median_trade_perc": round(median_trade_perc, 3),
        "mean": round(mean_trade_perc, 3),
        "num_trades": len(aux),
        "win_perc": round(win_perc, 3),
        "loss_perc": round(loss_perc, 3),
        "equity_peak": float(equity_peak),
        "equity_final": float(equity_final),
        "first_tic": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "last_tic": end_date.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tics": len(df.index),
        "test_duration": (perf_stop_time - perf_start_time).total_seconds(),
    }

    return summary
