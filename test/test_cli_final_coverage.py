"""Cover remaining CLI helpers without hanging interactive loops."""

import asyncio
import datetime
import json
import threading
import time as time_mod
from unittest import mock

import pandas as pd
import pytest

import fast_trade.cli as cli_mod
from fast_trade.cli import (
    _flush_stream_timeout,
    _live_signal_from_df,
)
from fast_trade.cli_helpers import _parse_simple_yaml
from fast_trade.run_backtest import compile_action_logic


def test_parse_simple_yaml_empty_list_item():
    text = "items:\n  - \n  - name: a\n"
    parsed = _parse_simple_yaml(text)
    assert "items" in parsed
    assert isinstance(parsed["items"], list)


def test_flush_stream_timeout_klines_and_trades(tmp_path, monkeypatch):
    symbol = "BTC-USD"
    log_path = str(tmp_path / "stream.jsonl")
    now = 1_700_000_000.0
    cutoff = datetime.datetime.utcfromtimestamp(now).replace(second=0, microsecond=0)
    older = cutoff - datetime.timedelta(minutes=2)
    candles = {
        older: {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
        cutoff: {"open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 5.0},
    }
    trade_buffer = [
        {
            "trade_id": "1",
            "price": 1.0,
            "size": 1.0,
            "side": "buy",
            "time": older.isoformat(),
        }
    ]
    seen = {"old": now - 7200, "new": now}

    monkeypatch.setattr(cli_mod, "_append_klines_to_archive", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "_append_trades_parquet", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "minute_floor", lambda dt: cutoff)

    trade_buffer2, seen2, lk, lt = _flush_stream_timeout(
        symbol,
        candles,
        trade_buffer,
        seen,
        log_path,
        last_kline_flush=now - 61,
        last_trade_flush=now - 61,
        now=now,
    )
    assert older not in candles
    assert trade_buffer2 == []
    assert "old" not in seen2
    assert "new" in seen2
    assert lk == now and lt == now


def test_flush_stream_timeout_force_klines(tmp_path, monkeypatch):
    log_path = str(tmp_path / "s.jsonl")
    now = 2000.0
    cutoff = datetime.datetime.utcfromtimestamp(now).replace(second=0, microsecond=0)
    older = cutoff - datetime.timedelta(minutes=1)
    candles = {
        older: {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
        cutoff: {"open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0, "volume": 1.0},
    }
    monkeypatch.setattr(cli_mod, "_append_klines_to_archive", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "minute_floor", lambda dt: cutoff)
    _flush_stream_timeout(
        "BTC-USD",
        candles,
        [],
        {},
        log_path,
        last_kline_flush=now,
        last_trade_flush=now,
        now=now,
        force_klines=True,
    )
    assert older not in candles


def test_flush_stream_timeout_no_op_when_fresh():
    time_now = 1000.0
    tb, st, lk, lt = _flush_stream_timeout(
        "BTC-USD",
        {},
        [],
        {},
        "/tmp/nope.jsonl",
        last_kline_flush=time_now,
        last_trade_flush=time_now,
        now=time_now + 10,
    )
    assert tb == []
    assert lk == time_now


def test_live_signal_from_df_empty_and_actions():
    compiled = compile_action_logic(
        {
            "enter": [["close", ">", 0]],
            "exit": [["close", "<", 0]],
            "any_enter": [],
            "any_exit": [],
            "trailing_stop_loss": 0,
        }
    )
    label, price, indicators, parts = _live_signal_from_df(pd.DataFrame(), compiled)
    assert label == "HOLD"
    assert parts == []

    idx = pd.date_range("2024-01-01", periods=5, freq="min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5],
            "high": [1, 2, 3, 4, 5],
            "low": [1, 2, 3, 4, 5],
            "close": [1.0, 2.0, 3.0, 4.0, 5.0],
            "volume": [10] * 5,
            "rsi": [10, 20, 30, 40, 50],
        },
        index=idx,
    )
    label, price, indicators, parts = _live_signal_from_df(df, compiled)
    assert label in {"ENTER", "HOLD", "EXIT"}
    assert price == pytest.approx(5.0)
    assert "rsi" in indicators
    assert parts


def test_terminal_index_out_of_range_and_load_error(archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)

    with pytest.raises(cli_mod.typer.Exit):
        cli_mod.terminal_cmd(run_id=None, index=99, page_size=5)

    with pytest.raises(cli_mod.typer.Exit):
        with mock.patch.object(
            cli_mod, "_load_backtest_run", side_effect=RuntimeError("boom")
        ):
            cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_default_latest_run(archive_env, backtest_run, monkeypatch):
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    prompts = iter(["q"])

    class Sess:
        def prompt(self, *a, **k):
            return next(prompts)

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=None, index=None, page_size=5)


def test_terminal_bt_progress_and_no_strategy(
    archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv
):
    run_id, _, _ = backtest_run
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)

    strat = {
        "symbol": "BTC-USD",
        "freq": "1Min",
        "start": "",
        "datapoints": [],
        "enter": [["close", ">", 0]],
        "exit": [["close", "<", 0]],
        "any_enter": [],
        "any_exit": [],
        "trailing_stop_loss": 0,
        "base_balance": 1000,
        "comission": 0,
        "lot_size_perc": 1,
        "exit_on_end": True,
    }

    def fake_run(strategy, progress_callback=None, **kw):
        if progress_callback:
            progress_callback({"phase": "data", "percent": 50})
            progress_callback({"phase": "actions", "percent": 50})
            progress_callback({"phase": "simulation", "percent": 50})
        return {
            "summary": {"return_perc": 1.0, "strategy": strategy},
            "df": sample_ohlcv.copy(),
            "trade_df": pd.DataFrame(),
        }

    monkeypatch.setattr(cli_mod, "run_backtest", fake_run)
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: strat)
    monkeypatch.setattr(cli_mod, "save", lambda *a, **k: {"path": "/tmp/x"})
    monkeypatch.setattr(cli_mod, "create_plot", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "_load_json_or_yaml", lambda p: strat)
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))
    override = archive_env / "backtests" / run_id / "strategy.override.yml"
    override.write_text("symbol: BTC-USD\n")

    cmds = iter(["BT", "BT PLOT SAVE", "SAVE", "q"])

    class Sess:
        def prompt(self, *a, **k):
            try:
                return next(cmds)
            except StopIteration:
                return "q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=run_id, index=1, page_size=5)


