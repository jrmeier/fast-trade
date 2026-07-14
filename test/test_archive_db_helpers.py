import datetime
import os
import sqlite3
from unittest import mock

import pandas as pd
import pytest

from test.archive_main_runners import run_db_helpers_main
from fast_trade.archive import db_helpers


def _sample_df(index=None):
    if index is None:
        index = pd.to_datetime(["2024-01-01", "2024-01-02"])
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [110.0, 111.0],
            "low": [90.0, 91.0],
            "close": [105.0, 106.0],
            "volume": [1000.0, 1100.0],
        },
        index=index,
    )


@pytest.fixture
def archive_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    monkeypatch.setattr(db_helpers, "ARCHIVE_PATH", str(tmp_path))
    return tmp_path


def test_archive_path_file_parent_resolution(tmp_path, monkeypatch):
    archive_file = tmp_path / "archive.parquet"
    archive_file.write_text("x")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive_file))
    import importlib

    import fast_trade.archive.db_helpers as dh

    importlib.reload(dh)
    assert dh.ARCHIVE_PATH == str(tmp_path)


def test_atomic_write_parquet(tmp_path):
    path = str(tmp_path / "out.parquet")
    db_helpers._atomic_write_parquet(_sample_df(), path)
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")


def test_safe_read_parquet_success(tmp_path):
    path = str(tmp_path / "data.parquet")
    db_helpers._atomic_write_parquet(_sample_df(), path)
    df = db_helpers._safe_read_parquet(path)
    assert df is not None
    assert len(df) == 2


def test_safe_read_parquet_corrupt_removes_file(tmp_path):
    path = str(tmp_path / "bad.parquet")
    with open(path, "w") as f:
        f.write("not parquet")
    result = db_helpers._safe_read_parquet(path)
    assert result is None
    assert not os.path.exists(path)


def test_safe_read_parquet_remove_oserror(tmp_path):
    path = str(tmp_path / "bad.parquet")
    with open(path, "w") as f:
        f.write("not parquet")
    with mock.patch("fast_trade.archive.db_helpers.os.remove", side_effect=OSError("denied")):
        result = db_helpers._safe_read_parquet(path)
    assert result is None


def test_get_local_assets(archive_path):
    binance = archive_path / "binanceus"
    coinbase = archive_path / "coinbase"
    binance.mkdir()
    coinbase.mkdir()
    (binance / "BTCUSDT.parquet").write_text("")
    (binance / "_skip.parquet").write_text("")
    (coinbase / "BTC-USD.sqlite").write_text("")
    (archive_path / "notadir.txt").write_text("")

    assets = db_helpers.get_local_assets()
    assert ("binanceus", "BTCUSDT") in assets
    assert ("coinbase", "BTC-USD") in assets
    assert all(not sym.startswith("_") for _, sym in assets)


def test_update_klines_to_db_creates_archive_path(archive_path, monkeypatch):
    monkeypatch.setattr(db_helpers, "ARCHIVE_PATH", str(archive_path / "nested" / "archive"))
    path = db_helpers.update_klines_to_db(_sample_df(), "BTCUSDT", "binanceus")
    assert os.path.exists(path)


