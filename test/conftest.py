"""Shared fixtures for CLI tests."""

import datetime
from pathlib import Path

import polars as pl
import pytest
import yaml
from typer.testing import CliRunner


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def archive_env(tmp_path, monkeypatch):
    """Create a minimal archive layout and point ARCHIVE_PATH at it."""
    archive = tmp_path / "ft_archive"
    backtests = archive / "backtests"
    strategies = archive / "strategies"
    backtests.mkdir(parents=True)
    strategies.mkdir(parents=True)
    (archive / "binanceus").mkdir(parents=True)
    (archive / "coinbase").mkdir(parents=True)
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))
    return archive


def _write_summary(run_dir: Path, summary: dict) -> None:
    with open(run_dir / "summary.yml", "w") as fh:
        yaml.safe_dump(summary, fh, sort_keys=False)


def _write_parquet_frames(run_dir: Path, df: pl.DataFrame, trade_df: pl.DataFrame) -> None:
    df.write_parquet(run_dir / "dataframe.parquet")
    trade_df.write_parquet(run_dir / "trade_log.parquet")


@pytest.fixture
def sample_ohlcv():
    return pl.read_csv("./test/ohlcv_data.csv.txt").with_columns(
        pl.from_epoch("date", time_unit="s")
    )


@pytest.fixture
def backtest_run(archive_env, sample_ohlcv):
    """One saved backtest run with summary + parquet files."""
    run_id = "2026_01_01_12_00_00"
    run_dir = archive_env / "backtests" / run_id
    run_dir.mkdir(parents=True)
    summary = {
        "return_perc": 12.5,
        "num_trades": 3,
        "win_perc": 66.0,
        "loss_perc": 34.0,
        "sharpe_ratio": 1.2,
        "max_drawdown": -5.0,
        "total_fees": 0.5,
        "equity_final": 1125.0,
        "equity_peak": 1150.0,
        "test_duration": "30d",
        "position_metrics": {"avg_hold": 10},
        "strategy": {
            "name": "test",
            "symbol": "BTCUSDT",
            "exchange": "binanceus",
            "freq": "1H",
            "start": "2024-01-01",
            "stop": "2024-12-31",
            "base_balance": 1000,
        },
    }
    _write_summary(run_dir, summary)
    trade_df = pl.DataFrame(
        {
            "date": pl.datetime_range(
                start=datetime.datetime(2024, 1, 1),
                end=datetime.datetime(2024, 1, 1, 2),
                interval="1h",
                eager=True,
            ),
            "close": [100.0, 101.0, 102.0],
            "in_trade": [True, False, True],
            "action": ["e", "x", "e"],
        }
    )
    _write_parquet_frames(run_dir, sample_ohlcv.head(50), trade_df)
    return run_id, run_dir, summary


@pytest.fixture
def strategy_file(archive_env):
    path = archive_env / "strategies" / "test_strategy.yml"
    strat = {
        "name": "Test",
        "symbol": "BTCUSDT",
        "exchange": "binanceus",
        "freq": "1H",
        "start": "2024-01-01",
        "stop": "2024-12-31",
        "base_balance": 1000,
        "lot_size_perc": 1.0,
        "enter": [],
        "exit": [],
        "datapoints": [],
    }
    with open(path, "w") as fh:
        yaml.safe_dump(strat, fh, sort_keys=False)
    return path


@pytest.fixture
def mock_backtest_result(sample_ohlcv):
    trade_df = pl.DataFrame(
        {
            "date": [
                datetime.datetime(2024, 1, 1),
                datetime.datetime(2024, 1, 1, 1),
            ],
            "close": [100.0, 101.0],
            "in_trade": [True, False],
        }
    )
    return {
        "df": sample_ohlcv.head(20),
        "trade_df": trade_df,
        "summary": {
            "return_perc": 5.0,
            "num_trades": 2,
            "mean_trade_len": 120,
            "max_trade_held": 240,
            "min_trade_len": 60,
            "median_trade_len": 120,
            "strategy": {"name": "Test"},
        },
    }