def test_terminal_show_edit_strat_branches(
    archive_env, backtest_run, strategy_file, monkeypatch
):
    run_id, _, _ = backtest_run
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod, "_edit_backtest_interactive", lambda *a, **k: {"x": 1})
    monkeypatch.setattr(cli_mod, "_edit_strategy_interactive", lambda *a, **k: strategy_file)
    monkeypatch.setattr(cli_mod, "_create_strategy_interactive", lambda: None)
    monkeypatch.setattr(
        cli_mod,
        "open_strat_file",
        lambda p: {"name": "n", "symbol": "BTC-USD"},
    )
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    cmds = iter(
        [
            "SHOW STRAT",
            "EDIT BT",
            "EDIT STRAT",
            "NEW STRAT",
            "q",
        ]
    )

    class Sess:
        def prompt(self, *a, **k):
            try:
                return next(cmds)
            except StopIteration:
                return "q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_show_strat_load_error(archive_env, backtest_run, strategy_file, monkeypatch):
    run_id, _, _ = backtest_run
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    def boom(p):
        raise RuntimeError("bad strat")

    monkeypatch.setattr(cli_mod, "open_strat_file", boom)
    cmds = iter(["SHOW STRAT", "EDIT STRAT", "q"])

    class Sess:
        def prompt(self, *a, **k):
            try:
                return next(cmds)
            except StopIteration:
                return "q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_live_sync_and_parquet_error(
    archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv
):
    run_id, _, _ = backtest_run
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    # Sync live only — stream runs in thread so START returns
    monkeypatch.setenv("FT_TERMINAL_SYNC_LIVE", "1")
    monkeypatch.delenv("FT_TERMINAL_SYNC_STREAM", raising=False)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(
        cli_mod.threading.Event,
        "wait",
        lambda self, timeout=None: True,
    )

    strat = {
        "symbol": "BTC-USD",
        "freq": "1Min",
        "start": "",
        "datapoints": [],
        "enter": [["close", ">", 0]],
        "exit": [["close", "<", 0]],
        "any_enter": [],
        "any_exit": [],
        "trailing_stop_loss": 0,
        "base_balance": 1000,
        "comission": 0,
        "lot_size_perc": 1,
        "exit_on_end": True,
    }
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: strat)
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.copy())

    import types
    import sys
    import asyncio

    class FakeWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def send(self, msg):
            return None

        async def recv(self):
            await asyncio.sleep(0.05)
            raise asyncio.TimeoutError()

    mod = types.ModuleType("websockets")
    mod.connect = lambda *a, **k: FakeWS()
    monkeypatch.setitem(sys.modules, "websockets", mod)
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))
    monkeypatch.setattr(cli_mod, "_append_klines_to_archive", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "_append_trades_parquet", lambda *a, **k: None)

    cmds = iter(
        [
            "LIVE START BTC-USD",
            "LIVE STOP",
            "q",
        ]
    )

    class Sess:
        def prompt(self, *a, **k):
            try:
                return next(cmds)
            except StopIteration:
                return "q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)

    monkeypatch.setattr(
        cli_mod,
        "_load_latest_ohlcv",
        mock.Mock(side_effect=RuntimeError("Parquet magic bytes not found")),
    )
    cmds2 = iter(["LIVE START", "q"])

    class Sess2:
        def prompt(self, *a, **k):
            try:
                return next(cmds2)
            except StopIteration:
                return "q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess2())
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_bt_no_strategy(archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    # clear last strategy
    last = archive_env / "last_strategy_path.txt"
    if last.exists():
        last.unlink()
    cmds = iter(["BT", "SAVE", "q"])

    class Sess:
        def prompt(self, *a, **k):
            try:
                return next(cmds)
            except StopIteration:
                return "q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_live_bad_strategy_path(archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    (archive_env / "last_strategy_path.txt").write_text("/no/such/strategy.yml")
    monkeypatch.setattr(
        cli_mod, "open_strat_file", mock.Mock(side_effect=RuntimeError("nope"))
    )
    cmds = iter(["LIVE START", "q"])

    class Sess:
        def prompt(self, *a, **k):
            try:
                return next(cmds)
            except StopIteration:
                return "q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_logs_follow_exception_path(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    log_dir = archive_env / "live_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{run_id}.jsonl"
    path.write_text('{"a":1}\n')

    calls = {"n": 0}

    def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)

    class BadFile:
        closed = False

        def readline(self):
            raise OSError("read fail")

        def seek(self, *a):
            return None

        def close(self):
            self.closed = True

    real_open = open

    def open_side_effect(p, *a, **k):
        if str(p).endswith(".jsonl"):
            return BadFile()
        return real_open(p, *a, **k)

    monkeypatch.setattr("builtins.open", open_side_effect)
    try:
        cli_runner.invoke(
            cli_mod.app,
            ["logs", run_id, "--kind", "live", "--tail", "0", "--follow"],
        )
    except KeyboardInterrupt:
        pass


