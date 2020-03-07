import datetime
import pandas as pd


def build_summary(df, starting_aux_bal, perf_start_time):

    # Not yet implimented
    # Exposure [%]                            94.29
    # Return [%]                             596.65
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

    aux = df.drop_duplicates(subset="aux_balance", keep=False, inplace=False)
    trade_perc_series = aux["aux_balance"].pct_change() * 100
    trade_time_held_series = pd.to_datetime(aux["date"], unit="s").diff()

    mean_trade_time_held = trade_time_held_series.mean()
    max_trade_time_held = trade_time_held_series.max()
    min_trade_time_held = trade_time_held_series.min()

    max_trade_perc = trade_perc_series.max()
    min_trade_perc = trade_perc_series.min()
    mean_trade_perc = trade_perc_series.mean()

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

    equity_peak_unit = df["aux_balance"].max()
    equity_final = df.iloc[-1]["aux_balance"]

    perf_stop_time = datetime.datetime.utcnow()
    start_date = df.index[0]
    end_date = df.index[-1]

    summary = {
        "return_perc": round(return_perc, 3),
        "mean_trade_len": str(mean_trade_time_held),
        "max_trade_held": str(max_trade_time_held),
        "min_trade_len": str(min_trade_time_held),
        "best_trade_perc": round(max_trade_perc, 3),
        "min_trade_perc": round(min_trade_perc, 3),
        "mean": round(mean_trade_perc, 3),
        "num_trades": len(aux),
        "win_perc": round(win_perc, 3),
        "loss_perc": round(loss_perc, 3),
        "equity_peak": df["aux_balance"].max(),
        "equity_final": equity_final,
        "equity_peak_unit": equity_peak_unit,
        "first_tic": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "last_tic": end_date.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tics": len(df.index),
        "test_duration": str(perf_stop_time - perf_start_time),
    }

    return summary
