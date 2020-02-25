import datetime
import numpy as np

def build_summary(df, aux, base, starting_aux_bal, start):
    df["base_balance"] = base
    df["aux_balance"] = aux

    aux_sum = {
        "start": float(starting_aux_bal),
        "end": round(float(df.iloc[-1]["aux_balance"]), 8),
        "max": round(float(df["aux_balance"].max()), 8),
    }

    base_sum = {
        "start": 0.0,
        "end": round(float(df.iloc[-1]["base_balance"]), 8),
        "max": round(float(df.iloc[-1]["base_balance"].max()), 8),
    }

    max_gain_perc = round((1 - (starting_aux_bal / df["aux_balance"].max())) * 100, 3)
    stop = datetime.datetime.utcnow()

    # Exposure [%]                            94.29
    # Equity Final [$]                     69665.12
    # Equity Peak [$]                      69722.15
    # Return [%]                             596.65
    # Buy & Hold Return [%]                  703.46
    # Max. Drawdown [%]                      -33.61
    # Avg. Drawdown [%]                       -5.68
    # Max. Drawdown Duration      689 days 00:00:00
    # Avg. Drawdown Duration       41 days 00:00:00
    # # Trades                                   93
    # Win Rate [%]                            53.76
    # Best Trade [%]                          56.98
    # Worst Trade [%]                        -17.03
    # Avg. Trade [%]                           2.44
    # Max. Trade Duration         121 days 00:00:00
    # Avg. Trade Duration          32 days 00:00:00
    # Expectancy [%]                           6.92
    # SQN                                      1.77
    # Sharpe Ratio                             0.22
    # Sortino Ratio                            0.54
    # Calmar Ratio                             0.07
 

    start_time = df.index[0]
    end_time = df.index[-1]
    diff_days = end_time - start_time
    duration = diff_days

    # print(df)
    return {
            "start": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration": str(duration),
            # "total_trades": total_trades,/
            "total_tics": len(df.index),
            "max_gain_perc": max_gain_perc,
            "base_sum": base_sum,
            "aux_sum": aux_sum,
        }