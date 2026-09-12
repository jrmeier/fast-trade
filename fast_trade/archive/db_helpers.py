import datetime
import os
import sqlite3
import typing

import polars as pl

from ..utils import DATE_COL, ensure_date_column, resample_ohlcv

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive"))
if os.path.isfile(ARCHIVE_PATH):
    ARCHIVE_PATH = os.path.dirname(ARCHIVE_PATH)

KLINE_COLUMNS = [DATE_COL, "open", "high", "low", "close", "volume"]


def _atomic_write_parquet(df, path: str, index: bool = True) -> None:
    """Write a frame to parquet, swapping it in only once it is complete.

    ``index`` is only used for pandas style frames, which still reach this
    helper from fast_trade.portfolio.
    """
    tmp_path = path + ".tmp"
    if hasattr(df, "write_parquet"):
        df.write_parquet(tmp_path)
    else:
        df.to_parquet(tmp_path, index=index)
    os.replace(tmp_path, path)


def _safe_read_parquet(path: str) -> typing.Optional[pl.DataFrame]:
    try:
        return pl.read_parquet(path)
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
        exchange_path = os.path.join(ARCHIVE_PATH, exchange)
        if not os.path.isdir(exchange_path):
            continue
        for symbol in os.listdir(exchange_path):
            if symbol.startswith("_"):
                continue
            if symbol.endswith(".parquet"):
                all_assets.append((exchange, symbol.replace(".parquet", "")))
            elif symbol.endswith(".sqlite"):
                all_assets.append((exchange, symbol.replace(".sqlite", "")))

    return all_assets


def update_klines_to_db(df: pl.DataFrame, symbol: str, exchange: str) -> str:
    """
    Store the kline dataframe to the db

    Args:
        df (pl.DataFrame): The kline dataframe to store, with a date column
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

    if os.path.exists(symbol_path):
        existing = _safe_read_parquet(symbol_path)
        if existing is None:
            _atomic_write_parquet(df, symbol_path)
        else:
            combined = pl.concat([standardize_df(existing), df])
            # newer rows win when the same minute shows up twice
            combined = combined.unique(
                subset=[DATE_COL], keep="last", maintain_order=True
            ).sort(DATE_COL)
            _atomic_write_parquet(combined, symbol_path)
    else:
        _atomic_write_parquet(df, symbol_path)

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
    df = pl.read_database("SELECT * FROM klines", connection=conn)
    if DATE_COL in df.columns:
        df = ensure_date_column(df).sort(DATE_COL)
    _atomic_write_parquet(df, parquet_path)


def standardize_df(df: pl.DataFrame) -> pl.DataFrame:
    """Trim a kline frame down to the archive layout: date + OHLCV, sorted."""
    new_df = ensure_date_column(df).with_columns(pl.col(DATE_COL).cast(pl.Datetime("us")))

    new_df = new_df.sort(DATE_COL).unique(
        subset=[DATE_COL], keep="last", maintain_order=True
    )

    # drop any columns that arent klines
    new_df = new_df.select(KLINE_COLUMNS)

    return new_df.with_columns(
        [pl.col(col).cast(pl.Float64) for col in KLINE_COLUMNS[1:]]
    )


def get_kline(
    symbol: str,
    exchange: str,
    start_date: datetime.datetime = None,
    end_date: datetime.datetime = None,
    freq: str = "1Min",
) -> pl.DataFrame:
    """
    Get the klines from the db

    Returns a Polars DataFrame with a datetime "date" column aggregated to
    ``freq``. Windows without data are left out rather than filled in.
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
            df = ensure_date_column(df)

    if df is None:
        if os.path.exists(sqlite_path):
            conn = connect_to_db(sqlite_path)
            query = "SELECT * FROM klines"
            if start_date:
                query += f" WHERE date >= '{start_date.isoformat()}'"

            if end_date:
                query += f" AND date <= '{end_date.isoformat()}'"

            df = pl.read_database(query, connection=conn)
            df = ensure_date_column(df).sort(DATE_COL)
            _atomic_write_parquet(df, parquet_path)
        else:
            import fast_trade.archive.update_kline as update_kline

            update_kline.update_kline(
                symbol=symbol, exchange=exchange, start_date=start_date, end_date=end_date
            )
            if os.path.exists(parquet_path):
                df = _safe_read_parquet(parquet_path)
                if df is not None:
                    df = ensure_date_column(df)

    if df is None:
        raise RuntimeError(f"Failed to load parquet for {exchange}:{symbol}; file was corrupted or missing")

    # set the freq of the dataframe
    return resample_ohlcv(df, freq)


if __name__ == "__main__":
    symbol = "BTCUSDT"
    exchange = "binanceus"
    start_date = datetime.datetime(2024, 12, 12)
    end_date = datetime.datetime(2024, 12, 31)
    df = get_kline(symbol, exchange, start_date, end_date)
