import random
from store import generate_random_name


def generate_strategy():
    charts = ["m", "h", "d"]
    t1 = random.randint(1, 100)
    t2 = random.randint(t1 + 1, t1 * 2)
    t3 = random.randint(t2 + 1, t2 * 3)
    chart = random.choice(charts)
    time1 = f"{t1}{chart}"
    time2 = f"{t2}{chart}"
    time3 = f"{t3}{chart}"
    ema_exit = random.choice(["short", "mid", "long"])
    return {
        "name": generate_random_name(),
        "enter": [["close", ">", "mid"], ["close", ">", "long"]],
        "exit": [["close", "<", ema_exit]],
        "indicators": [
            {"ref": "short", "name": "ta.ema", "timeperiod": time1, "df": "close"},
            {"ref": "mid", "name": "ta.ema", "timeperiod": time2, "df": "close"},
            {"ref": "long", "name": "ta.ema", "timeperiod": time3, "df": "close"},
        ],
    }


if __name__ == "__main__":

    print(generate_strategy())
