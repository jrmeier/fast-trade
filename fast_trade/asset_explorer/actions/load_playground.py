import pandas as pd
import os
import sqlite3
import datetime
from fast_trade.asset_explorer.cb_api import get_product_candles, store_df_to_sql


def load_playground(name: str):

    playground_path = os.path.join(os.getcwd(), "playgrounds", f"{name}.db")
    if not os.path.exists(playground_path):
        raise ValueError(f"Playground {name} does not exist")

    conn = sqlite3.connect(playground_path)

    table_names = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
    table_names = table_names.name.tolist()

    print(table_names)

    return table_names


def add_symbol_to_playground(playground_name: str,  symbol: str):
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    data = get_product_candles(symbol)
    store_df_to_sql(data, f"{symbol}_ohlcv", conn)


def update_playground(playground_name: str):
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    print(playground_path)
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    table_names = load_playground(playground_name)

    for table_name in table_names:
        if "_candles" not in table_name:
            continue
        symbol = table_name.split("_")[0]
        # get the latest date for this symbol
        max_sql = f"SELECT MAX(date) FROM `{table_name}`"
        max_date = conn.cursor().execute(max_sql).fetchone()[0]

        print("max_date: ", max_date)
        max_date = datetime.datetime.fromisoformat(max_date)
        curr_date = datetime.datetime.utcnow()
        print("curr_date: ", curr_date)
        data = get_product_candles(symbol, start=max_date, end=curr_date)
        store_df_to_sql(data, table_name, conn)


if __name__ == "__main__":
    # playground = add_symbol_to_playground("playground_2", "ETH-USD")
    playground = update_playground("pg1")
    print(playground)
