import pandas as pd
import os
import sqlite3

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive"))

# update the kline archive by the given symbol and exchange
# get the archive path from the environment variable


def update_klines_to_db(df, symbol, exchange) -> str:
    """
    Store the kline dataframe to the db

    Args:
        df (pd.DataFrame): The kline dataframe to store
        symbol (str): The symbol of the klines
        exchange (str): The exchange of the klines

    Returns:
        str: The path to the db
    """
    # create the archive path if it doesn't exist
    if not os.path.exists(ARCHIVE_PATH):
        os.makedirs(ARCHIVE_PATH)
    # create the exchange path if it doesn't exist
    exchange_path = f"{ARCHIVE_PATH}/{exchange}"
    if not os.path.exists(exchange_path):
        os.makedirs(exchange_path)
    # create the symbol path if it doesn't exist
    symbol_path = f"{exchange_path}/{symbol}.sqlite"
    engine = connect_to_db(symbol_path, create=True)
    df = standardize_df(df)
    # print(df)
    df.to_sql("klines", con=engine, if_exists="append", index=True, index_label="date")

    return symbol_path


def connect_to_db(db_path: str, create: bool = False) -> sqlite3.Connection:
    """
    Connect to the sqlite database

    Args:
        db_name (str, optional): The name of the database to connect to. Defaults to "ftc".

    Returns:
        sqlite3.Connection: The connection to the database
    """
    conn_str = db_path
    # check if the db exists
    if not os.path.exists(conn_str) and not create:
        raise Exception(f"Database {conn_str} does not exist")

    conn = sqlite3.connect(conn_str)
    # if db_name == "ftc":
    conn.execute("pragma journal_mode=WAL")
    return conn


def standardize_df(df):
    new_df = df.copy()

    new_df = new_df[~new_df.index.duplicated(keep="last")]

    # drop any columns that arent klines
    allowed_columns = [
        "open",
        "close",
        "high",
        "low",
        "volume",
    ]
    new_df = new_df[allowed_columns]
    new_df = new_df.sort_index()

    new_df.open = pd.to_numeric(new_df.open)
    new_df.close = pd.to_numeric(new_df.close)
    new_df.high = pd.to_numeric(new_df.high)
    new_df.low = pd.to_numeric(new_df.low)
    new_df.volume = pd.to_numeric(new_df.volume)

    return new_df
