"""Focused tests for remaining CLI / helper coverage gaps."""

import asyncio
import datetime
import json
import os
import sqlite3
import sys
import threading
import time
from io import StringIO
from unittest import mock

import pandas as pd
import pytest
import typer
import yaml
from rich.console import Console
from typer.testing import CliRunner

import fast_trade.terminal_ui as tui
from fast_trade import cli as cli_mod
from fast_trade.cli import app
from fast_trade.cli_helpers import (
    _parse_simple_yaml,
    render_plot_preview,
    render_plot_preview_from_data,
)
from fast_trade import ftv


def _invoke(runner, args, **kwargs):
    return runner.invoke(app, args, **kwargs)


def _mock_tty(monkeypatch):
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)


import threading as _threading_mod

_RealThread = _threading_mod.Thread


class _RunnableThread:
    """Thread stand-in that actually runs target in a background thread."""

    def __init__(self, target=None, daemon=None):
        self._target = target
        self._thread = None
        self._alive = False
        self._daemon = daemon

    def start(self):
        if self._target is None:
            self._alive = True
            return

        def _run():
            try:
                self._target()
            finally:
                self._alive = False

        self._alive = True
        self._thread = _RealThread(target=_run, daemon=self._daemon)
        self._thread.start()

    def is_alive(self):
        if self._thread is not None and self._thread.is_alive():
            return True
        return self._alive

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._alive = False


# --- backtest live / interactive ---


def test_backtest_live_invalid_start_and_progress(cli_runner, archive_env, mock_backtest_result, monkeypatch):
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)

    def fake_update(**kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            cb({"perc_complete": "bad"})
        return None

    monkeypatch.setattr(cli_mod, "update_kline", fake_update)

    strat = archive_env / "strategies" / "bad_start.yml"
    strat.write_text(
        yaml.safe_dump(
            {
                "symbol": "BTCUSDT",
                "exchange": "binanceus",
                "freq": "1H",
                "start": "not-a-valid-date",
                "stop": "2024-12-31",
            }
        )
    )
    assert _invoke(cli_runner, ["backtest", str(strat), "--live"]).exit_code == 0


def test_backtest_interactive_details_confirm(strategy_file, mock_backtest_result, monkeypatch):
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}
    with mock.patch.object(cli_mod.Confirm, "ask", side_effect=[True, False]):
        cli_mod.backtest(
            ctx,
            strategy=str(strategy_file),
            mods=None,
            save_results=False,
            save_all=False,
            preview=True,
            plot=False,
            live=False,
            details=False,
            show_strategy=False,
        )


def test_backtest_summary_non_numeric_trade_len(cli_runner, strategy_file, monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "run_backtest",
        lambda *a, **k: {"summary": {"mean_trade_len": "bad"}, "df": None, "trade_df": None},
    )
    assert _invoke(cli_runner, ["backtest", str(strategy_file)]).exit_code == 0


# --- backtests interactive pick ---


def test_backtests_pick_from_list_and_latest_empty(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}

    with mock.patch.object(cli_mod.Confirm, "ask", return_value=True), mock.patch.object(
        cli_mod.IntPrompt, "ask", return_value=1
    ):
        cli_mod.backtests_cmd(ctx, action="list", run_id=None, limit=10, last=0, index=None)

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=1):
        cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=0, index=None)

    for child in list((archive_env / "backtests").iterdir()):
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
    assert _invoke(cli_runner, ["backtests", "latest"]).exit_code != 0


def test_backtests_pick_out_of_range_and_decline(archive_env, backtest_run):
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}

    with mock.patch.object(cli_mod.Confirm, "ask", return_value=False):
        cli_mod.backtests_cmd(ctx, action="list", run_id=None, limit=10, last=0, index=None)

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=99):
        with pytest.raises(typer.Exit):
            cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=0, index=None)

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=1):
        cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=1, index=None)


def test_backtests_pick_no_runs_direct(archive_env):
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}
    for child in (archive_env / "backtests").iterdir():
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
    with pytest.raises(typer.Exit):
        cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=0, index=None)


# --- migrate commands ---


def test_migrate_backtests_all_branches(cli_runner, archive_env, backtest_run, sample_ohlcv):
    run_id, run_dir, summary = backtest_run

    df_db = run_dir / "dataframe.db"
    con = sqlite3.connect(df_db)
    pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}).to_sql(
        "dataframe", con, index=False
    )
    con.close()

    trade_db = run_dir / "trade_log.db"
    con2 = sqlite3.connect(trade_db)
    pd.DataFrame({"close": [1.0], "in_trade": [True]}).to_sql("trade_log", con2, index=False)
    con2.close()

    (run_dir / "summary.json").write_text(json.dumps(summary))
    os.remove(run_dir / "summary.yml")

    assert _invoke(cli_runner, ["migrate_backtests", "--limit", "1"]).exit_code == 0

    with mock.patch("yaml.safe_dump", side_effect=RuntimeError("yaml fail")):
        (run_dir / "summary.json").write_text(json.dumps(summary))
        if (run_dir / "summary.yml").exists():
            os.remove(run_dir / "summary.yml")
        _invoke(cli_runner, ["migrate_backtests", "--limit", "1"])

    with mock.patch("fast_trade.cli.connect_to_db", side_effect=RuntimeError("db fail")):
        _invoke(cli_runner, ["migrate_backtests", "--limit", "1"])


