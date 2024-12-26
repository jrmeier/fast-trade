import pandas as pd
import os
import sqlite3


# update the kline archive by the given symbol and exchange
# get the archive path from the environment variable
ARCHIVE_PATH = os.getenv("FT_ARCHIVE_PATH")


def connect_to_db(db_name: str, create: bool = False) -> sqlite3.Connection:
    """
    Connect to the sqlite database

    Args:
        db_name (str, optional): The name of the database to connect to. Defaults to "ftc".

    Returns:
        sqlite3.Connection: The connection to the database
    """
    conn_str = f"{ARCHIVE_PATH}/{db_name}"
    # check if the db exists
    if not os.path.exists(conn_str) and not create:
        raise Exception(f"Database {conn_str} does not exist")
    conn = sqlite3.connect(conn_str)
    # if db_name == "ftc":
    conn.execute("pragma journal_mode=WAL")
    return conn


def update_kline_archive(symbol, exchange):
    # read the kline archive
    # get the db name
    db_name = f"{ARCHIVE_PATH}/{exchange}/{symbol}.db"
    conn = connect_to_db(db_name)

    # fetch the last date
    last_date = pd.read_sql(f"SELECT MAX(date) FROM {symbol}_{exchange}", con=conn)
    # get the next date
