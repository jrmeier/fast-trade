"""Tests for fast_trade.terminal_ui and cli terminal helpers."""

import datetime
import json
import os
import threading
import time
from io import StringIO
from unittest import mock

import pandas as pd
import pytest
from rich.console import Console
from rich.panel import Panel
from typer.testing import CliRunner

import fast_trade.terminal_ui as tui
from fast_trade import cli as cli_mod


@pytest.fixture
def console():
    return Console(file=StringIO(), width=120, force_terminal=True, legacy_windows=False)


def test_render_trades_table_action_column_reorder(console):
    df = pd.DataFrame(
        {"close": [1.0], "volume": [2.0]},
        index=pd.date_range("2024-01-01", periods=1, freq="h"),
    )
    df["action"] = "e"
    tui.render_trades_table(console, df, 0, 5)


def test_build_dashboard_layout_empty_metrics(console, archive_env):
    class SizedConsole(Console):
        def __init__(self, height, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._height = height

        @property
        def size(self):
            return mock.Mock(height=self._height, width=120)

    sized = SizedConsole(30, file=StringIO(), width=120, force_terminal=True)
    layout = tui.build_dashboard_layout(
        sized, "run", "/tmp", {}, pd.DataFrame(), pd.DataFrame(), [], str(archive_env)
    )
    assert layout is not None


def test_render_trades_table_empty_and_paged(console):
    tui.render_trades_table(console, None, 0, 5)
    tui.render_trades_table(console, pd.DataFrame(), 0, 5)
    df = pd.DataFrame(
        {"close": [1, 2, 3], "action": ["e", "x", "e"]},
        index=pd.date_range("2024-01-01", periods=3, freq="h"),
    )
    tui.render_trades_table(console, df, 5, 2)
    tui.render_trades_table(console, df, 0, 2)
    df2 = pd.DataFrame({"close": [1]}, index=pd.date_range("2024-01-01", periods=1, freq="h"))
    tui.render_trades_table(console, df2, 0, 5)


def test_render_summary_and_tearsheet(console):
    summary = {
        "return_perc": 1.0,
        "strategy": {"name": "S", "symbol": "BTC", "exchange": "binanceus", "freq": "1H"},
        "position_metrics": {"x": 1},
        "extra": "scalar",
    }
    tui.render_summary_page(console, summary)
    tui.render_tearsheet(console, summary)
    tui.render_tearsheet(console, {"strategy": {}})  # minimal
    tui.render_tearsheet(console, {})  # no data


def test_format_stream_line_channels():
    ts = "2024-01-01T00:00:00"
    trades = tui.format_stream_line(
        {
            "channel": "market_trades",
            "timestamp": ts,
            "events": [{"product_id": "BTC", "trades": [{"side": "buy", "price": "1", "size": "2"}]}],
        }
    )
    assert trades and "market_trades" in trades[0]

    level2 = tui.format_stream_line(
        {
            "channel": "level2",
            "timestamp": ts,
            "events": [
                {
                    "product_id": "BTC",
                    "type": "update",
                    "updates": [{"side": "bid", "price_level": "1", "new_quantity": "2"}],
                }
            ],
        }
    )
    assert level2

    other = tui.format_stream_line({"channel": "heartbeat", "events": [{"type": "ping"}]})
    assert other

    empty = tui.format_stream_line({"channel": "x", "events": []})
    assert "(no events)" in empty[0]


def test_parse_trade_time_and_candle_helpers():
    assert tui.parse_trade_time("") is None
    assert tui.parse_trade_time("bad") is None
    dt = tui.parse_trade_time("2024-01-01T12:00:00Z")
    assert dt is not None
    floored = tui.minute_floor(dt)
    assert floored.second == 0

    candle = {"open": None, "high": None, "low": None, "close": None, "volume": 0.0}
    tui.update_candle(candle, 10.0, 1.0)
    assert candle["open"] == 10.0
    tui.update_candle(candle, 12.0, 2.0)
    assert candle["high"] == 12.0
    assert candle["volume"] == 3.0


def test_render_position_and_graph(console, tmp_path, sample_ohlcv):
    tui.render_position_page(console, {})
    tui.render_position_page(console, {"position_metrics": {"a": 1}})

    run_path = tmp_path / "run"
    run_path.mkdir()
    (run_path / "plot.png").write_bytes(b"x")
    tui.render_graph_page(console, str(run_path), sample_ohlcv.head(10), None)
    tui.render_graph_page(console, str(run_path), None, None)

    html_path = tmp_path / "run2"
    html_path.mkdir()
    (html_path / "plot.html").write_text("<html></html>")
    tui.render_graph_page(console, str(html_path), pd.DataFrame(), pd.DataFrame())


def test_dashboard_widgets_and_layout(console, archive_env, backtest_run, sample_ohlcv):
    run_id, run_dir, summary = backtest_run
    trade_df = pd.DataFrame({"close": [1.0]}, index=pd.date_range("2024-01-01", periods=1, freq="h"))
    runs = [run_id]

    panel = tui._dashboard_table("T", [["k", "v"]])
    assert isinstance(panel, Panel)
    panel2 = tui._dashboard_text("T", ["line"])
    assert isinstance(panel2, Panel)

    tui._WIDGET_CACHE.clear()
    fake_panel = tui._dashboard_text("NYC Weather", ["cached"])
    tui._WIDGET_CACHE["weather_nyc"] = {"ts": time.time(), "panel": fake_panel}
    assert tui._widget_weather_nyc() is fake_panel

    tui._WIDGET_CACHE.clear()
    resp = mock.Mock()
    resp.raise_for_status = mock.Mock()
    resp.json.return_value = {
        "current_condition": [
            {
                "temp_F": "70",
                "temp_C": "21",
                "weatherDesc": [{"value": "Clear"}],
                "humidity": "40",
                "windspeedMiles": "5",
            }
        ]
    }

    def run_fetch():
        fetch_fn = None
        with mock.patch("fast_trade.terminal_ui.requests.get", return_value=resp):
            tui._WIDGET_CACHE.clear()
            tui._widget_weather_nyc()
            if "weather_nyc" in tui._WIDGET_CACHE:
                entry = tui._WIDGET_CACHE["weather_nyc"]
                for t in threading.enumerate():
                    if t.name.startswith("Thread") and t.is_alive():
                        t.join(timeout=1.0)

    run_fetch()

    tui._WIDGET_CACHE.clear()
    with mock.patch("fast_trade.terminal_ui.requests.get", side_effect=OSError("net")):
        p = tui._widget_weather_nyc()
        for t in threading.enumerate():
            if t != threading.main_thread() and t.is_alive():
                t.join(timeout=1.0)
        assert p is not None

    class SizedConsole(Console):
        def __init__(self, height, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._height = height

        @property
        def size(self):
            return mock.Mock(height=self._height, width=120)

    for height in [30, 40, 50]:
        sized = SizedConsole(height, file=StringIO(), width=120, force_terminal=True)
        layout = tui.build_dashboard_layout(
            sized,
            run_id,
            str(run_dir),
            summary,
            trade_df,
            sample_ohlcv.head(5),
            runs,
            str(archive_env),
            stream_info={
                "status": "running",
                "product": "BTC",
                "channels": ["trades"],
                "mps": 1.5,
                "live": {"status": "ok"},
            },
        )
        assert layout is not None

    tui.render_dashboard(console, run_id, str(run_dir), summary, trade_df, sample_ohlcv.head(5), runs, str(archive_env))
    tui.build_stream_panel({"status": "on", "product": "BTC", "channels": ["a"], "mps": 2})
    assert tui.stringify_value({"a": 1}).startswith("{")
    assert tui.stringify_value([1]).startswith("[")
    tui.render_dict_table(console, "D", {"k": "v", "n": 1})


def test_cli_helper_functions(archive_env, backtest_run, strategy_file, tmp_path):
    from prompt_toolkit import PromptSession

    run_id, run_dir, summary = backtest_run
    backtests_path = str(archive_env / "backtests")

    assert cli_mod._apply_mods({"a": 1}, None)["a"] == 1
    with pytest.raises(Exception):
        cli_mod._apply_mods({"a": 1}, ["k"])
    assert cli_mod._apply_mods({"a": 1}, ["b", "2"])["b"] == "2"

    assert cli_mod._format_log_line('{"line":"x"}') == "x"
    assert cli_mod._format_log_line('{"message":"m"}') == "m"
    assert cli_mod._format_log_line('{"event":{"a":1}}') == '{"a": 1}'
    assert cli_mod._format_log_line("plain") == "plain"
    assert cli_mod._format_log_line("[1,2]") == "[1, 2]"

    path, s, tdf, df = cli_mod._load_backtest_run(backtests_path, run_id)
    assert s["return_perc"] == 12.5

    # summary json migration path
    json_run = archive_env / "backtests" / "json_run"
    json_run.mkdir()
    with open(json_run / "summary.json", "w") as fh:
        json.dump({"return_perc": 1}, fh)
    loaded = cli_mod._load_backtest_summary(str(json_run))
    assert loaded["return_perc"] == 1

    assert cli_mod._max_datapoint_periods({"datapoints": [{"args": [3, "x"]}, {"args": [10]}]}) == 10
    assert cli_mod._max_datapoint_periods({}) == 0

    parquet_path = archive_env / "coinbase" / "BTC-USD.parquet"
    sample = pd.DataFrame(
        {"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]},
        index=pd.to_datetime(["2024-01-01"]),
    )
    sample.index.name = "date"
    sample.to_parquet(parquet_path)
    ohlcv = cli_mod._load_latest_ohlcv("coinbase", "BTC-USD", 1)
    assert len(ohlcv) == 1

    with mock.patch("fast_trade.archive.db_helpers._safe_read_parquet", return_value=None), mock.patch(
        "fast_trade.archive.db_helpers.get_kline", return_value=sample
    ):
        ohlcv2 = cli_mod._load_latest_ohlcv("coinbase", "BTC-USD", 5)
        assert not ohlcv2.empty

    rows = [(datetime.datetime(2024, 1, 1), {"open": 1, "close": 1, "high": 1, "low": 1, "volume": 1})]
    cli_mod._append_klines_to_archive("BTC-USD", [])
    cli_mod._append_klines_to_archive("BTC-USD", rows)
    cli_mod._append_klines_to_archive("BTC-USD", rows)  # merge existing

    trades = [{"ts": "2024-01-01T00:00:00", "trade_id": "t1", "price": 1, "size": 1}]
    cli_mod._append_trades_parquet("BTC-USD", [])
    cli_mod._append_trades_parquet("BTC-USD", trades)
    cli_mod._append_trades_parquet("BTC-USD", trades)  # dedupe

    assert cli_mod._parse_input_value('{"a":1}') == {"a": 1}
    assert cli_mod._parse_input_value("text") == "text"
    assert cli_mod._parse_input_value(None) is None
    assert cli_mod._parse_input_value("  ") == "  "

    out = tmp_path / "out.yml"
    cli_mod._save_yaml_or_json(str(out), {"k": 1})
    assert out.exists()

    files = cli_mod._list_strategy_files()
    assert any("test_strategy" in f for f in files)

    session = mock.Mock()
    session.prompt.side_effect = ["2", "bad", "99", "1"]
    assert cli_mod._pick_from_list(session, "Items", ["a", "b"]) == "b"
    assert cli_mod._pick_from_list(session, "Items", ["a"]) is None
    assert cli_mod._pick_from_list(session, "Items", ["a"]) is None
    assert cli_mod._pick_from_list(session, "Items", []) is None


def test_edit_interactive_flows(archive_env, backtest_run, tmp_path):

    run_id, run_dir, summary = backtest_run

    session = mock.Mock()
    session.prompt.side_effect = ["name", "Updated", "S"]
    with mock.patch("fast_trade.cli.PromptSession", return_value=session), mock.patch(
        "fast_trade.cli.Confirm.ask", return_value=False
    ):
        result = cli_mod._edit_dict_interactive("Edit", {"name": "Old"})
    assert result["name"] == "Updated"

    session.prompt.side_effect = ["", "Q"]
    with mock.patch("fast_trade.cli.PromptSession", return_value=session):
        assert cli_mod._edit_dict_interactive("Edit", {"a": 1}) is None

    session.prompt.side_effect = ["newkey", "actualval", "S"]
    with mock.patch("fast_trade.cli.PromptSession", return_value=session), mock.patch(
        "fast_trade.cli.Confirm.ask", return_value=True
    ):
        out = cli_mod._edit_dict_interactive("Edit", {})
    assert out["newkey"] == "actualval"

    session2 = mock.Mock()
    session2.prompt.side_effect = ["R", "x", "", "S"]
    with mock.patch("fast_trade.cli.PromptSession", return_value=session2):
        cli_mod._edit_dict_interactive("Edit", {"x": 1})

    with mock.patch("fast_trade.cli._edit_dict_interactive", return_value={"name": "N"}):
        path = cli_mod._edit_strategy_interactive({"name": "O"}, str(run_dir))
        assert path and os.path.exists(path)

    with mock.patch("fast_trade.cli._edit_dict_interactive", return_value=None):
        assert cli_mod._edit_strategy_interactive({}, str(run_dir)) is None

    with mock.patch("fast_trade.cli._edit_dict_interactive", return_value={"return_perc": 9}):
        updated = cli_mod._edit_backtest_interactive(summary, str(run_dir))
        assert updated["return_perc"] == 9

    session.prompt.side_effect = ["", str(tmp_path / "new.yml")]
    with mock.patch("fast_trade.cli._edit_dict_interactive", return_value={"name": "New"}), mock.patch(
        "fast_trade.cli.PromptSession", return_value=session
    ):
        p = cli_mod._create_strategy_interactive()
        assert p and os.path.exists(p)

    with mock.patch("fast_trade.cli._edit_dict_interactive", return_value=None):
        assert cli_mod._create_strategy_interactive() is None


def _mock_tty(monkeypatch):
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)


def test_terminal_cmd_non_tty(cli_runner, monkeypatch):
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: False)
    result = cli_runner.invoke(cli_mod.app, ["terminal"])
    assert result.exit_code != 0


def test_terminal_cmd_missing_archive(cli_runner, tmp_path, monkeypatch):
    _mock_tty(monkeypatch)
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path / "empty"))
    result = cli_runner.invoke(cli_mod.app, ["terminal"])
    assert result.exit_code != 0