def test_migrate_archive_skips_non_dirs(cli_runner, archive_env, tmp_path, monkeypatch):
    (archive_env / "readme.txt").write_text("x")
    ex = archive_env / "binanceus"
    sqlite_path = ex / "ETHUSDT.sqlite"
    con = sqlite3.connect(sqlite_path)
    pd.DataFrame({"date": ["2024-01-01"], "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}).to_sql(
        "kline", con, index=False
    )
    con.close()
    assert _invoke(cli_runner, ["migrate_archive"]).exit_code == 0


# --- helper functions ---


def test_load_backtest_run_date_columns(archive_env, backtest_run, sample_ohlcv):
    run_id, run_dir, _ = backtest_run
    df = sample_ohlcv.head(5).reset_index()
    df.to_parquet(run_dir / "dataframe.parquet", index=False)
    trade = pd.DataFrame({"date": df["date"], "close": [1.0] * len(df), "in_trade": [True] * len(df)})
    trade.to_parquet(run_dir / "trade_log.parquet", index=False)

    _, summary, trade_df, df_out = cli_mod._load_backtest_run(str(archive_env / "backtests"), run_id)
    assert summary["return_perc"] == 12.5
    assert trade_df is not None
    assert df_out is not None


def test_load_backtest_summary_yaml_write_failure(archive_env, tmp_path):
    run_dir = archive_env / "backtests" / "json_only"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({"return_perc": 2}))

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", fake_import):
        loaded = cli_mod._load_backtest_summary(str(run_dir))
    assert loaded["return_perc"] == 2


def test_load_latest_ohlcv_date_column(archive_env, sample_ohlcv):
    path = archive_env / "coinbase" / "ETH-USD.parquet"
    df = sample_ohlcv.head(10).reset_index()
    df.to_parquet(path, index=False)
    out = cli_mod._load_latest_ohlcv("coinbase", "ETH-USD", 5)
    assert len(out) == 5


def test_append_klines_and_trades_corrupt_existing(archive_env, monkeypatch, sample_ohlcv):
    rows = [
        (
            datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            {"open": 1, "close": 1, "high": 1, "low": 1, "volume": 1},
        )
    ]
    path = archive_env / "coinbase" / "BTC-USD.parquet"
    sample_ohlcv.head(3).to_parquet(path)
    trade_path = archive_env / "coinbase" / "trades" / "BTC-USD-2024-01-01.parquet"
    trade_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ts": "2024-01-01T00:00:00", "trade_id": "t1", "price": 1, "size": 1}]).to_parquet(
        trade_path, index=False
    )

    with mock.patch("fast_trade.archive.db_helpers._safe_read_parquet", return_value=None):
        cli_mod._append_klines_to_archive("BTC-USD", rows)
        cli_mod._append_trades_parquet(
            "BTC-USD",
            [{"ts": "2024-01-01T00:00:00", "trade_id": "t2", "price": 1, "size": 1}],
        )


def test_save_yaml_or_json_without_yaml(tmp_path, monkeypatch):
    out = tmp_path / "out.yml"
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    cli_mod._save_yaml_or_json(str(out), {"a": 1})
    assert json.loads(out.read_text())["a"] == 1


def test_list_strategy_files_filters(archive_env, tmp_path, monkeypatch):
    strat_dir = archive_env / "strategies"
    (strat_dir / ".hidden.yml").write_text("x: 1\n")
    (strat_dir / "notes.txt").write_text("nope")
    cwd_yml = tmp_path / "local_strat.yml"
    cwd_yml.write_text("name: local\n")
    monkeypatch.chdir(tmp_path)
    files = cli_mod._list_strategy_files()
    assert not any(os.path.basename(f).startswith(".") for f in files)
    assert not any(f.endswith(".txt") for f in files)


def test_edit_dict_unknown_key_declined():
    session = mock.Mock()
    session.prompt.side_effect = ["missing", "S"]
    with mock.patch("fast_trade.cli.PromptSession", return_value=session), mock.patch(
        "fast_trade.cli.Confirm.ask", return_value=False
    ):
        out = cli_mod._edit_dict_interactive("T", {"a": 1})
    assert out == {"a": 1}


# --- terminal early exits ---


def test_terminal_no_backtests_dir(cli_runner, tmp_path, monkeypatch):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path / "empty"))
    assert cli_runner.invoke(app, ["terminal"]).exit_code != 0


def test_terminal_no_runs(cli_runner, archive_env, monkeypatch):
    _mock_tty(monkeypatch)
    for child in (archive_env / "backtests").iterdir():
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
    assert cli_runner.invoke(app, ["terminal"]).exit_code != 0


def test_terminal_index_out_of_range(cli_runner, archive_env, monkeypatch):
    _mock_tty(monkeypatch)
    assert cli_runner.invoke(app, ["terminal", "--index", "99"]).exit_code != 0


def test_terminal_bad_last_strategy_path(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    bad_path_file = archive_env / "last_strategy_path.txt"
    bad_path_file.write_text("/does/not/exist.yml")
    with mock.patch("fast_trade.cli.PromptSession") as ps:
        ps.return_value.prompt.side_effect = ["Q"]
        cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


# --- terminal full loop ---


def _terminal_session(monkeypatch, commands):
    cmd_iter = iter(list(commands) + ["Q"])

    def _next(*args, **kwargs):
        try:
            return next(cmd_iter)
        except StopIteration:
            return "Q"

    session = mock.Mock()
    session.prompt.side_effect = _next
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)
    return session


