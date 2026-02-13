import datetime
import os
import sqlite3
import typing

import pandas as pd

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive"))


def _atomic_write_parquet(df: pd.DataFrame, path: str, index: bool = True) -> None:
    tmp_path = path + ".tmp"
    df.to_parquet(tmp_path, index=index)
    os.replace(tmp_path, path)


def _safe_read_parquet(path: str) -> typing.Optional[pd.DataFrame]:
    try:
        return pd.read_parquet(path)
    except Exception:
        # If the parquet is corrupted, remove it so we can recover cleanly.
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return None


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
            if symbol.startswith("_"):
                continue
            if symbol.endswith(".parquet"):
                all_assets.append((exchange, symbol.replace(".parquet", "")))
            elif symbol.endswith(".sqlite"):
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
    symbol_path = f"{exchange_path}/{symbol}.parquet"
    df = standardize_df(df)
    df.index.name = "date"

    if os.path.exists(symbol_path):
        existing = _safe_read_parquet(symbol_path)
        if existing is None:
            _atomic_write_parquet(df, symbol_path, index=True)
        else:
            if "date" in existing.columns:
                existing = existing.set_index("date")
            existing.index = pd.to_datetime(existing.index)
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
            _atomic_write_parquet(combined, symbol_path, index=True)
    else:
        _atomic_write_parquet(df, symbol_path, index=True)

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


def migrate_sqlite_to_parquet(sqlite_path: str, parquet_path: str) -> None:
    conn = connect_to_db(sqlite_path)
    df = pd.read_sql_query("SELECT * FROM klines", conn)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    _atomic_write_parquet(df, parquet_path, index=True)


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
    parquet_path = f"{ARCHIVE_PATH}/{exchange}/{symbol}.parquet"
    sqlite_path = f"{ARCHIVE_PATH}/{exchange}/{symbol}.sqlite"
    # if the db exists, if not try and downlaod it
    if not os.path.exists(parquet_path) and not os.path.exists(sqlite_path):
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

    df = None
    if os.path.exists(parquet_path):
        df = _safe_read_parquet(parquet_path)
        if df is not None:
            if "date" in df.columns:
                df = df.set_index("date")
            df.index = pd.to_datetime(df.index)

    if df is None:
        if os.path.exists(sqlite_path):
            conn = connect_to_db(sqlite_path)
            query = "SELECT * FROM klines"
            if start_date:
                query += f" WHERE date >= '{start_date.isoformat()}'"

            if end_date:
                query += f" AND date <= '{end_date.isoformat()}'"

            df = pd.read_sql_query(query, conn)
            df.date = pd.to_datetime(df.date)
            df = df.set_index("date")
            _atomic_write_parquet(df, parquet_path, index=True)
        else:
            import fast_trade.archive.update_kline as update_kline

            update_kline.update_kline(
                symbol=symbol, exchange=exchange, start_date=start_date, end_date=end_date
            )
            if os.path.exists(parquet_path):
                df = _safe_read_parquet(parquet_path)
                if df is not None:
                    if "date" in df.columns:
                        df = df.set_index("date")
                    df.index = pd.to_datetime(df.index)

    if df is None:
        raise RuntimeError(f"Failed to load parquet for {exchange}:{symbol}; file was corrupted or missing")

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