def test_terminal_cmd_interactive_loop(archive_env, backtest_run, strategy_file, monkeypatch):
    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run

    commands = ["TR", "N", "P", "SUM", "TS", "POS", "HELP", "UA", "Q"]
    cmd_iter = iter(commands)
    session = mock.Mock()
    session.prompt.side_effect = lambda *a, **k: next(cmd_iter, "Q")
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)
    monkeypatch.setattr(cli_mod, "update_archive", mock.Mock())
    monkeypatch.setattr(cli_mod.threading, "Thread", lambda *a, **k: mock.Mock(is_alive=lambda: False, start=mock.Mock(), join=mock.Mock()))
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=2)


def test_terminal_cmd_extended_commands(archive_env, backtest_run, strategy_file, mock_backtest_result, monkeypatch, sample_ohlcv):
    _mock_tty(monkeypatch)
    run_id, run_dir, summary = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))
    override = run_dir / "strategy.override.yml"
    override.write_text("symbol: BTCUSDT\nexchange: binanceus\nfreq: 1H\nstart: 2024-01-01\nstop: 2024-12-31\n")
    summary = dict(summary)
    summary["strategy_override_path"] = str(override)

    commands = [
        "SHOW STRAT", "OPEN STRAT", "OPEN BT", "EDIT BT", "NEW STRAT",
        "BT SAVE PLOT", "SAVE", "LOGS STREAM", "STREAM START BTC-USD",
        "STREAM STOP", "LIVE START", "LIVE STOP", "PORTFOLIO START", "Q",
    ]
    cmd_iter = iter(commands)
    session = mock.Mock()
    session.prompt.side_effect = lambda *a, **k: next(cmd_iter, "Q")

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    monkeypatch.setattr(cli_mod, "save", lambda *a, **k: {"path": str(run_dir)})
    monkeypatch.setattr(cli_mod, "create_plot", mock.Mock())
    monkeypatch.setattr(cli_mod, "_pick_from_list", mock.Mock(side_effect=[str(strategy_file), run_id]))
    monkeypatch.setattr(cli_mod, "_edit_dict_interactive", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "_create_strategy_interactive", mock.Mock())
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {
        "symbol": "BTC-USD", "exchange": "coinbase", "freq": "1H",
        "start": "2024-01-01", "stop": "2024-12-31", "datapoints": [{"args": [5]}],
    })
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(30))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {"enter": [], "exit": [], "any_enter": [], "any_exit": [], "trailing_stop_loss": False})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "h")
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))
    monkeypatch.setattr(cli_mod.Confirm, "ask", mock.Mock(return_value=False))

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self._alive = True

        def start(self):
            return None

        def is_alive(self):
            return self._alive

        def join(self, timeout=None):
            self._alive = False

    monkeypatch.setattr(cli_mod.threading, "Thread", FakeThread)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)

    # patch summary load to include override path
    orig_load = cli_mod._load_backtest_run

    def _load_with_override(path, rid):
        rp, sm, tdf, df = orig_load(path, rid)
        sm = dict(sm)
        sm["strategy_override_path"] = str(override)
        return rp, sm, tdf, df

    monkeypatch.setattr(cli_mod, "_load_backtest_run", _load_with_override)
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=2)