def test_terminal_pages_and_commands(archive_env, backtest_run, strategy_file, mock_backtest_result, monkeypatch, sample_ohlcv, tmp_path):
    _mock_tty(monkeypatch)
    run_id, run_dir, summary = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))
    override = run_dir / "strategy.override.yml"
    override.write_text(yaml.safe_dump({"symbol": "BTC-USD", "exchange": "coinbase", "freq": "1Min", "datapoints": [{"args": [5]}]}))

    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"live"}\n{"message":"m"}\n')
    stream_log = archive_env / "stream_logs" / f"{run_id}.log"
    stream_log.parent.mkdir(exist_ok=True)
    stream_log.write_text("stream legacy\n")

    commands = [
        "GP",
        "STREAM",
        "LIVE",
        "DB LIVE",
        "DB",
        "LOGS LIVE",
        "LOGS STREAM",
        "SHOW STRAT",
        "EDIT STRAT",
        "EDIT BT",
        "NEW STRAT",
        "OPEN STRAT",
        "OPEN BT",
        "BT MODS freq 1Min",
        "BT SAVE PLOT MODS freq 1Min",
        "SAVE",
        "download BTC binanceus",
        "PORTFOLIO STATUS pf1",
        "PORTFOLIO STOP pf1",
        "PORTFOLIO START",
        "PORTFOLIO BAD",
        "LIVE START",
        "LIVE STOP",
        "STREAM START BTC-USD channels=trades,level2",
        "STREAM STOP",
        "UA",
        "HELP",
    ]
    _terminal_session(monkeypatch, commands)

    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    monkeypatch.setattr(cli_mod, "save", lambda *a, **k: {"path": str(run_dir)})
    monkeypatch.setattr(cli_mod, "create_plot", mock.Mock())
    monkeypatch.setattr(cli_mod, "update_archive", mock.Mock())
    monkeypatch.setattr(cli_mod, "_pick_from_list", mock.Mock(side_effect=[str(strategy_file), run_id]))
    monkeypatch.setattr(cli_mod, "_edit_dict_interactive", lambda *a, **k: {"name": "Edited"})
    monkeypatch.setattr(cli_mod, "_create_strategy_interactive", lambda: str(strategy_file))
    monkeypatch.setattr(
        cli_mod,
        "open_strat_file",
        lambda p: {
            "symbol": "BTC-USD",
            "exchange": "coinbase",
            "freq": "1Min",
            "datapoints": [{"args": [5]}],
            "start": "2024-01-01",
            "stop": "2024-12-31",
        },
    )
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(50))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))
    monkeypatch.setattr(cli_mod.Confirm, "ask", mock.Mock(return_value=False))
    monkeypatch.setattr(cli_mod.threading, "Thread", _RunnableThread)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    orig_load = cli_mod._load_backtest_run

    def _load_override(path, rid):
        rp, sm, tdf, df = orig_load(path, rid)
        sm = dict(sm)
        sm["strategy_override_path"] = str(override)
        return rp, sm, tdf, df

    monkeypatch.setattr(cli_mod, "_load_backtest_run", _load_override)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=2)


