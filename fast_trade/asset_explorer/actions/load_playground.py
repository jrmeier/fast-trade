import pandas as pd
import os
import sqlite3
import datetime
from fast_trade.asset_explorer.cb_api import get_product_candles, store_df_to_sql


def get_playgrounds():
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    playgrounds = os.listdir(playground_path)
    playgrounds = [p.split(".")[0] for p in playgrounds if p.endswith(".db")]
    # remove the settings file
    playgrounds = [p for p in playgrounds if p != "settings"]

    return playgrounds


def load_playground(name: str):

    playground_path = os.path.join(os.getcwd(), "playgrounds", f"{name}.db")
    if not os.path.exists(playground_path):
        raise ValueError(f"Playground {name} does not exist")

    conn = sqlite3.connect(playground_path)

    table_names = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
    table_names = table_names.name.tolist()

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


def get_playground_metadata(playground_name: str):
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    # metadata = pd.read_sql("SELECT * FROM metadata", conn)
    metadata = conn.execute("SELECT * FROM metadata").fetchall()
    # print("metadata: ", metadata)
    meta_dict = {}
    for row in metadata:
        meta_dict[row[0]] = row[1]
    return {
        "name": meta_dict['name'],
        "symbols": meta_dict['symbols'].split(","),
        "created_at": meta_dict['created_at'],
        "start": meta_dict['start'],
        "end": meta_dict['end'],
    }
    # as_dict = metadata.to_dict()
    # print("as_dict: ", as_dict)
    # return {
    #     "name": as_dict['index']['name'],
    #     "symbols": as_dict['index']['symbols'].split(","),
    #     "created_at": as_dict['index']['created_at'],
    #     "start": as_dict['index']['start'],
    #     "end": as_dict['index']['end'],
    # }
    # return metadata.to_dict()['index']


if __name__ == "__main__":
    # playground = add_symbol_to_playground("playground_2", "ETH-USD")
    playground = update_playground("pg1")
    print(playground)
