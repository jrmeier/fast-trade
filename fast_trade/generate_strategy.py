import random
from store import generate_random_name



def generate_strategy():
    time1 = random.randint(0,100)
    time2 = random.randint(time1+1, time1*2)
    time3 = random.randint(time2+1, time2*3)
    ema_exit = random.choice(["short","mid","long"])
    return {
        "name": generate_random_name(),
        "enter": [
                [
                    "close",
                    ">",
                    "mid"
                ],
                [
                    "close",
                    ">",
                    "long"
                ]
            ],
            "exit": [
                [
                    "close",
                    "<",
                    ema_exit
                ]
            ],
            "indicators": [
                {
                    "ref": "short",
                    "name": "ta.ema",
                    "timeperiod": time1,
                    "df": "close"
                },
                {
                    "ref": "mid",
                    "name": "ta.ema",
                    "timeperiod": time2,
                    "df": "close"
                },
                {
                    "ref": "long",
                    "name": "ta.ema",
                    "timeperiod": time3,
                    "df": "close"
                }
            ]
            }


if __name__ == "__main__":

    print(generate_strategy())