def test_terminal_stream_websocket_full(archive_env, backtest_run, monkeypatch, sample_ohlcv):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("FT_TERMINAL_SYNC_STREAM", "1")
    run_id, _, _ = backtest_run

    recv_count = {"n": 0}

    class FakeWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def send(self, msg):
            return None

        async def recv(self):
            recv_count["n"] += 1
            if recv_count["n"] == 1:
                return json.dumps(
                    {
                        "channel": "market_trades",
                        "timestamp": "2024-01-01T00:00:00",
                        "events": [
                            {
                                "product_id": "BTC-USD",
                                "trades": [
                                    {
                                        "trade_id": "t1",
                                        "time": "2024-01-01T00:00:00Z",
                                        "price": "100",
                                        "size": "1",
                                        "side": "buy",
                                    },
                                    {
                                        "trade_id": "t1",
                                        "time": "2024-01-01T00:00:00Z",
                                        "price": "100",
                                        "size": "1",
                                        "side": "buy",
                                    },
                                    {
                                        "trade_id": "t2",
                                        "time": "bad-time",
                                        "price": "100",
                                        "size": "1",
                                        "side": "buy",
                                    },
                                ],
                            }
                        ],
                    }
                )
            if recv_count["n"] == 2:
                return json.dumps(
                    {
                        "channel": "level2",
                        "timestamp": "2024-01-01T00:00:00",
                        "events": [
                            {
                                "product_id": "BTC-USD",
                                "type": "update",
                                "updates": [{"side": "bid", "price_level": "1", "new_quantity": "2"}],
                            }
                        ],
                    }
                )
            if recv_count["n"] == 3:
                return "not-json{{{"
            await asyncio.sleep(0.01)
            raise asyncio.TimeoutError()

    class FailConnect:
        calls = 0

        def __call__(self, *args, **kwargs):
            FailConnect.calls += 1
            if FailConnect.calls == 1:
                raise RuntimeError("connect fail")
            return FakeWS()

    clock = {"t": 1000.0}

    def fake_time():
        clock["t"] += 65.0
        return clock["t"]

    stop_checks = {"n": 0}
    orig_is_set = threading.Event.is_set

    def stop_after(self):
        stop_checks["n"] += 1
        if stop_checks["n"] > 8:
            return True
        return orig_is_set(self)

    monkeypatch.setattr("websockets.connect", FailConnect())
    monkeypatch.setattr(cli_mod, "_append_klines_to_archive", mock.Mock())
    monkeypatch.setattr(cli_mod, "_append_trades_parquet", mock.Mock())
    monkeypatch.setattr(cli_mod.time, "time", fake_time)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(threading.Event, "is_set", stop_after)

    prompts = iter(["STREAM START BTC-USD channels=trades,level2", "Q"])
    session = mock.Mock()
    session.prompt.side_effect = lambda *a, **k: next(prompts)
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)

    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_stream_import_error(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("FT_TERMINAL_SYNC_STREAM", "1")
    run_id, _, _ = backtest_run
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "websockets":
            raise ImportError("no websockets")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    _terminal_session(monkeypatch, ["STREAM START BTC-USD", "Q"])
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_live_runner_paths(archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    class AliveStreamThread:
        def __init__(self, target=None, daemon=None):
            self._alive = True

        def start(self):
            return None

        def is_alive(self):
            return True

        def join(self, timeout=None):
            return None

    calls = {"n": 0}

    def load_ohlcv(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return sample_ohlcv.head(50)
        if calls["n"] == 2:
            return pd.DataFrame()
        raise RuntimeError("Parquet magic bytes not found in footer")

    _terminal_session(monkeypatch, ["LIVE START ETH-USD", "LIVE STOP", "LIVE START", "LIVE STOP"])
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "exchange": "coinbase", "freq": "1Min", "datapoints": [{"args": [5]}]})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", load_ohlcv)
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "x")
    monkeypatch.setattr(cli_mod.threading, "Thread", _RunnableThread)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    orig_thread = cli_mod.threading.Thread

    def thread_factory(*args, **kwargs):
        target = kwargs.get("target") or (args[0] if args else None)
        if target and getattr(target, "__name__", "") == "_run_stream":
            return AliveStreamThread()
        return _RunnableThread(target=target, daemon=kwargs.get("daemon"))

    monkeypatch.setattr(cli_mod.threading, "Thread", thread_factory)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_live_no_strategy(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, run_dir, summary = backtest_run
    summary_no_strat = dict(summary)
    summary_no_strat.pop("strategy", None)
    with open(run_dir / "summary.yml", "w") as fh:
        yaml.safe_dump(summary_no_strat, fh)
    _terminal_session(monkeypatch, ["LIVE START", "LIVE STOP"])
    monkeypatch.setattr(cli_mod.threading, "Thread", _RunnableThread)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_bt_and_save_errors(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    _terminal_session(monkeypatch, ["BT MODS bad", "SAVE", "SHOW STRAT"])
    monkeypatch.setattr(cli_mod, "open_strat_file", mock.Mock(side_effect=RuntimeError("bad strat")))
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_open_bt_failure(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    _terminal_session(monkeypatch, ["OPEN BT"])
    monkeypatch.setattr(cli_mod, "_pick_from_list", mock.Mock(return_value="missing_run"))
    orig = cli_mod._load_backtest_run

    def load_maybe_fail(path, rid):
        if rid == "missing_run":
            raise FileNotFoundError("nope")
        return orig(path, rid)

    monkeypatch.setattr(cli_mod, "_load_backtest_run", load_maybe_fail)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_portfolio_no_strategy(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    _terminal_session(monkeypatch, ["PORTFOLIO START"])
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_passthrough_subprocess_error(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    _terminal_session(monkeypatch, ["noterm cmd"])
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock(side_effect=OSError("fail"))))
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_logs_read_errors(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"x"}\n')

    _terminal_session(monkeypatch, ["LOGS ALL"])

    real_open = open

    def selective_open(path, *args, **kwargs):
        text = str(path)
        if text.endswith(".jsonl") or text.endswith(".log"):
            if "live_logs" in text or "stream_logs" in text:
                raise OSError("read fail")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", selective_open)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_show_strat_empty_keys(archive_env, backtest_run, strategy_file, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))
    _terminal_session(monkeypatch, ["OPEN STRAT", "SHOW STRAT"])
    monkeypatch.setattr(cli_mod, "_pick_from_list", mock.Mock(return_value=str(strategy_file)))
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"custom": 1})
    monkeypatch.setattr(cli_mod.Confirm, "ask", mock.Mock(return_value=True))
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


# --- logs command ---


def test_logs_empty_runs(cli_runner, archive_env, monkeypatch):
    for child in (archive_env / "backtests").iterdir():
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
    assert _invoke(cli_runner, ["logs"]).exit_code != 0


def test_logs_tail_zero_and_missing_and_follow(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    assert _invoke(cli_runner, ["logs", "--run-id", run_id, "--tail", "0"]).exit_code == 0

    missing = _invoke(cli_runner, ["logs", "--run-id", "no_such_run_xyz", "--kind", "stream"])
    assert missing.exit_code == 0

    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"tail"}\n')

    iterations = {"n": 0}

    def fake_sleep(_):
        iterations["n"] += 1
        if iterations["n"] >= 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(run_id=run_id, index=None, kind="live", follow=True, tail=1)


# --- portfolio ---


def test_portfolio_default_name_and_once_daemon(cli_runner, strategy_file, archive_env, monkeypatch):
    proc = mock.Mock(pid=999)
    popen = mock.Mock(return_value=proc)
    monkeypatch.setattr(cli_mod.subprocess, "Popen", popen)
    r = _invoke(
        cli_runner,
        ["portfolio", "start", str(strategy_file), "--once"],
    )
    assert r.exit_code == 0
    cmd = popen.call_args[0][0]
    assert "--once" in cmd

    with mock.patch("builtins.open", mock.mock_open()) as mopen:
        mopen.side_effect = [mock.mock_open().return_value, OSError("pid fail")]
        monkeypatch.setattr(cli_mod.subprocess, "Popen", mock.Mock(return_value=proc))
        _invoke(cli_runner, ["portfolio", "start", str(strategy_file)])


def test_portfolio_no_frames_path(cli_runner, strategy_file, archive_env, monkeypatch):
    df = pd.DataFrame({"close": [1.0]}, index=pd.date_range("2024-01-01", periods=1, freq="min"))

    class EmptyTail:
        def tail(self, n):
            return pd.DataFrame()

    df_mock = mock.Mock()
    df_mock.empty = False
    df_mock.tail = EmptyTail().tail
    df_mock.index = df.index

    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: df)
    monkeypatch.setattr(cli_mod, "prepare_df", lambda d, s: df_mock)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "_append_portfolio_log", mock.Mock())
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)
    _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--once", "--name", "noframes"])


