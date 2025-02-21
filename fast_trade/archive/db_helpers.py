import datetime
import os
import sqlite3
import typing

import pandas as pd

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive"))


# update the kline archive by the given symbol and exchange
# get the archive path from the environment variable
def get_local_assets() -> typing.List[typing.Tuple[str, str]]:
    """
    Get the local assets from the archive

    Returns:
        typing.List[typing.Tuple[str, str]]: A list of tuples containing the exchange and symbol
    """
    all_assets = []

    for exchange in os.listdir(ARCHIVE_PATH):
        for symbol in os.listdir(os.path.join(ARCHIVE_PATH, exchange)):
            if symbol.startswith("_") or not symbol.endswith(".sqlite"):
                # ignore files that start with an underscore
                continue
            all_assets.append((exchange, symbol.replace(".sqlite", "")))

    return all_assets


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


def get_kline(
    symbol: str,
    exchange: str,
    start_date: datetime.datetime = None,
    end_date: datetime.datetime = None,
    freq: str = "1Min",
) -> pd.DataFrame:
    """
    Get the klines from the db
    """
    db_path = f"{ARCHIVE_PATH}/{exchange}/{symbol}.sqlite"
    # if the db exists, if not try and downlaod it
    if not os.path.exists(db_path):
        import fast_trade.archive.update_kline as update_kline

        update_kline.update_kline(
            symbol=symbol, exchange=exchange, start_date=start_date, end_date=end_date
        )

    if start_date is not None:
        if isinstance(start_date, str):
            start_date = datetime.datetime.fromisoformat(start_date)

    if end_date is not None:
        if isinstance(end_date, str):
            end_date = datetime.datetime.fromisoformat(end_date)

    conn = connect_to_db(db_path)
    query = "SELECT * FROM klines"
    if start_date:
        query += f" WHERE date >= '{start_date.isoformat()}'"

    if end_date:
        query += f" AND date <= '{end_date.isoformat()}'"

    df = pd.read_sql_query(query, conn)
    df.date = pd.to_datetime(df.date)
    df = df.set_index("date")
    # set the freq of the dataframe
    df = df.resample(freq).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    return df


if __name__ == "__main__":
    symbol = "BTCUSDT"
    exchange = "binanceus"
    start_date = datetime.datetime(2024, 12, 12)
    end_date = datetime.datetime(2024, 12, 31)
    df = get_kline(symbol, exchange, start_date, end_date)
    print(df)