def test_terminal_cmd_index_and_load_errors(archive_env, backtest_run, monkeypatch):
    result = CliRunner().invoke(cli_mod.app, ["terminal", "--index", "99"])
    assert result.exit_code != 0

    bad_run = archive_env / "backtests" / "broken"
    bad_run.mkdir()
    (bad_run / "summary.yml").write_text("x: [")
    result2 = CliRunner().invoke(cli_mod.app, ["terminal", "--run-id", "broken"])
    assert result2.exit_code != 0


def test_terminal_stream_and_live_branches(archive_env, backtest_run, strategy_file, monkeypatch, sample_ohlcv, tmp_path):

    _mock_tty(monkeypatch)
    run_id, run_dir, summary = backtest_run
    (archive_env / "last_strategy_path.txt").write_text(str(strategy_file))

    live_log = archive_env / "live_logs" / f"{run_id}.jsonl"
    live_log.parent.mkdir(exist_ok=True)
    live_log.write_text('{"line":"live"}\n')
    stream_log = archive_env / "stream_logs" / f"{run_id}.log"
    stream_log.parent.mkdir(exist_ok=True)
    stream_log.write_text("legacy\n")

    cmds = [
        "LIVE START ETH-USD",
        "STREAM START",
        "BT MODS freq --mods 1H",
        "PORTFOLIO START",
        "Q",
    ]
    cmd_iter = iter(cmds)

    def _next_prompt(*args, **kwargs):
        try:
            return next(cmd_iter)
        except StopIteration:
            return "Q"

    session = mock.Mock()
    session.prompt.side_effect = _next_prompt
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)
    monkeypatch.setattr(cli_mod, "open_strat_file", lambda p: {"symbol": "BTC-USD", "exchange": "coinbase", "freq": "1H", "datapoints": [{"args": [5]}]})
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: sample_ohlcv.head(50))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "e")
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: {"summary": summary, "df": sample_ohlcv.head(5), "trade_df": None})
    monkeypatch.setattr(cli_mod, "subprocess", mock.Mock(run=mock.Mock()))

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self._alive = True

        def start(self):
            return None

        def is_alive(self):
            return self._alive

        def join(self, timeout=None):
            self._alive = False

    monkeypatch.setattr(cli_mod.threading, "Thread", FakeThread)
    monkeypatch.setattr(cli_mod.threading, "Event", threading.Event)

    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=20)


def test_terminal_stream_websocket_loop(archive_env, backtest_run, monkeypatch, sample_ohlcv):
    import asyncio

    _mock_tty(monkeypatch)
    run_id, _, _ = backtest_run

    class FakeWS:
        def __init__(self):
            self._sent = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def send(self, msg):
            return None

        async def recv(self):
            if self._sent == 0:
                self._sent += 1
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
                                    }
                                ],
                            }
                        ],
                    }
                )
            await asyncio.sleep(0.01)
            raise asyncio.TimeoutError()

    ws_mock = mock.Mock(return_value=FakeWS())
    monkeypatch.setattr("websockets.connect", ws_mock)

    commands = ["STREAM START BTC-USD channels=trades,level2", "STREAM STOP", "Q"]
    cmd_iter = iter(commands)
    session = mock.Mock()
    session.prompt.side_effect = lambda *a, **k: next(cmd_iter, "Q")
    monkeypatch.setattr(cli_mod, "PromptSession", lambda **k: session)

    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=20)