def test_portfolio_pid_remove_error(cli_runner, strategy_file, monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", mock.Mock(side_effect=KeyboardInterrupt()))
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)
    monkeypatch.setattr(cli_mod, "_portfolio_paths", lambda name: {"state": "/tmp/s", "log": "/tmp/l", "trades": "/tmp/t", "pid": "/tmp/p.pid"})
    with mock.patch("os.path.exists", return_value=True), mock.patch("os.remove", side_effect=OSError("rm fail")):
        _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--name", "rmfail"])


def test_portfolio_stop_pid_remove_error(cli_runner, tmp_path, monkeypatch):
    pid_file = tmp_path / "runner.pid"
    pid_file.write_text("4242")
    with mock.patch("fast_trade.cli._portfolio_paths", return_value={"pid": str(pid_file)}), mock.patch(
        "os.kill"
    ), mock.patch("os.remove", side_effect=OSError("rm fail")):
        assert _invoke(cli_runner, ["portfolio", "stop", "mypf"]).exit_code == 0


# --- final coverage gaps ---


def test_append_log_line_types(tmp_path):
    log_path = str(tmp_path / "logs" / "run.jsonl")
    cli_mod._append_log_line(log_path, "plain message", kind="live")
    cli_mod._append_log_line(log_path, {"line": "dict"}, kind="stream")
    cli_mod._append_log_line(log_path, 123, kind="live")
    assert os.path.exists(log_path)

    with mock.patch("builtins.open", side_effect=OSError("fail")):
        cli_mod._append_log_line(log_path, "x")


def test_append_klines_new_file_only(archive_env):
    rows = [
        (
            datetime.datetime(2025, 6, 1),
            {"open": 1, "close": 1, "high": 1, "low": 1, "volume": 1},
        )
    ]
    path = archive_env / "coinbase" / "NEW-USD.parquet"
    if path.exists():
        os.remove(path)
    cli_mod._append_klines_to_archive("NEW-USD", rows)
    assert path.exists()


def test_migrate_backtests_trade_with_date(cli_runner, archive_env):
    run_dir = archive_env / "backtests" / "trade_date"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.yml").write_text("return_perc: 1\n")
    trade_db = run_dir / "trade_log.db"
    con = sqlite3.connect(trade_db)
    pd.DataFrame(
        {"date": ["2024-01-01"], "close": [1.0], "in_trade": [True]}
    ).to_sql("trade_log", con, index=False)
    con.close()
    assert _invoke(cli_runner, ["migrate_backtests"]).exit_code == 0


def test_migrate_backtests_outer_exception(cli_runner, archive_env, monkeypatch):
    run_dir = archive_env / "backtests" / "fail_run"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.yml").write_text("x: 1\n")
    (run_dir / "dataframe.db").write_text("not a db")
    with mock.patch("fast_trade.cli.connect_to_db", side_effect=RuntimeError("boom")):
        assert _invoke(cli_runner, ["migrate_backtests"]).exit_code == 0


def test_list_strategy_files_missing_dir(archive_env, tmp_path, monkeypatch):
    import shutil

    strat_dir = archive_env / "strategies"
    if strat_dir.exists():
        shutil.rmtree(strat_dir)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARCHIVE_PATH", str(archive_env))
    assert cli_mod._list_strategy_files() == []


def test_cli_and_ftv_main_lines():
    root = os.path.dirname(os.path.dirname(__file__))
    cli_path = os.path.join(root, "fast_trade", "cli.py")
    ftv_path = os.path.join(root, "fast_trade", "ftv.py")
    cli_src = open(cli_path).read().splitlines()
    ftv_src = open(ftv_path).read().splitlines()

    with mock.patch.object(cli_mod, "main") as cli_main:
        exec("\n".join(cli_src[-2:]), {"__name__": "__main__", "main": cli_main}, {})
        cli_main.assert_called_once()

    with mock.patch.object(ftv, "main") as ftv_main:
        exec("\n".join(ftv_src[-2:]), {"__name__": "__main__", "main": ftv_main}, {})
        ftv_main.assert_called_once()


def test_render_plot_preview_from_data_x_oob(capsys, sample_ohlcv):
    df = sample_ohlcv.head(9).reset_index(drop=True)
    df.index = pd.date_range("2020-01-01", periods=len(df), freq="h")
    idx = df.index[-1]
    trade_df = pd.DataFrame({"close": [df.loc[idx, "close"]], "in_trade": [True]}, index=[idx])
    render_plot_preview_from_data(df, trade_df, width=2, height=4)
    assert capsys.readouterr().out


