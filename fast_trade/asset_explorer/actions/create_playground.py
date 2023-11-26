import datetime
import os
import pandas as pd
import sqlite3
from pprint import pprint
from fast_trade.asset_explorer.cb_api import store_df_to_sql, get_product_candles


def create_playgroud(name: str = None, symbols: list = None, start: datetime = None, end: datetime = None):
    if not name:
        name = input("Enter a name for the playground: ")

    # strip anything that isn't a letter or number
    name = "".join([char for char in name if char.isalnum() or char == " "])
    name = name.replace(" ", "_")

    if not symbols:
        symbols = input("Enter a list of symbols to include in the playground separated by a comma: ")
        symbols = symbols.split(",")
        symbols = [symbol.strip() for symbol in symbols]

    if not start:
        start = input("Enter a start date for the playground (YYYY-MM-DD): ")
        start = datetime.datetime.fromisoformat(start)

    if not end:
        end = input("Enter an end date for the playground (YYYY-MM-DD): ")
        end = datetime.datetime.fromisoformat(end)

    playground = {
        "name": name,
        "symbols": symbols,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }

    playgrounds_path = f"{os.getcwd()}/playgrounds"
    if not os.path.exists(playgrounds_path):
        os.mkdir(playgrounds_path)
    else:
        if os.path.exists(os.path.join(playgrounds_path, f"{name}.db")):
            raise Exception(f"Playground {name} already exists")

    # now load the files for each symbol
    conn = sqlite3.connect(os.path.join(playgrounds_path, f"{name}.db"))

    for symbol in symbols:
        data = get_product_candles(symbol, start, end)
        store_df_to_sql(data, f"{symbol}_candles", conn)

    # store the playgound metadatda in the db
    playground_df = pd.DataFrame.from_dict(playground)
    playground_df.to_sql("metadata", conn, if_exists="replace")

    # print("Playground created with the following symbols: ", symbols)
    pprint(playground)
    return playground


if __name__ == "__main__":
    name = "pg1"
    symbols = ["BTC-USD"]
    start = datetime.datetime.fromisoformat("2023-11-20")
    end = datetime.datetime.fromisoformat("2023-11-21")
    create_playgroud(name, symbols, start, end)
