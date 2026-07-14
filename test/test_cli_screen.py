"""CLI tests for screen commands."""

import json
from unittest import mock

from typer.testing import CliRunner

from fast_trade import cli as cli_mod
from fast_trade.cli import app


def test_screen_hmm_basic(cli_runner, monkeypatch, tmp_path):
    payload = {"results": [{"symbol": "BTC-USD", "score": 1.5, "price": 100}], "skipped": []}
    monkeypatch.setattr("fast_trade.ml.hmm_data.screen_from_config", lambda cfg: payload)

    result = cli_runner.invoke(
        app,
        [
            "screen",
            "hmm",
            "--exchange",
            "coinbase",
            "--symbol",
            "BTC-USD",
            "--live",
            "--horizon",
            "5",
            "--json-out",
            str(tmp_path / "out.json"),
            "--md-out",
            str(tmp_path / "out.md"),
        ],
    )
    assert result.exit_code == 0
    assert "BTC-USD" in result.stdout


def test_screen_hmm_with_config(cli_runner, monkeypatch, tmp_path):
    cfg = tmp_path / "screen.yml"
    cfg.write_text(
        json.dumps(
            {
                "exchange": "binanceus",
                "symbols": ["ETH-USD"],
                "settings": {"lookback_days": 100},
            }
        )
    )
    monkeypatch.setattr(
        "fast_trade.ml.hmm_data.screen_from_config",
        lambda cfg: {"results": [], "skipped": [{"symbol": "ETH-USD", "reason": "x"}]},
    )
    result = cli_runner.invoke(app, ["screen", "hmm", str(cfg)])
    assert result.exit_code == 0


def test_screen_hmm_bad_exchange(cli_runner):
    result = cli_runner.invoke(app, ["screen", "hmm", "--exchange", "invalid_exchange"])
    assert result.exit_code != 0