def test_update_klines_to_db_merges_existing_indexed_parquet(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    existing = pd.DataFrame(
        {
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [105.0],
            "volume": [1000.0],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )
    db_helpers._atomic_write_parquet(existing, str(exchange_dir / "BTCUSDT.parquet"))

    new_df = pd.DataFrame(
        {
            "open": [101.0],
            "high": [111.0],
            "low": [91.0],
            "close": [106.0],
            "volume": [1100.0],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )
    path = db_helpers.update_klines_to_db(new_df, "BTCUSDT", "binanceus")
    merged = pd.read_parquet(path)
    assert len(merged) == 2


def test_update_klines_to_db_creates_new_parquet(archive_path):
    df = _sample_df()
    path = db_helpers.update_klines_to_db(df, "BTCUSDT", "binanceus")
    assert path.endswith("binanceus/BTCUSDT.parquet")
    loaded = pd.read_parquet(path)
    assert len(loaded) == 2


def test_update_klines_to_db_merges_existing_with_date_column(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    existing = pd.DataFrame(
        {
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [105.0],
            "volume": [1000.0],
            "date": pd.to_datetime(["2024-01-01"]),
        }
    )
    existing.to_parquet(exchange_dir / "BTCUSDT.parquet", index=False)

    new_df = pd.DataFrame(
        {
            "open": [101.0],
            "high": [111.0],
            "low": [91.0],
            "close": [106.0],
            "volume": [1100.0],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )
    path = db_helpers.update_klines_to_db(new_df, "BTCUSDT", "binanceus")
    merged = pd.read_parquet(path)
    assert len(merged) == 2


def test_update_klines_to_db_recover_from_corrupt_existing(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    corrupt = exchange_dir / "BTCUSDT.parquet"
    corrupt.write_text("bad")

    path = db_helpers.update_klines_to_db(_sample_df(), "BTCUSDT", "binanceus")
    loaded = pd.read_parquet(path)
    assert len(loaded) == 2
    assert path == str(corrupt)


def test_connect_to_db_existing(archive_path):
    db_path = str(archive_path / "test.sqlite")
    conn = sqlite3.connect(db_path)
    conn.close()
    loaded = db_helpers.connect_to_db(db_path)
    assert loaded.execute("pragma journal_mode").fetchone()[0] == "wal"
    loaded.close()


def test_connect_to_db_missing_raises(archive_path):
    with pytest.raises(Exception, match="does not exist"):
        db_helpers.connect_to_db(str(archive_path / "missing.sqlite"), create=False)


def test_connect_to_db_create(archive_path):
    db_path = str(archive_path / "new.sqlite")
    conn = db_helpers.connect_to_db(db_path, create=True)
    conn.close()
    assert os.path.exists(db_path)


def test_migrate_sqlite_to_parquet(archive_path):
    sqlite_path = str(archive_path / "BTCUSDT.sqlite")
    parquet_path = str(archive_path / "BTCUSDT.parquet")
    conn = sqlite3.connect(sqlite_path)
    conn.execute(
        "CREATE TABLE klines (date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.execute(
        "INSERT INTO klines VALUES ('2024-01-01T00:00:00', 1, 2, 0.5, 1.5, 10)"
    )
    conn.commit()
    conn.close()

    db_helpers.migrate_sqlite_to_parquet(sqlite_path, parquet_path)
    df = pd.read_parquet(parquet_path)
    assert len(df) == 1


def test_standardize_df_drops_extra_columns_and_dedupes():
    idx = pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"])
    df = pd.DataFrame(
        {
            "open": ["1", "2", "3"],
            "high": ["2", "3", "4"],
            "low": ["0.5", "1", "2"],
            "close": ["1.5", "2.5", "3.5"],
            "volume": ["10", "20", "30"],
            "extra": ["x", "y", "z"],
        },
        index=idx,
    )
    result = db_helpers.standardize_df(df)
    assert list(result.columns) == ["open", "close", "high", "low", "volume"]
    assert len(result) == 2


def test_get_kline_from_parquet(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    db_helpers._atomic_write_parquet(_sample_df(), str(exchange_dir / "BTCUSDT.parquet"))

    start = datetime.datetime(2024, 1, 1)
    end = datetime.datetime(2024, 1, 2)
    df = db_helpers.get_kline("BTCUSDT", "binanceus", start, end)
    assert not df.empty


def test_get_kline_string_dates(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    db_helpers._atomic_write_parquet(_sample_df(), str(exchange_dir / "BTCUSDT.parquet"))

    df = db_helpers.get_kline(
        "BTCUSDT",
        "binanceus",
        start_date="2024-01-01T00:00:00",
        end_date="2024-01-02T00:00:00",
    )
    assert not df.empty


def test_get_kline_triggers_update_when_missing(archive_path):
    with mock.patch("fast_trade.archive.update_kline.update_kline") as update_mock:
        update_mock.side_effect = lambda **kwargs: db_helpers.update_klines_to_db(
            _sample_df(), kwargs["symbol"], kwargs["exchange"]
        )
        df = db_helpers.get_kline("BTCUSDT", "binanceus")
    assert not df.empty
    assert update_mock.called


def test_get_kline_sqlite_fallback_and_migrates(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    sqlite_path = exchange_dir / "BTCUSDT.sqlite"
    conn = sqlite3.connect(str(sqlite_path))
    conn.execute(
        "CREATE TABLE klines (date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.execute(
        "INSERT INTO klines VALUES ('2024-01-01T00:00:00', 1, 2, 0.5, 1.5, 10)"
    )
    conn.commit()
    conn.close()

    start = datetime.datetime(2024, 1, 1)
    df = db_helpers.get_kline("BTCUSDT", "binanceus", start_date=start)
    assert not df.empty
    assert (exchange_dir / "BTCUSDT.parquet").exists()


def test_get_kline_sqlite_with_end_date_filter(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    sqlite_path = exchange_dir / "BTCUSDT.sqlite"
    conn = sqlite3.connect(str(sqlite_path))
    conn.execute(
        "CREATE TABLE klines (date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.execute(
        "INSERT INTO klines VALUES ('2024-01-01T00:00:00', 1, 2, 0.5, 1.5, 10)"
    )
    conn.execute(
        "INSERT INTO klines VALUES ('2024-01-03T00:00:00', 2, 3, 1.5, 2.5, 20)"
    )
    conn.commit()
    conn.close()

    df = db_helpers.get_kline(
        "BTCUSDT",
        "binanceus",
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 1, 2),
    )
    assert not df.empty


def test_get_kline_parquet_corrupt_then_update_retry(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    corrupt = exchange_dir / "BTCUSDT.parquet"
    corrupt.write_text("bad")

    with mock.patch("fast_trade.archive.update_kline.update_kline") as update_mock:
        update_mock.side_effect = lambda **kwargs: db_helpers.update_klines_to_db(
            _sample_df(), kwargs["symbol"], kwargs["exchange"]
        )
        df = db_helpers.get_kline("BTCUSDT", "binanceus")
    assert not df.empty


def test_get_kline_parquet_with_date_column_index(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    df = _sample_df().reset_index().rename(columns={"index": "date"})
    df.to_parquet(exchange_dir / "BTCUSDT.parquet", index=False)

    loaded = db_helpers.get_kline("BTCUSDT", "binanceus")
    assert not loaded.empty


def test_get_kline_runtime_error_when_still_missing(archive_path):
    parquet_path = str(archive_path / "binanceus" / "BTCUSDT.parquet")

    def exists(path):
        return path == parquet_path

    with mock.patch("fast_trade.archive.update_kline.update_kline"), mock.patch(
        "fast_trade.archive.db_helpers.os.path.exists", side_effect=exists
    ), mock.patch("fast_trade.archive.db_helpers._safe_read_parquet", return_value=None):
        with pytest.raises(RuntimeError, match="Failed to load parquet"):
            db_helpers.get_kline("BTCUSDT", "binanceus")


def test_get_kline_after_update_reads_date_column_parquet(archive_path):
    parquet_path = archive_path / "binanceus" / "BTCUSDT.parquet"

    def exists(path):
        return str(path) == str(parquet_path)

    stored = _sample_df().reset_index().rename(columns={"index": "date"})

    def fake_update(**kwargs):
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        stored.to_parquet(parquet_path, index=False)

    with mock.patch("fast_trade.archive.db_helpers.os.path.exists", side_effect=exists), mock.patch(
        "fast_trade.archive.update_kline.update_kline", side_effect=fake_update
    ), mock.patch("fast_trade.archive.db_helpers._safe_read_parquet", side_effect=[None, stored]):
        df = db_helpers.get_kline("BTCUSDT", "binanceus")
    assert not df.empty


def test_main_block_runs(archive_path):
    run_db_helpers_main(str(archive_path))
