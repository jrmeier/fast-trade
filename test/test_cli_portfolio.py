"""CLI tests for portfolio commands."""

import os
from unittest import mock

import pandas as pd
import pytest
from typer.testing import CliRunner

from fast_trade import cli as cli_mod
from fast_trade.cli import app


def _invoke(runner, args):
    return runner.invoke(app, args)


def test_portfolio_start_no_paper(cli_runner, strategy_file):
    result = _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-paper"])
    assert result.exit_code != 0


def test_portfolio_start_daemon(cli_runner, strategy_file, archive_env, monkeypatch):
    proc = mock.Mock(pid=12345)
    monkeypatch.setattr(cli_mod.subprocess, "Popen", mock.Mock(return_value=proc))
    result = _invoke(
        cli_runner,
        ["portfolio", "start", str(strategy_file), "--symbol", "BTC-USD", "--name", "testpf", "--cash", "5000"],
    )
    assert result.exit_code == 0
    assert "12345" in result.stdout


def test_portfolio_start_once_cycle(cli_runner, strategy_file, archive_env, sample_ohlcv, monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(50))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {"enter": [], "exit": [], "any_enter": [], "any_exit": [], "trailing_stop_loss": False})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod, "_apply_portfolio_action", lambda state, action, price, lsp, mls: (state, {"side": "buy", "price": price, "qty": 1, "notional": price}, action))
    monkeypatch.setattr(cli_mod, "_append_portfolio_log", mock.Mock())
    monkeypatch.setattr(cli_mod, "_append_portfolio_trades", mock.Mock())
    monkeypatch.setattr(cli_mod, "_save_portfolio_state", mock.Mock())
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)

    result = _invoke(
        cli_runner,
        ["portfolio", "start", str(strategy_file), "--no-daemon", "--once", "--name", "oncepf"],
    )
    assert result.exit_code == 0


def test_portfolio_start_error_paths(cli_runner, strategy_file, archive_env, monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", mock.Mock(side_effect=FileNotFoundError("no data")))
    monkeypatch.setattr(cli_mod, "_append_portfolio_log", mock.Mock())
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)
    _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--once", "--name", "errpf"])

    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: pd.DataFrame())
    _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--once", "--name", "empty"])

    df = pd.DataFrame({"close": [1.0]}, index=pd.date_range("2024-01-01", periods=1, freq="min"))
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: df)
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: pd.DataFrame())
    _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--once", "--name", "prep"])

    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "h")
    monkeypatch.setattr(cli_mod, "_apply_portfolio_action", lambda state, action, price, lsp, mls: (state, None, action))
    monkeypatch.setattr(cli_mod, "_save_portfolio_state", mock.Mock())
    _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--once", "--name", "hold"])


def test_portfolio_start_keyboard_interrupt(cli_runner, strategy_file, monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", mock.Mock(side_effect=KeyboardInterrupt()))
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)
    monkeypatch.setattr(cli_mod, "_portfolio_paths", lambda name: {"state": "/tmp/s", "log": "/tmp/l", "trades": "/tmp/t", "pid": "/tmp/p.pid"})
    with mock.patch("os.path.exists", return_value=True), mock.patch("os.remove"):
        _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--name", "ki"])


def test_portfolio_start_invalid_strategy(cli_runner, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    with mock.patch("fast_trade.cli.open_strat_file", return_value=[]):
        result = _invoke(cli_runner, ["portfolio", "start", str(bad), "--no-daemon"])
        assert result.exit_code != 0


def test_portfolio_status(cli_runner, archive_env, monkeypatch):
    state_path = archive_env / "portfolios" / "mypf" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"cash": 1000, "position_qty": 0}')
    pid_path = archive_env / "portfolios" / "mypf" / "runner.pid"
    pid_path.write_text("99999")

    with mock.patch("fast_trade.cli._portfolio_paths") as paths:
        paths.return_value = {"state": str(state_path), "pid": str(pid_path)}
        with mock.patch("os.kill") as kill:
            kill.return_value = None
            result = _invoke(cli_runner, ["portfolio", "status", "mypf"])
            assert result.exit_code == 0

    with mock.patch("fast_trade.cli._portfolio_paths") as paths:
        paths.return_value = {"state": str(state_path), "pid": str(pid_path)}
        with mock.patch("os.kill", side_effect=OSError("gone")):
            _invoke(cli_runner, ["portfolio", "status", "mypf"])

    with mock.patch("fast_trade.cli._portfolio_paths") as paths:
        paths.return_value = {"state": str(archive_env / "nope.json"), "pid": str(pid_path)}
        with mock.patch("fast_trade.cli._load_portfolio_state", return_value={}):
            bad = _invoke(cli_runner, ["portfolio", "status", "missing"])
            assert bad.exit_code != 0


def test_portfolio_stop(cli_runner, tmp_path, monkeypatch):
    pid_file = tmp_path / "runner.pid"
    pid_file.write_text("4242")
    with mock.patch("fast_trade.cli._portfolio_paths", return_value={"pid": str(pid_file)}), mock.patch(
        "os.kill"
    ) as kill, mock.patch("os.remove"):
        result = _invoke(cli_runner, ["portfolio", "stop", "mypf"])
        assert result.exit_code == 0
        kill.assert_called_with(4242, cli_mod.signal.SIGTERM)

    missing = tmp_path / "missing.pid"
    with mock.patch("fast_trade.cli._portfolio_paths", return_value={"pid": str(missing)}):
        _invoke(cli_runner, ["portfolio", "stop", "mypf"])

    pid_file2 = tmp_path / "bad.pid"
    pid_file2.write_text("bad")
    with mock.patch("fast_trade.cli._portfolio_paths", return_value={"pid": str(pid_file2)}):
        _invoke(cli_runner, ["portfolio", "stop", "mypf"])