def test_render_plot_preview_print_exception(tmp_path):
    img = mock.Mock()
    img.width = 4
    img.height = 4
    img.convert.return_value = img
    img.resize.return_value = img
    img.getdata.return_value = [128] * 16
    with mock.patch("PIL.Image.open", return_value=img), mock.patch(
        "builtins.print", side_effect=OSError("print fail")
    ):
        render_plot_preview(str(tmp_path / "x.png"), width=4)


def test_terminal_live_page_with_history(archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("FT_TERMINAL_SYNC_LIVE", "1")
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    stop_checks = {"n": 0}
    orig_is_set = threading.Event.is_set

    def stop_after(self):
        stop_checks["n"] += 1
        return stop_checks["n"] > 2 or orig_is_set(self)

    prompts = iter(["LIVE START", "LIVE", "Q"])
    session = mock.Mock()
    session.prompt.side_effect = lambda *a, **k: next(prompts)
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(10))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "h")
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(threading.Event, "is_set", stop_after)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_logs_tail_empty_path(cli_runner, archive_env, backtest_run):
    run_id, _, _ = backtest_run
    assert _invoke(cli_runner, ["logs", "--run-id", run_id, "--kind", "live", "--tail", "0"]).exit_code == 0


def test_logs_follow_no_files(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    calls = {"n": 0}

    def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(run_id=run_id, index=None, kind="all", follow=True, tail=0)


def test_terminal_early_exits(tmp_path, archive_env, monkeypatch):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path / "no_archive"))
    with pytest.raises(typer.Exit):
        cli_mod.terminal_cmd(run_id=None, index=None, page_size=5)

    empty = tmp_path / "empty_archive"
    (empty / "backtests").mkdir(parents=True)
    monkeypatch.setenv("ARCHIVE_PATH", str(empty))
    with pytest.raises(typer.Exit):
        cli_mod.terminal_cmd(run_id=None, index=None, page_size=5)

    monkeypatch.setenv("ARCHIVE_PATH", str(archive_env))
    with pytest.raises(typer.Exit):
        cli_mod.terminal_cmd(run_id=None, index=99, page_size=5)

    with pytest.raises(typer.Exit):
        cli_mod.terminal_cmd(run_id="missing_run_xyz", index=None, page_size=5)


