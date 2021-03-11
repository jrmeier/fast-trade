import random


def generate_backtest():

    charts = [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "12h",
        "1d",
    ]

    t1 = random.randint(1, 50)
    t2 = random.randint(t1 + 1, t1 * 2)
    t3 = random.randint(t2 + 1, t2 * 2)

    chart = random.choice(charts)

    emas = ["short", "mid", "long"]
    ema_exit = random.choice(emas)
    emas.pop(emas.index(ema_exit))

    funcs = ["zlema", "ema", "smma", "sma"]
    # funcs = [ "ta.hma" ]
    ema_enter = random.choice(emas)
    func = random.choice(funcs)

    # backtest = backtest()

    df_columns = ["close", "volume"]
    # operator = [">", "<", "="]

    df_column = random.choice(df_columns)
    new_enter_logiz = []
    new_enter_logiz.append(df_column)
    new_enter_logiz.append(">")
    new_enter_logiz.append(ema_enter)

    new_exit_logiz = []
    new_exit_logiz.append(df_column)
    new_exit_logiz.append("<")
    new_exit_logiz.append(ema_exit)

    short_ind = {}
    short_ind["name"] = "short"
    short_ind["func"] = func
    short_ind["args"] = [t1]
    short_ind["df"] = "close"

    mid_ind = {}
    mid_ind["name"] = "mid"
    mid_ind["func"] = func
    mid_ind["args"] = [t2]
    mid_ind["df"] = "close"

    long_ind = {}
    long_ind["name"] = "short"
    long_ind["func"] = func
    long_ind["args"] = [t3]
    long_ind["df"] = "close"

    indicators = []
    indicators.append(short_ind)
    indicators.append(mid_ind)
    indicators.append(long_ind)

    exit_logiz = []
    enter_logiz = []
    exit_logiz.append(new_exit_logiz)
    enter_logiz.append(new_enter_logiz)

    return {
        "name": "generated",
        "chart_period": f"{chart}",
        "enter": [["close", ">", ema_enter]],
        "exit": [["close", "<", ema_exit]],
        "indicators": [
            {"name": "short", "func": func, "args": [t1], "df": "close"},
            {"name": "mid", "func": func, "args": [t2], "df": "close"},
            {"name": "long", "func": func, "args": [t3], "df": "close"},
        ],
    }
