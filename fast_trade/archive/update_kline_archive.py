# import ftc.api_adapters.coinbase as cb_api
from .coinbase_api import coinbase_api as cb_api
from .binance_api import binance_api as bn_api
import datetime
from .db_helpers import (
    get_latest_date_from_archive,
    get_archive_settings,
    store_kline_df_to_sql,
    normalize_symbol,
    connect_to_db,
)

import math
import logging


logger = logging.Logger()


def update_kline_archive(
    symbol: str, exchange: str, start=None, end=None, maxdate=None
) -> None:
    """
    Update the the local database with the latest kline data from the given dates

    Args:
    symbol: str: the symbol to update
    exchange: str: the exchange to update
    start: datetime: the start date to update from
    end: datetime: the end date to update to
    maxdate: bool: if true, then get the latest date from the api

    Returns:
    None

    """
    # print("Updating candle for: ",  symbol, exchange)
    # first, check the local archive and see if we have it already
    if not start:
        start = get_latest_date_from_archive(symbol, exchange)
    # if its not set, then we need to find the oldest date from the
    # settings and start filling it
    if not start:
        # this means its new and we need to add it to the candle meta table
        start = get_archive_settings().get("oldest_date_to_fetch")

    if maxdate or not start:
        if exchange == "coinbase":
            start = cb_api.get_oldest_day(symbol)
        elif exchange == "binanceus":
            start = bn_api.get_oldest_date_available(symbol)

    start = start.replace(tzinfo=datetime.timezone.utc)
    add_kline_meta(symbol, exchange, updating=True, first_date=start)

    start = start.replace(tzinfo=datetime.timezone.utc)

    if not end:
        end = datetime.datetime.utcnow()

    end = end.replace(tzinfo=datetime.timezone.utc)

    total_duration_hours = (end - start).total_seconds() / 3600
    hours_to_split = 3 if exchange == "coinbase" else 15
    num_calls = math.ceil(total_duration_hours / hours_to_split)
    # split up the dates to fetch 1 month at a time
    current_date = start
    last_date = None
    call_count = 0
    start_time = datetime.datetime.utcnow()
    missing_data_count = 0

    while current_date < end:
        now = datetime.datetime.utcnow()
        now = now.replace(tzinfo=datetime.timezone.utc)
        next_end_date = current_date + datetime.timedelta(days=7)
        # print(current_date, end)
        # print("Fetching: ", current_date)
        if next_end_date > now:
            next_end_date = now

        # fetch the data
        if exchange == "coinbase":
            df, status = cb_api.get_product_candles(
                symbol, start=current_date, end=next_end_date
            )
        elif exchange == "binanceus":
            # df, status = cb_api.get_product_candles(
            #     symbol, start=current_date, end=next_end_date
            # )
            df, status = bn_api.load_historical_klines_as_df(
                symbol, start_date=current_date, end_date=next_end_date
            )
        else:
            print("exchange not supported")
            break
        # print(status)
        # print("df", df)

        call_count += status.get("num_calls")

        perc_complete = round(call_count / num_calls * 100, 2)

        # Current time
        current_time = datetime.datetime.utcnow()
        # Calculate the elapsed time since the start
        elapsed_time = current_time - start_time

        # Calculate total estimated time based on current progress
        if perc_complete == 0:
            print("Unknown, no progress made yet")
        total_time_estimated = elapsed_time / (perc_complete / 100)

        # Calculate remaining time
        remaining_time = total_time_estimated - elapsed_time

        print(f"{symbol}: {perc_complete:.2f}% complete, {remaining_time} remaining")

        # store the data in the sqlite db

        if not df.empty:
            last_date = df.index[-1]
            last_date = last_date.to_pydatetime()
        else:
            print("No data found for: ", current_date, next_end_date)
            missing_data_count += 1
            # single_value = your_dataframe.index[index_position]

            # print("last_date", last_date)
        # print("Fetching: ", current_date, next_end_date)
        # time.sleep(1)
        if missing_data_count > 4:
            print("Too many missing data points, aborting")
            break
        store_kline_df_to_sql(df, exchange, symbol)
        current_date = next_end_date

    print("Done")


def add_kline_meta(
    symbol: str, exchange: str, updating=False, last_date=None, first_date=None
) -> None:
    """
    Add the symbol and exchange to the tracking table
    """
    conn = connect_to_db(f"{normalize_symbol(symbol)}_{exchange}")
    cursor = conn.cursor()
    exg_symbol = symbol
    symbol = normalize_symbol(symbol)
    # create if it doesnt exist
    table_name = "meta"
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            id INTEGER PRIMARY KEY,
            exg_symbol TEXT NOT NULL,
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            createdAt TIMESTAMP,
            first_date TIMESTAMP,
            last_date TIMESTAMP,
            updating BOOLEAN,
            enabled BOOLEAN DEFAULT TRUE
        );
        """
    )
    # it needs to be an update, not and insert
    # check if the symbol exists
    exists = cursor.execute(
        """
        SELECT count(*) FROM meta
        """,
    ).fetchone()[0]

    if exists:
        # update the record
        stmt = f"""UPDATE {table_name} SET updating = ?"""
        values = [updating]

        if first_date:
            stmt = stmt + ", first_date = ?"
            values.append(first_date)

        if last_date:
            stmt = stmt + ", last_date = ?"
            values.append(last_date)

        stmt = stmt + """ WHERE symbol = ? AND exchange = ?"""
        values.append(symbol)
        values.append(exchange)
        # cursor.execute(stmt, values)
    else:
        # build the insert statement
        stmt = """INSERT INTO meta"""
        # dynmically build the statement based on the input
        columns = ["exg_symbol", "symbol", "exchange", "updating"]
        values = [exg_symbol, symbol, exchange, updating]

        if first_date:
            columns.append("first_date")
            values.append(first_date)

        if last_date:
            columns.append("last_date")
            values.append(last_date)

        stmt = (
            stmt + f""" ({",".join(columns)}) VALUES ({",".join(["?"]*len(columns))})"""
        )

    # insert the latest date to t

    cursor.execute(stmt, values)
    conn.commit()
    conn.close()
