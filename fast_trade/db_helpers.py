import sqlite3
import os

DEFAULT_DB_PATH = os.path.join(os.getcwd(), "fast_trade.db")


def get_connection(db_path=DEFAULT_DB_PATH):
    return sqlite3.connect(db_path)


def get_settings():
    conn = get_connection()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, value TEXT)"
    )
    settings = conn.execute("SELECT * FROM settings").fetchall()

    return {setting[1]: setting[2] for setting in settings}


def update_settings(settings):
    conn = get_connection()
    for setting in settings:
        conn.execute(
            "UPDATE settings SET value=? WHERE name=?", (settings[setting], setting)
        )
    conn.commit()


def get_candle_tables():
    conn = get_connection()
    return conn.execute(
        'SELECT name FROM sqlite_master WHERE type="table" AND name LIKE "%_candles"'
    ).fetchall()