class _SyncFollowThread:
    """Run follow-view wait targets synchronously so stop_follow is set before the loop."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        if self._target is not None:
            self._target()

    def is_alive(self):
        return False

    def join(self, timeout=None):
        return None


class _AutoStopEvent(threading.Event):
    """Event that reports set after N is_set checks (for follow loops only)."""

    def __init__(self, stop_after=2):
        super().__init__()
        self._checks = 0
        self._stop_after = stop_after

    def is_set(self):
        self._checks += 1
        if self._checks >= self._stop_after:
            return True
        return super().is_set()


_RealThread = threading.Thread


def _terminal_thread_factory(target=None, daemon=None, *args, **kwargs):
    """Use real threads except for follow-view wait helpers (noop to avoid races)."""
    if target and getattr(target, "__name__", "") in (
        "_wait_enter",
        "_wait_enter_live_view",
        "_wait_enter_logs",
    ):
        class _NoopThread:
            def start(self):
                return None

            def is_alive(self):
                return False

            def join(self, timeout=None):
                return None

        return _NoopThread()
    return _RealThread(target=target, daemon=daemon, *args, **kwargs)


def _mock_tty(monkeypatch):
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)


def _terminal_prompts(monkeypatch, commands):
    cmd_iter = iter(list(commands) + ["Q"])

    def _next(text="", *args, **kwargs):
        if "Press Enter" in str(text):
            return ""
        try:
            return next(cmd_iter)
        except StopIteration:
            return "Q"

    session = mock.Mock()
    session.prompt.side_effect = _next
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: session)
    return session


def test_live_signal_from_df_empty_frames_and_hold():
    compiled = compile_action_logic(
        {
            "enter": [["close", ">", 0]],
            "exit": [["close", "<", 0]],
            "any_enter": [],
            "any_exit": [],
            "trailing_stop_loss": 0,
        }
    )

    class _EmptyIterDF:
        empty = False
        columns = ["close", "rsi"]

        def tail(self, n):
            return self

        def itertuples(self):
            return iter([])

    label, price, indicators, parts = _live_signal_from_df(_EmptyIterDF(), compiled)
    assert label == "HOLD"
    assert price is None
    assert parts == []

    idx = pd.date_range("2024-01-01", periods=3, freq="min", tz="UTC")
    df = pd.DataFrame(
        {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1.0, 2.0, 3.0], "volume": [1, 1, 1], "rsi": [10, 20, 30]},
        index=idx,
    )
    with mock.patch.object(cli_mod, "determine_action_compiled", return_value="h"):
        label, price, _, parts = _live_signal_from_df(df, compiled)
    assert label == "HOLD"
    assert price == pytest.approx(3.0)
    assert parts


def test_terminal_follow_views_and_logs(
    archive_env, backtest_run, strategy_file, mock_backtest_result, monkeypatch, sample_ohlcv
):
    _mock_tty(monkeypatch)
    run_id, run_dir, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    live_legacy = archive_env / "live_logs" / f"{run_id}.log"
    live_legacy.parent.mkdir(exist_ok=True)
    live_legacy.write_text('{"message":"legacy live"}\n')
    stream_log = archive_env / "stream_logs" / f"{run_id}.jsonl"
    stream_log.parent.mkdir(exist_ok=True)
    stream_log.write_text('{"line":"stream"}\n')

    override = run_dir / "strategy.override.yml"
    override.write_text("symbol: BTC-USD\nfreq: 1Min\n")

    _terminal_prompts(
        monkeypatch,
        [
            "N",
            "OPEN",
            "PORTFOLIO",
            "LOGS ALL FOLLOW",
            "LIVE START",
            "LIVE VIEW",
            "STREAM START BTC-USD",
            "STREAM VIEW",
            "STREAM",
            "LIVE",
            "EDIT",
            "BT",
        ],
    )

    monkeypatch.setenv("FT_TERMINAL_SYNC_LIVE", "1")
    monkeypatch.delenv("FT_TERMINAL_SYNC_STREAM", raising=False)

    class _ImmediateTimer:
        def __init__(self, delay, func, args=None, kwargs=None):
            self._func = func

        def start(self):
            self._func()

    monkeypatch.setattr(cli_mod.threading, "Timer", _ImmediateTimer)
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    monkeypatch.setattr(cli_mod, "save", lambda *a, **k: {"path": str(run_dir)})
    monkeypatch.setattr(cli_mod, "create_plot", mock.Mock())
    monkeypatch.setattr(cli_mod, "_edit_strategy_interactive", lambda *a, **k: str(strategy_file))
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(10))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(cli_mod.threading, "Thread", _terminal_thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Event", lambda: _AutoStopEvent(stop_after=2))

    orig_load = cli_mod._load_backtest_run

    def _load_with_override(path, rid):
        rp, sm, tdf, df = orig_load(path, rid)
        sm = dict(sm)
        sm["strategy_override_path"] = str(override)
        sm["strategy"] = {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []}
        return rp, sm, tdf, df

    monkeypatch.setattr(cli_mod, "_load_backtest_run", _load_with_override)

    # Populate stream/live buffers before page render
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_stream_channel_name_helper():
    assert cli_mod._stream_channel_name("trades") == "market_trades"
    assert cli_mod._stream_channel_name("level2") == "level2"


def test_terminal_stream_trades_channel_and_pages(
    archive_env, backtest_run, monkeypatch, sample_ohlcv
):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "websockets":
            raise ImportError("no websockets")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    _terminal_prompts(monkeypatch, ["STREAM START BTC-USD channels=trades", "STREAM", "Q"])
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_live_start_strategy_errors_and_stream_restart(
    archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv
):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("FT_TERMINAL_SYNC_LIVE", "1")
    monkeypatch.delenv("FT_TERMINAL_SYNC_STREAM", raising=False)
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    class FakeAliveStreamThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            return None

        def is_alive(self):
            return getattr(self._target, "__name__", "") == "_run_stream"

        def join(self, timeout=None):
            return None

    def thread_factory(target=None, daemon=None, *args, **kwargs):
        if target and getattr(target, "__name__", "") == "_run_stream":
            return FakeAliveStreamThread(target=target, daemon=daemon)
        return _terminal_thread_factory(target=target, daemon=daemon, *args, **kwargs)

    class _ImmediateTimer:
        def __init__(self, delay, func, args=None, kwargs=None):
            self._func = func

        def start(self):
            self._func()

    calls = {"n": 0}

    def open_side(p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bad strat load")
        return {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []}

    monkeypatch.setattr(cli_mod.threading, "Thread", thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Timer", _ImmediateTimer)
    monkeypatch.setattr(cli_mod, "open_strat_file", open_side)
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(10))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    _terminal_prompts(
        monkeypatch,
        [
            "LIVE START",
            "STREAM START BTC-USD",
            "LIVE START ETH-USD",
            "LIVE",
            "Q",
        ],
    )
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_open_strat_and_bt_errors(
    archive_env, backtest_run, strategy_file, monkeypatch, mock_backtest_result
):
    _mock_tty(monkeypatch)
    run_id, run_dir, _ = backtest_run
    override = run_dir / "strategy.override.yml"
    override.write_text("symbol: BTC-USD\nfreq: 1Min\n")

    _terminal_prompts(monkeypatch, ["OPEN STRAT", "EDIT STRAT", "BT", "Q"])
    monkeypatch.setattr(cli_mod, "_pick_from_list", mock.Mock(return_value=str(strategy_file)))
    monkeypatch.setattr(cli_mod, "_edit_strategy_interactive", lambda *a, **k: str(strategy_file))

    real_open = open
    writes = {"n": 0}

    def selective_open(path, *args, **kwargs):
        text = str(path)
        mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
        if text.endswith("last_strategy_path.txt") and "w" in mode:
            raise OSError("write fail")
        if text.endswith("strategy.yml") or text.endswith("test_strategy.yml"):
            writes["n"] += 1
            if writes["n"] == 1:
                return real_open(path, *args, **kwargs)
            raise RuntimeError("load fail after pick")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", selective_open)
    monkeypatch.setattr(cli_mod, "open_strat_file", mock.Mock(side_effect=RuntimeError("bad strat")))
    monkeypatch.setattr(cli_mod, "run_backtest", mock.Mock(side_effect=RuntimeError("bt fail")))

    orig_load = cli_mod._load_backtest_run

    def _load_override(path, rid):
        rp, sm, tdf, df = orig_load(path, rid)
        sm = dict(sm)
        sm.pop("strategy_override_path", None)
        sm["strategy"] = {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []}
        return rp, sm, tdf, df

    monkeypatch.setattr(cli_mod, "_load_backtest_run", _load_override)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_bt_override_progress_and_portfolio_override(
    archive_env, backtest_run, strategy_file, mock_backtest_result, monkeypatch, sample_ohlcv
):
    _mock_tty(monkeypatch)
    run_id, run_dir, _ = backtest_run
    override = run_dir / "strategy.override.yml"
    override.write_text("symbol: BTC-USD\nfreq: 1Min\n")

    def fake_run(strategy, progress_callback=None, **kw):
        if progress_callback:
            progress_callback({"phase": "data", "percent": 50})
            progress_callback({"phase": "actions", "percent": 75})
            progress_callback({"phase": "simulation", "percent": 100})
        return mock_backtest_result

    _terminal_prompts(monkeypatch, ["BT", "PORTFOLIO START", "Q"])
    monkeypatch.setattr(cli_mod, "run_backtest", fake_run)
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))

    orig_load = cli_mod._load_backtest_run

    def _load_override(path, rid):
        rp, sm, tdf, df = orig_load(path, rid)
        sm = dict(sm)
        sm["strategy_override_path"] = str(override)
        return rp, sm, tdf, df

    monkeypatch.setattr(cli_mod, "_load_backtest_run", _load_override)
    if (archive_env / "last_strategy_path.txt").exists():
        (archive_env / "last_strategy_path.txt").unlink()
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_logs_read_errors_and_follow(
    archive_env, backtest_run, monkeypatch
):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    stream_log = archive_env / "stream_logs" / f"{run_id}.jsonl"
    stream_log.parent.mkdir(exist_ok=True)
    stream_log.write_text('{"line":"x"}\n')

    _terminal_prompts(monkeypatch, ["LOGS STREAM FOLLOW", "Q"])
    monkeypatch.setattr(cli_mod.threading, "Thread", _terminal_thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Event", lambda: _AutoStopEvent(stop_after=3))
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    real_open = open
    opens = {"n": 0}

    def flaky_open(path, *args, **kwargs):
        text = str(path)
        if "stream_logs" in text and text.endswith(".jsonl"):
            opens["n"] += 1
            if opens["n"] == 1:
                return real_open(path, *args, **kwargs)
            raise OSError("read fail")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", flaky_open)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_logs_follow_reads_lines(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"one"}\n')

    reads = {"n": 0}
    real_open = open

    class FollowFile:
        closed = False

        def __init__(self, fh):
            self._fh = fh

        def readline(self):
            reads["n"] += 1
            if reads["n"] == 1:
                return '{"line":"new"}\n'
            raise KeyboardInterrupt()

        def seek(self, *a, **k):
            return self._fh.seek(*a, **k)

        def close(self):
            self.closed = True

    def open_side(path, *args, **kwargs):
        if str(path).endswith(".jsonl"):
            return FollowFile(real_open(path, *args, **kwargs))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", open_side)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(run_id=run_id, index=None, kind="live", follow=True, tail=0)


def test_logs_tail_file_missing_path(cli_runner, archive_env, backtest_run):
    run_id, _, _ = backtest_run
    assert cli_runner.invoke(cli_mod.app, ["logs", "--run-id", run_id, "--tail", "0"]).exit_code == 0


def test_terminal_stream_join_exception(
    archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv
):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("FT_TERMINAL_SYNC_LIVE", "1")
    monkeypatch.delenv("FT_TERMINAL_SYNC_STREAM", raising=False)
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    class JoinFailStreamThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            return None

        def is_alive(self):
            return getattr(self._target, "__name__", "") == "_run_stream"

        def join(self, timeout=None):
            raise RuntimeError("join fail")

    class _ImmediateTimer:
        def __init__(self, delay, func, args=None, kwargs=None):
            self._func = func

        def start(self):
            self._func()

    def thread_factory(target=None, daemon=None, *args, **kwargs):
        if target and getattr(target, "__name__", "") == "_run_stream":
            return JoinFailStreamThread(target=target, daemon=daemon)
        return _terminal_thread_factory(target=target, daemon=daemon, *args, **kwargs)

    monkeypatch.setattr(cli_mod.threading, "Thread", thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Timer", _ImmediateTimer)
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(10))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    _terminal_prompts(monkeypatch, ["STREAM START BTC-USD", "LIVE START ETH-USD", "Q"])
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_edit_from_summary_strategy(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, run_dir, _ = backtest_run
    last = archive_env / "last_strategy_path.txt"
    if last.exists():
        last.unlink()

    _terminal_prompts(monkeypatch, ["EDIT STRAT", "Q"])
    monkeypatch.setattr(cli_mod, "_edit_strategy_interactive", lambda *a, **k: str(run_dir / "strategy.override.yml"))
    monkeypatch.setattr(cli_mod, "open_strat_file", mock.Mock(side_effect=RuntimeError("no file")))
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_open_strat_write_and_load_errors(archive_env, backtest_run, strategy_file, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    real_open = open
    load_calls = {"n": 0}

    def selective_open(path, *args, **kwargs):
        text = str(path)
        mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
        if text.endswith("last_strategy_path.txt") and "w" in mode:
            raise OSError("write fail")
        return real_open(path, *args, **kwargs)

    def open_strat_side(path):
        load_calls["n"] += 1
        if load_calls["n"] == 1:
            return {"name": "x", "symbol": "BTC-USD"}
        raise RuntimeError("summary load fail")

    _terminal_prompts(monkeypatch, ["OPEN STRAT", "Q"])
    monkeypatch.setattr("builtins.open", selective_open)
    monkeypatch.setattr(cli_mod, "_pick_from_list", mock.Mock(return_value=str(strategy_file)))
    monkeypatch.setattr(cli_mod, "open_strat_file", open_strat_side)
    monkeypatch.setattr(cli_mod.Confirm, "ask", mock.Mock(return_value=False))
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_logs_follow_tail_lines(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    stream_log = archive_env / "stream_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    stream_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"live"}\n')
    stream_log.write_text('{"line":"stream"}\n')

    class _ImmediateTimer:
        def __init__(self, delay, func, args=None, kwargs=None):
            self._func = func

        def start(self):
            self._func()

    read_counts = {"live": 0, "stream": 0}
    real_open = open

    class TailFile:
        closed = False

        def __init__(self, fh, key):
            self._fh = fh
            self._key = key

        def readline(self):
            read_counts[self._key] += 1
            if read_counts[self._key] == 1:
                return '{"line":"new"}\n'
            return ""

        def seek(self, *a, **k):
            return self._fh.seek(*a, **k)

        def close(self):
            self.closed = True

    def open_side(path, *args, **kwargs):
        text = str(path)
        if text.endswith(".jsonl") and "live_logs" in text:
            return TailFile(real_open(path, *args, **kwargs), "live")
        if text.endswith(".jsonl") and "stream_logs" in text:
            return TailFile(real_open(path, *args, **kwargs), "stream")
        return real_open(path, *args, **kwargs)

    _terminal_prompts(monkeypatch, ["LOGS ALL FOLLOW", "Q"])
    monkeypatch.setattr("builtins.open", open_side)
    monkeypatch.setattr(cli_mod.threading, "Thread", _terminal_thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Event", lambda: _AutoStopEvent(stop_after=2))
    monkeypatch.setattr(cli_mod.threading, "Timer", _ImmediateTimer)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_logs_stream_read_error(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    stream_log = archive_env / "stream_logs" / f"{run_id}.jsonl"
    stream_log.parent.mkdir(exist_ok=True)
    stream_log.write_text('{"line":"x"}\n')

    _terminal_prompts(monkeypatch, ["LOGS STREAM", "Q"])
    real_open = open

    def open_side(path, *args, **kwargs):
        if "stream_logs" in str(path):
            raise OSError("read fail")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", open_side)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_logs_follow_read_exception(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"one"}\n')

    class BadFollow:
        closed = False

        def readline(self):
            raise OSError("read fail")

        def seek(self, *a, **k):
            return None

        def close(self):
            self.closed = True

    real_open = open

    def open_side(path, *args, **kwargs):
        if str(path).endswith(".jsonl"):
            return BadFollow()
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", open_side)
    calls = {"n": 0}

    def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(run_id=run_id, index=None, kind="live", follow=True, tail=0)


def test_terminal_live_page_with_history_render(
    archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv
):
    _mock_tty(monkeypatch)
    monkeypatch.delenv("FT_TERMINAL_SYNC_LIVE", raising=False)
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    class _NoopTimer:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return None

    wait_calls = {"n": 0}
    orig_wait = threading.Event.wait

    def wait_side(self, timeout=None):
        wait_calls["n"] += 1
        if wait_calls["n"] >= 1:
            self.set()
            return True
        return orig_wait(self, timeout)

    cmd_iter = iter(["LIVE START", "LIVE", "Q"])

    def prompt_side(text="", *args, **kwargs):
        if "Press Enter" in str(text):
            return ""
        cmd = next(cmd_iter)
        if cmd == "LIVE":
            time_mod.sleep(0.2)
        return cmd

    session = mock.Mock()
    session.prompt.side_effect = prompt_side
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: session)
    monkeypatch.setattr(cli_mod.threading, "Timer", _NoopTimer)
    monkeypatch.setattr(threading.Event, "wait", wait_side)
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(10))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_follow_view_loops_with_content(
    archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv
):
    _mock_tty(monkeypatch)
    monkeypatch.delenv("FT_TERMINAL_SYNC_LIVE", raising=False)
    run_id, _, _ = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    class _NoopTimer:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return None

    wait_calls = {"n": 0}
    orig_wait = threading.Event.wait

    def wait_side(self, timeout=None):
        wait_calls["n"] += 1
        if wait_calls["n"] >= 1:
            self.set()
            return True
        return orig_wait(self, timeout)

    cmd_iter = iter(["STREAM START BTC-USD", "LIVE START", "LIVE VIEW", "STREAM VIEW", "Q"])

    def prompt_side(text="", *args, **kwargs):
        if "Press Enter" in str(text):
            return ""
        cmd = next(cmd_iter)
        if cmd == "LIVE VIEW":
            time_mod.sleep(0.2)
        return cmd

    session = mock.Mock()
    session.prompt.side_effect = prompt_side
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: session)
    monkeypatch.setattr(cli_mod.threading, "Timer", _NoopTimer)
    monkeypatch.setattr(threading.Event, "wait", wait_side)
    monkeypatch.setattr(cli_mod.threading, "Thread", _terminal_thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Event", lambda: _AutoStopEvent(stop_after=2))
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "freq": "1Min", "datapoints": []})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(10))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "websockets":
            raise ImportError("no websockets")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_follow_wait_prompts(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"live"}\n')

    _terminal_prompts(monkeypatch, ["LIVE VIEW", "STREAM VIEW", "LOGS ALL FOLLOW", "Q"])
    monkeypatch.setattr(cli_mod.threading, "Thread", _SyncFollowThread)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_portfolio_start_uses_override_path(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, run_dir, _ = backtest_run
    override = run_dir / "strategy.override.yml"
    override.write_text("symbol: BTC-USD\nfreq: 1Min\n")
    last = archive_env / "last_strategy_path.txt"
    if last.exists():
        last.unlink()

    _terminal_prompts(monkeypatch, ["PORTFOLIO START", "Q"])
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))

    orig_load = cli_mod._load_backtest_run

    def _load_override(path, rid):
        rp, sm, tdf, df = orig_load(path, rid)
        sm = dict(sm)
        sm["strategy_override_path"] = str(override)
        return rp, sm, tdf, df

    monkeypatch.setattr(cli_mod, "_load_backtest_run", _load_override)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)
    inserted = cli_mod.subprocess.run.call_args[0][0]
    assert str(override) in inserted


def test_terminal_logs_follow_legacy_and_errors(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    stream_legacy = archive_env / "stream_logs" / f"{run_id}.log"
    stream_legacy.parent.mkdir(exist_ok=True)
    stream_legacy.write_text('{"line":"legacy"}\n')

    _terminal_prompts(monkeypatch, ["LOGS STREAM FOLLOW", "Q"])
    monkeypatch.setattr(cli_mod.threading, "Thread", _terminal_thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Event", lambda: _AutoStopEvent(stop_after=2))
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    real_open = open

    def open_side(path, *args, **kwargs):
        text = str(path)
        if "live_logs" in text and text.endswith(".jsonl"):
            raise OSError("live follow fail")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", open_side)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_terminal_logs_follow_live_read_exception(archive_env, backtest_run, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run
    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"live"}\n')

    _terminal_prompts(monkeypatch, ["LOGS LIVE FOLLOW", "Q"])
    monkeypatch.setattr(cli_mod.threading, "Thread", _terminal_thread_factory)
    monkeypatch.setattr(cli_mod.threading, "Event", lambda: _AutoStopEvent(stop_after=2))
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    real_open = open
    opens = {"n": 0}

    def open_side(path, *args, **kwargs):
        text = str(path)
        mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
        if "live_logs" in text and text.endswith(".jsonl") and "r" in mode:
            opens["n"] += 1
            if opens["n"] >= 2:
                raise OSError("live follow fail")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", open_side)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)


def test_save_last_strategy_path_write_failure(tmp_path, monkeypatch):
    path = str(tmp_path / "last_strategy_path.txt")
    monkeypatch.setattr("builtins.open", mock.Mock(side_effect=OSError("write fail")))
    cli_mod._save_last_strategy_path(path, "/tmp/strategy.yml")
