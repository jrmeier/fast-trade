import pandas as pd
import os
import sqlite3
import datetime
from fast_trade.asset_explorer.cb_api import get_product_candles, store_df_to_sql


def get_last_conn():
    settings = get_settings()
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    playground_name = settings.get('last_playground')
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    return conn


def get_settings():
    # read the settings file
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    # if it doesn't exist, create it
    if not os.path.exists(playground_path):
        os.mkdir(playground_path)
    
    # create the settings database
    settings_db_path = os.path.join(playground_path, "settings.db")
    if not os.path.exists(settings_db_path):
        conn = sqlite3.connect(settings_db_path)
        # settings_df = pd.DataFrame(columns=["name", "value"])
        # settings_df = settings_df.set_index("name")
        data = [
            {
                "name": "last_playground",
                "value": None
            },
            {
                "name": "created_at",
                "value": datetime.datetime.utcnow()
            }
        ]
        # settings_df = settings_df.append(data, ignore_index=True)
        # insert the data into the database
        conn.cursor().execute("CREATE TABLE settings (name TEXT, value TEXT)")
        for d in data:
            conn.cursor().execute(f"INSERT INTO settings VALUES ('{d['name']}', '{d['value']}')")
        conn.commit()
        conn.close()
    else:
        print("settings db exists")
        conn = sqlite3.connect(settings_db_path)
        res = conn.cursor().execute("SELECT * FROM settings").fetchall()
        # turn this into a key value pair
        print(res)
        settings = {}
        for r in res:
            # set any primates to their correct type
            value = r[1]
            if value == "None":
                value = None
            elif value == "True":
                value = True
            elif value == "False":
                value = False
            elif value.isnumeric():
                value = int(value)
            elif value.replace(".", "").isnumeric():
                value = float(value)
            
            settings[r[0]] = value

    return settings

    # return the settings



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


def add_symbol_to_playground(playground_name: str,  symbol: str, update_status: callable = lambda x: None):
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    meta = get_playground_metadata(playground_name)
    start = datetime.datetime.fromisoformat(meta['start'])
    end = datetime.datetime.fromisoformat(meta['end'])
    data = get_product_candles(symbol, update_status=update_status, start=start, end=end)
    store_df_to_sql(data, f"{symbol}_candles", conn)

    # update the metadata
    update_playground_metadata(playground_name)


def update_playground_metadata(playground_name: str):
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    # read all file symbols
    table_names = load_playground(playground_name)
    symbols = [t for t in table_names if "_candles" in t]
    symbols = [s.split("_")[0] for s in symbols]

    # update the metadata
    curr_date = datetime.datetime.utcnow()
    res = conn.execute(f"UPDATE metadata SET end='{curr_date.isoformat()}', symbols='{','.join(symbols)}'")
    conn.commit()
    print("res: ", res)


def update_playground(playground_name: str, update_status: callable = lambda x: None):
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    table_names = load_playground(playground_name)
    print("table_names: ", table_names)
    symbols = [t for t in table_names if "_candles" in t]
    print("symbols: ", symbols)
    for table_name in symbols:
        symbol = table_name.split("_")[0]
        # get the latest date for this symbol
        max_sql = f"SELECT MAX(date) FROM `{table_name}`"
        max_date = conn.cursor().execute(max_sql).fetchone()[0]

        max_date = datetime.datetime.fromisoformat(max_date)
        curr_date = datetime.datetime.utcnow()
        data = get_product_candles(symbol, start=max_date, end=curr_date, update_status=update_status)
        store_df_to_sql(data, table_name, conn)
    
    # update the metadata
    res = conn.execute(f"UPDATE metadata SET end='{curr_date.isoformat()}', symbols='{','.join(symbols)}'")
    conn.commit()
    print("res: ", res)


def get_candle_data(symbol: str, start: datetime.datetime, end: datetime.datetime):
    conn = get_last_conn()
    table_name = f"{symbol}_candles"
    # set the start and end dates to sql
    start = start.isoformat()
    end = end.isoformat()
    data = pd.read_sql(f"SELECT * FROM `{table_name}` WHERE date BETWEEN '{start}' AND '{end}'", conn)
    print("candle_data: ", data.columns)
    # data.index = pd.to_datetime(data.date, unit='ms')
    data.set_index('date', inplace=True)

    return data


def get_last_candle_data(symbol: str, playground_name: str = None, conn: sqlite3.Connection = None):
    if conn is None:
        playground_path = os.path.join(os.getcwd(), "playgrounds")
        conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))

    if symbol.endswith("_candles"):
        symbol = symbol.split("_")[0]
    table_name = f"{symbol}_candles"
    data = pd.read_sql(f"SELECT * FROM `{table_name}` ORDER BY date DESC LIMIT 1", conn)

    ret = {}
    for row in data:
        ret[row] = data[row].values[0]
    return ret


def get_playground_metadata(playground_name: str):
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    conn = sqlite3.connect(os.path.join(playground_path, f"{playground_name}.db"))
    # metadata = pd.read_sql("SELECT * FROM metadata", conn)
    metadata = conn.execute("SELECT name, symbols, created_at, start, end FROM metadata").fetchone()
    meta_dict = {
        "name": metadata[0],
        "symbols": metadata[1],
        "created_at": metadata[2],
        "start": metadata[3],
        "end": metadata[4],
    }

    # load the symbol metadata
    symbols_data = []
    for symbol in meta_dict['symbols'].split(","):
        symbol_metadata = get_last_candle_data(symbol, conn=conn)
        symbol_metadata['symbol'] = symbol
        symbols_data.append(symbol_metadata)

    return {
        "name": meta_dict['name'],
        "symbols": meta_dict['symbols'].split(","),
        "created_at": meta_dict['created_at'],
        "start": meta_dict['start'],
        "end": meta_dict['end'],
        "symbols_data": symbols_data
    }


if __name__ == "__main__":
    # playground = add_symbol_to_playground("playground_2", "ETH-USD")
    playground = update_playground("pg1")
    print(playground)