def test_cli_main_block_runs():
    root = os.path.dirname(os.path.dirname(__file__))
    cli_path = os.path.join(root, "fast_trade", "cli.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        cli_path,
        "exec",
    )
    with mock.patch.object(cli_mod, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()


def test_ftv_main_block_runs():
    root = os.path.dirname(os.path.dirname(__file__))
    ftv_path = os.path.join(root, "fast_trade", "ftv.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        ftv_path,
        "exec",
    )
    with mock.patch.object(ftv, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()



# --- evolve genes validation ---


def test_evolve_gene_validation_branches(cli_runner, tmp_path, monkeypatch):
    base = {"strategy": {"symbol": "BTC"}, "settings": {"num_generations": 1, "threads": 1}}

    p1 = tmp_path / "no_genes.json"
    p1.write_text(json.dumps({**base, "genes": []}))
    assert _invoke(cli_runner, ["evolve", str(p1)]).exit_code != 0

    p2 = tmp_path / "bad_gene.json"
    p2.write_text(json.dumps({**base, "genes": [{"name": "x"}]}))
    assert _invoke(cli_runner, ["evolve", str(p2)]).exit_code != 0

    p3 = tmp_path / "bad_type.json"
    p3.write_text(json.dumps({**base, "genes": [123]}))
    assert _invoke(cli_runner, ["evolve", str(p3)]).exit_code != 0

    p4 = tmp_path / "list_gene.json"
    p4.write_text(json.dumps({**base, "genes": [["freq", ["1H", "4H"]]]}))
    monkeypatch.setattr(cli_mod, "optimize_strategy", lambda **k: ([("freq", "1H")], 1.0))
    assert _invoke(cli_runner, ["evolve", str(p4)]).exit_code == 0

    p5 = tmp_path / "bad_genes_type.json"
    p5.write_text(json.dumps({**base, "genes": "bad"}))
    assert _invoke(cli_runner, ["evolve", str(p5)]).exit_code != 0


# --- __main__ ---


def test_cli_script_main():
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "fast_trade.cli", "--help"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_cli_main_error_path():
    with mock.patch.object(cli_mod, "app", side_effect=RuntimeError("err")), mock.patch.object(
        cli_mod.sys, "exit"
    ) as ex:
        cli_mod.main()
        ex.assert_called_with(1)


# --- cli_helpers remainders ---


def test_migrate_backtests_sqlite_without_parquet(cli_runner, archive_env, sample_ohlcv):
    run_dir = archive_env / "backtests" / "migrate_only"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.yml").write_text("return_perc: 1\n")

    df_db = run_dir / "dataframe.db"
    con = sqlite3.connect(df_db)
    pd.DataFrame(
        {"date": ["2024-01-01"], "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}
    ).to_sql("dataframe", con, index=False)
    con.close()

    trade_db = run_dir / "trade_log.db"
    con2 = sqlite3.connect(trade_db)
    pd.DataFrame({"close": [1.0], "in_trade": [True]}).to_sql("trade_log", con2, index=False)
    con2.close()

    assert _invoke(cli_runner, ["migrate_backtests", "--limit", "5"]).exit_code == 0
    assert (run_dir / "dataframe.parquet").exists()
    assert (run_dir / "trade_log.parquet").exists()


def test_append_klines_merge_existing(archive_env, sample_ohlcv):
    path = archive_env / "coinbase" / "ETH-USD.parquet"
    sample_ohlcv.head(5).to_parquet(path)
    rows = [
        (
            datetime.datetime(2025, 1, 1),
            {"open": 2, "close": 2, "high": 2, "low": 2, "volume": 2},
        )
    ]
    cli_mod._append_klines_to_archive("ETH-USD", rows)


def test_terminal_live_sync(archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("FT_TERMINAL_SYNC_LIVE", "1")
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    calls = {"n": 0}

    def load_ohlcv(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return sample_ohlcv.head(50)
        if calls["n"] == 2:
            return pd.DataFrame()
        raise RuntimeError("Parquet magic bytes not found in footer")

    stop_checks = {"n": 0}
    orig_is_set = threading.Event.is_set

    def stop_after(self):
        stop_checks["n"] += 1
        if stop_checks["n"] > 3:
            return True
        return orig_is_set(self)

    _terminal_session(monkeypatch, ["LIVE START ETH-USD", "Q"])
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "exchange": "coinbase", "freq": "1Min", "datapoints": [{"args": [5]}]})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", load_ohlcv)
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "tsl")
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(threading.Event, "is_set", stop_after)
    monkeypatch.setattr(cli_mod.time, "time", lambda: 1000.0)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_parse_simple_yaml_empty_dash_item():
    parsed = _parse_simple_yaml("items:\n  - \n")
    assert parsed == {"items": [{}]}
    parsed2 = _parse_simple_yaml("items:\n  - \n  - key: 1\n")
    assert isinstance(parsed2["items"], list)


def test_render_plot_preview_from_data_edge_cases(capsys, sample_ohlcv):
    df = sample_ohlcv.head(100)
    trade_idx = df.index[-1]
    trade_df = pd.DataFrame({"close": [df.loc[trade_idx, "close"]], "in_trade": [True]}, index=[trade_idx])
    render_plot_preview_from_data(df, trade_df, width=3, height=4)
    assert capsys.readouterr().out

    class _CloseSeries:
        @property
        def values(self):
            return []

    class _FakeDF:
        empty = False
        columns = ["close"]

        def __getitem__(self, key):
            return _CloseSeries()

    render_plot_preview_from_data(_FakeDF(), None)


def test_render_plot_preview_inner_exception(tmp_path, capsys):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not installed")
    img_path = tmp_path / "plot.png"
    Image.new("L", (4, 4), color=128).save(img_path)

    class BadImage:
        width = 4
        height = 4

        def convert(self, mode):
            return self

        def resize(self, size):
            return self

        def getdata(self):
            raise RuntimeError("pixels fail")

    with mock.patch("PIL.Image.open", return_value=BadImage()):
        render_plot_preview(str(img_path))


# --- ftv remainders ---


def test_ftv_json_to_json(cli_runner, tmp_path):
    src = tmp_path / "in.json"
    dest = tmp_path / "out.json"
    src.write_text(json.dumps({"plain": "hello"}))
    assert cli_runner.invoke(ftv.app, ["convert", str(src), str(dest)]).exit_code == 0


def test_ftv_script_main_entry():
    import subprocess

    result = subprocess.run(
        [sys.executable, "fast_trade/ftv.py", "--help"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


# --- terminal_ui remainder ---


@pytest.fixture
def console():
    return Console(file=StringIO(), width=120, force_terminal=True, legacy_windows=False)


def test_render_trades_table_action_reorder(console):
    trade_df = pd.DataFrame(
        {"close": [1.0, 2.0], "volume": [3.0, 4.0], "action": ["e", "x"]},
        index=pd.date_range("2024-01-01", periods=2, freq="h"),
    )
    view = trade_df[["close", "volume"]].iloc[0:2]

    class FakeTradeDF:
        empty = False
        columns = trade_df.columns

        @property
        def iloc(self):
            return mock.Mock(__getitem__=mock.Mock(return_value=view))

    tui.render_trades_table(console, FakeTradeDF(), 0, 5)


# --- additional terminal / cli gaps ---


def test_terminal_follow_views_and_branches(archive_env, backtest_run, strategy_file, mock_backtest_result, monkeypatch, sample_ohlcv):
    _mock_tty(monkeypatch)
    run_id, run_dir, summary = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))
    stream_log = archive_env / "stream_logs" / f"{run_id}.jsonl"
    stream_log.parent.mkdir(exist_ok=True)
    stream_log.write_text('{"line":"s"}\n')

    prompt_values = [
        "GP",
        "STREAM",
        "LIVE",
        "LOGS BADKIND",
        "EDIT STRAT",
        "EDIT",
        "SHOW STRAT",
        "OPEN STRAT",
        "BT",
        "BACKTEST SAVE",
        "SAVE",
        "STREAM STOP",
        "LIVE STOP",
        "PORTFOLIO STATUS x",
        "PORTFOLIO STOP x",
        "noterm x",
        "Q",
    ]
    prompt_iter = iter(prompt_values)
    session = mock.Mock()
    session.prompt.side_effect = lambda *a, **k: next(prompt_iter, "Q")
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    monkeypatch.setattr(cli_mod, "save", lambda *a, **k: {"path": str(run_dir)})
    monkeypatch.setattr(cli_mod, "create_plot", mock.Mock())
    monkeypatch.setattr(cli_mod, "_pick_from_list", mock.Mock(return_value=str(strategy_file)))
    monkeypatch.setattr(cli_mod, "_edit_dict_interactive", lambda *a, **k: {"name": "X"})
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "exchange": "coinbase", "freq": "1Min"})
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))
    monkeypatch.setattr(cli_mod.Confirm, "ask", mock.Mock(return_value=True))
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(cli_mod.threading, "Thread", _RunnableThread)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=2)


