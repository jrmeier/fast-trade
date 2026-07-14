import datetime
from unittest import mock

import pandas as pd
import pytest

from test.archive_main_runners import run_update_archive_main
from fast_trade.archive import update_archive


def _sample_df():
    return pd.DataFrame(
        {
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [105.0],
            "volume": [1000.0],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )


@pytest.fixture
def archive_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    monkeypatch.setattr(update_archive, "ARCHIVE_PATH", str(tmp_path))
    return tmp_path


def test_update_single_archive_existing_parquet(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    df = _sample_df()
    df.index = pd.to_datetime(["2024-01-10"])
    df.to_parquet(exchange_dir / "BTCUSDT.parquet")

    with mock.patch("fast_trade.archive.update_archive.update_kline") as update_mock:
        update_archive.update_single_archive("BTCUSDT", "binanceus")
        update_mock.assert_called_once()
        kwargs = update_mock.call_args[1]
        assert kwargs["symbol"] == "BTCUSDT"
        assert kwargs["exchange"] == "binanceus"
        assert kwargs["start_date"] == pd.to_datetime("2024-01-10")


def test_update_single_archive_symbol_already_has_extension(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    _sample_df().to_parquet(exchange_dir / "BTCUSDT.parquet")

    with mock.patch("fast_trade.archive.update_archive.update_kline") as update_mock:
        update_archive.update_single_archive("BTCUSDT.parquet", "binanceus")
        assert update_mock.call_args[1]["symbol"] == "BTCUSDT"


def test_update_single_archive_missing_file_defaults_start(archive_path):
    with mock.patch("fast_trade.archive.update_archive.update_kline") as update_mock:
        update_archive.update_single_archive("ETHUSDT", "binanceus")
        start = update_mock.call_args[1]["start_date"]
        assert start is not None
        assert start < datetime.datetime.now(datetime.timezone.utc)


def test_update_single_archive_corrupt_parquet(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    (exchange_dir / "BTCUSDT.parquet").write_text("bad")

    with mock.patch("fast_trade.archive.update_archive.update_kline") as update_mock:
        update_archive.update_single_archive("BTCUSDT", "binanceus")
        start = update_mock.call_args[1]["start_date"]
        assert start is not None


def test_update_single_archive_read_exception(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    (exchange_dir / "BTCUSDT.parquet").write_text("")

    with mock.patch(
        "fast_trade.archive.update_archive._safe_read_parquet",
        side_effect=RuntimeError("read failed"),
    ), mock.patch("fast_trade.archive.update_archive.update_kline") as update_mock:
        update_archive.update_single_archive("BTCUSDT", "binanceus")
        assert update_mock.called


def test_update_single_archive_existing_parquet_with_date_column(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [110.0, 111.0],
            "low": [90.0, 91.0],
            "close": [105.0, 106.0],
            "volume": [1000.0, 1100.0],
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        }
    )
    df.to_parquet(exchange_dir / "BTCUSDT.parquet", index=False)

    with mock.patch("fast_trade.archive.update_archive.update_kline") as update_mock:
        update_archive.update_single_archive("BTCUSDT", "binanceus")
        assert update_mock.call_args[1]["start_date"] == pd.to_datetime("2024-01-02")


def test_update_archive_processes_symbols(archive_path):
    for exchange, symbol in [("binanceus", "BTCUSDT"), ("coinbase", "BTC-USD")]:
        exchange_dir = archive_path / exchange
        exchange_dir.mkdir(parents=True)
        _sample_df().to_parquet(exchange_dir / f"{symbol}.parquet")
    (archive_path / "skip.txt").write_text("")

    with mock.patch("fast_trade.archive.update_archive.update_kline"), mock.patch(
        "fast_trade.archive.update_archive.console.print"
    ) as print_mock:
        update_archive.update_archive()

    print_mock.assert_called()
    assert "Updated 2 symbols" in str(print_mock.call_args)


def test_update_archive_skips_non_parquet_files(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    _sample_df().to_parquet(exchange_dir / "BTCUSDT.parquet")
    (exchange_dir / "notes.txt").write_text("skip")

    with mock.patch("fast_trade.archive.update_archive.update_kline"), mock.patch(
        "fast_trade.archive.update_archive.console.print"
    ) as print_mock:
        update_archive.update_archive()

    assert "Updated 1 symbols" in str(print_mock.call_args)


def test_update_archive_progress_callback_invalid_perc(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    _sample_df().to_parquet(exchange_dir / "BTCUSDT.parquet")

    def fake_update(symbol, exchange, progress_callback=None, **kwargs):
        if progress_callback:
            progress_callback({"perc_complete": "not-a-number"})

    with mock.patch(
        "fast_trade.archive.update_archive.update_kline", side_effect=fake_update
    ), mock.patch("fast_trade.archive.update_archive.console.print"):
        update_archive.update_archive()


def test_update_archive_raises_on_failure(archive_path):
    exchange_dir = archive_path / "binanceus"
    exchange_dir.mkdir(parents=True)
    _sample_df().to_parquet(exchange_dir / "BTCUSDT.parquet")

    with mock.patch(
        "fast_trade.archive.update_archive.update_kline",
        side_effect=RuntimeError("update failed"),
    ), mock.patch("fast_trade.archive.update_archive.console.print"):
        with pytest.raises(RuntimeError, match="update failed"):
            update_archive.update_archive()


def test_main_block_runs(archive_path):
    run_update_archive_main(str(archive_path))
