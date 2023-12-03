import datetime
import os
import pandas as pd
import sqlite3
from pprint import pprint
from fast_trade.asset_explorer.cb_api import store_df_to_sql, get_product_candles


def create_playground(name: str = None, symbols: list = None, start: datetime = None, end: datetime = None, update_status: callable = lambda x: None):
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
        "symbols": ",".join(symbols),
        "created_at": datetime.datetime.utcnow().isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    print("playground: ", playground)
    # store the playgound metadatda in the db
    playgrounds_path = f"{os.getcwd()}/playgrounds"
    conn = sqlite3.connect(os.path.join(playgrounds_path, f"{name}.db"))

    # create the metadata table
    conn.execute("CREATE TABLE IF NOT EXISTS metadata (name, symbols, created_at, start, end)")
    conn.execute("INSERT INTO metadata VALUES (?, ?, ?, ?, ?)", (name, playground["symbols"], playground["created_at"], playground["start"], playground["end"]))
    conn.commit()

    if not os.path.exists(playgrounds_path):
        os.mkdir(playgrounds_path)

    # now load the files for each symbol

    for symbol in symbols:
        data = get_product_candles(symbol, start, end, update_status=update_status)
        store_df_to_sql(data, f"{symbol}_candles", conn)

    # print("Playground created with the following symbols: ", symbols)
    pprint(playground)
    return playground


if __name__ == "__main__":
    name = "pg1"
    symbols = ["BTC-USD"]
    start = datetime.datetime.fromisoformat("2023-11-20")
    end = datetime.datetime.fromisoformat("2023-11-21")
    create_playground(name, symbols, start, end)
