import datetime
import time
from .db_helpers import connect_to_db
import os
from .update_kline import update_kline


ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive"))



def update_single_archive(symbol: str, exchange: str):
    # check the oldest date in the existing archive
    if not symbol.endswith(".sqlite"):
        symbol = symbol + ".sqlite"
    path = os.path.join(ARCHIVE_PATH, exchange, symbol)
    db = connect_to_db(path)

    now = datetime.datetime.now()
    now = now.replace(second=0, microsecond=0)
    now = now.replace(tzinfo=datetime.timezone.utc)

    start_date = db.execute("SELECT max(date) FROM klines").fetchone()[0]
    print(start_date)

    if start_date is None:
        start_date = now - datetime.timedelta(days=7)
    else:
        start_date = datetime.datetime.fromisoformat(start_date)

    actual_symbol = symbol.replace(".sqlite", "")
    print(f"Updating {actual_symbol} from {exchange} from {start_date} to {now}")

    update_kline(actual_symbol, exchange, start_date, now)


def update_archive():
    """Read the archive and update the klines"""
    count = 0
    start_time = time.time()

    for exchange in os.listdir(ARCHIVE_PATH):
        for symbol in os.listdir(os.path.join(ARCHIVE_PATH, exchange)):
            if symbol.startswith("_") or not symbol.endswith(".sqlite"):
                # ignore files that start with an underscore
                continue
            update_single_archive(symbol, exchange)
            count += 1

    print(f"Updated {count} symbols in {time.time() - start_time} seconds")


if __name__ == "__main__":
    update_archive()