def test_terminal_live_already_running(archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    class AlwaysAlive:
        def __init__(self, target=None, daemon=None):
            pass

        def start(self):
            return None

        def is_alive(self):
            return True

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(cli_mod.threading, "Thread", AlwaysAlive)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)
    _terminal_session(monkeypatch, ["LIVE START", "STREAM START BTC-USD", "Q"])
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "freq": "1Min"})
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_load_run_failure_direct(archive_env, monkeypatch):
    _mock_tty(monkeypatch)
    monkeypatch.setattr(cli_mod, "_load_backtest_run", mock.Mock(side_effect=RuntimeError("load fail")))
    with pytest.raises(typer.Exit):
        cli_mod.terminal_cmd(run_id="any", index=None, page_size=5)


def test_terminal_last_strategy_read_error(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    bad = archive_env / "last_strategy_path.txt"
    bad.write_text("/tmp/x.yml")
    real_open = open

    def selective_open(path, *args, **kwargs):
        text = str(path)
        mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
        if text.endswith("last_strategy_path.txt") and "r" in mode:
            raise OSError("read fail")
        return real_open(path, *args, **kwargs)

    _terminal_session(monkeypatch, ["Q"])
    monkeypatch.setattr("builtins.open", selective_open)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_stream_log_write_failure(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    real_open = open
    writes = {"n": 0}

    def flaky_open(path, *args, **kwargs):
        text = str(path)
        if "stream_logs" in text and "a" in args:
            writes["n"] += 1
            if writes["n"] > 0:
                raise OSError("log fail")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", flaky_open)
    monkeypatch.setattr(cli_mod.threading, "Thread", _RunnableThread)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "websockets":
            raise ImportError("no websockets")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    _terminal_session(monkeypatch, ["STREAM START BTC-USD", "Q"])
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_cli_name_main_guard():
    cli_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fast_trade", "cli.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        cli_path,
        "exec",
    )
    with mock.patch.object(cli_mod, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()


def test_render_plot_preview_from_data_trade_oob(capsys, sample_ohlcv):
    df = sample_ohlcv.head(200)
    early_idx = df.index[5]
    trade_df = pd.DataFrame({"close": [df.loc[early_idx, "close"]], "in_trade": [True]}, index=[early_idx])
    render_plot_preview_from_data(df, trade_df, width=2, height=4)
    assert capsys.readouterr().out


def test_render_plot_preview_line_loop_exception(tmp_path):
    img_path = tmp_path / "plot.png"
    img_path.write_bytes(b"\x00" * 16)

    img = mock.Mock()
    img.width = 4
    img.height = 4
    img.convert.return_value = img
    img.resize.return_value = img
    img.getdata.side_effect = OSError("pixels fail")

    with mock.patch("PIL.Image.open", return_value=img):
        render_plot_preview(str(img_path), width=4)


def test_ftv_dump_yaml_plain_string(tmp_path, monkeypatch):
    src = tmp_path / "in.json"
    dest = tmp_path / "out.yml"
    src.write_text(json.dumps({"msg": "hello"}))
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert CliRunner().invoke(ftv.app, ["convert", str(src), str(dest)]).exit_code == 0
    assert "hello" in dest.read_text()


def test_ftv_name_main_guard():
    ftv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fast_trade", "ftv.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        ftv_path,
        "exec",
    )
    with mock.patch.object(ftv, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()


def test_list_strategy_files_dot_and_txt(archive_env, tmp_path, monkeypatch):
    strat_dir = archive_env / "strategies"
    (strat_dir / ".secret.yml").write_text("x: 1\n")
    (strat_dir / "readme.txt").write_text("nope")
    monkeypatch.chdir(tmp_path)
    files = cli_mod._list_strategy_files()
    assert all(not os.path.basename(f).startswith(".") for f in files)
    assert all(f.endswith((".yml", ".yaml")) for f in files)


def test_logs_follow_stream_path(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    stream_log = archive_env / "stream_logs" / f"{run_id}.jsonl"
    stream_log.parent.mkdir(exist_ok=True)
    stream_log.write_text('{"line":"stream"}\n')

    calls = {"n": 0}

    def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(run_id=run_id, index=None, kind="stream", follow=True, tail=1)


def test_portfolio_pid_write_failure(cli_runner, strategy_file, monkeypatch):
    proc = mock.Mock(pid=123)
    monkeypatch.setattr(cli_mod.subprocess, "Popen", mock.Mock(return_value=proc))
    real_open = open

    def open_side(path, *args, **kwargs):
        if str(path).endswith("runner.pid"):
            raise OSError("pid write fail")
        return real_open(path, *args, **kwargs)

    with mock.patch("builtins.open", side_effect=open_side):
        assert _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--name", "pidfail"]).exit_code == 0

