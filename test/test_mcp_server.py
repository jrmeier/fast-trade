import json
from types import SimpleNamespace

import pytest

import fast_trade.mcp_server as mcp_server


def test_list_strategies(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    strategies = archive / "strategies"
    strategies.mkdir(parents=True)
    (strategies / "a.yml").write_text("x: 1", encoding="utf-8")
    (strategies / "b.yaml").write_text("x: 2", encoding="utf-8")
    (strategies / ".hidden.yml").write_text("x: 3", encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))

    items = mcp_server.list_strategies()
    assert len(items) == 2
    assert items[0].endswith("a.yml")
    assert items[1].endswith("b.yaml")


def test_tail_log(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    live_dir = archive / "live_logs"
    live_dir.mkdir(parents=True)
    log_path = live_dir / "run1.jsonl"
    log_path.write_text('{"message": "a"}\n{"message": "b"}\n{"message": "c"}\n', encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))

    res = mcp_server.tail_log("live", "run1", lines=2)
    assert res == ["b", "c"]


def test_portfolio_status_reads_state(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    state_dir = archive / "portfolio" / "demo"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    state_path.write_text(json.dumps({"cash": 123}), encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))

    res = mcp_server.portfolio_status("demo")
    assert res["state"]["cash"] == 123
    assert res["paths"]["state"].endswith("state.json")


def test_ft_command_str_runs(monkeypatch):
    calls = {}

    def fake_run(cmd, capture_output=True, text=True):
        calls["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)
    res = mcp_server.ft_command_str("assets")

    assert res["returncode"] == 0
    assert "fast_trade.cli" in " ".join(res["command"].split())
    assert calls["cmd"][0].endswith("python") or "python" in calls["cmd"][0]


def test_fxmacrodata_macro_context_forwards_arguments(monkeypatch):
    captured = {}

    def fake_build_macro_context(**kwargs):
        captured.update(kwargs)
        return {"base_calendar": {"data": []}}

    monkeypatch.setattr(mcp_server, "build_macro_context", fake_build_macro_context)

    result = mcp_server.fxmacrodata_macro_context("EUR", "USD", "inflation", limit=5)

    assert result == {"base_calendar": {"data": []}}
    assert captured == {"base": "EUR", "quote": "USD", "indicator": "inflation", "limit": 5}


def test_list_strategies_missing_dir(monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", "/does/not/exist")
    assert mcp_server.list_strategies() == []


def test_list_assets(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_assets", lambda exchange="local": [("coinbase", "BTC-USD"), "ETH-USD"])
    assert mcp_server.list_assets("coinbase") == ["coinbase:BTC-USD", "ETH-USD"]


def test_backtest_builds_cli_args(monkeypatch):
    captured = {}

    def fake_run(args):
        captured["args"] = args
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(args)}

    monkeypatch.setattr(mcp_server, "_run_ft", fake_run)
    mcp_server.backtest("strategy.yml", save=True, save_all=True, plot=True, mods=["a=1"])
    assert captured["args"] == [
        "backtest",
        "strategy.yml",
        "--save",
        "--all",
        "--plot",
        "--mods",
        "a=1",
    ]


def test_portfolio_start_and_stop(monkeypatch):
    captured = []

    def fake_run(args):
        captured.append(args)
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(args)}

    monkeypatch.setattr(mcp_server, "_run_ft", fake_run)
    mcp_server.portfolio_start("s.yml", symbol="ETH-USD", name="demo", cash=100.0, daemon=False)
    assert captured[0] == [
        "portfolio",
        "start",
        "s.yml",
        "--symbol",
        "ETH-USD",
        "--name",
        "demo",
        "--cash",
        "100.0",
        "--no-daemon",
    ]
    mcp_server.portfolio_stop("demo")
    assert captured[1] == ["portfolio", "stop", "demo"]


def test_ft_command_forwards(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "_run_ft",
        lambda args: {"returncode": 0, "stdout": "ok", "stderr": "", "command": "x"},
    )
    assert mcp_server.ft_command(["-h"])["stdout"] == "ok"


@pytest.mark.parametrize(
    "kind,subdir,filename,legacy_name",
    [
        ("live", "live_logs", "run1.jsonl", "run1.log"),
        ("stream", "stream_logs", "run1.jsonl", "run1.log"),
        ("portfolio", "portfolio/demo", "portfolio.jsonl", "portfolio.log"),
    ],
)
def test_tail_log_formats(tmp_path, monkeypatch, kind, subdir, filename, legacy_name):
    archive = tmp_path / "ft_archive"
    log_dir = archive / subdir
    log_dir.mkdir(parents=True)
    log_path = log_dir / filename
    log_path.write_text(
        '{"line": "line-msg"}\n{"message": "message-msg"}\n{"event": {"x": 1}}\nplain\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))
    res = mcp_server.tail_log(kind, "demo" if kind == "portfolio" else "run1", lines=10)
    assert "line-msg" in res
    assert "message-msg" in res
    assert '"x": 1' in res[-2] or '"x": 1' in res[-1]
    assert "plain" in res


def test_tail_log_json_payload_fallback(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    live_dir = archive / "live_logs"
    live_dir.mkdir(parents=True)
    log_path = live_dir / "run1.jsonl"
    log_path.write_text('{"foo": 1}\n', encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))
    res = mcp_server.tail_log("live", "run1", lines=1)
    assert '"foo": 1' in res[0]


def test_tail_log_legacy_and_missing(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    live_dir = archive / "live_logs"
    live_dir.mkdir(parents=True)
    legacy = live_dir / "run1.log"
    legacy.write_text("legacy-line\n", encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))
    assert mcp_server.tail_log("live", "run1") == ["legacy-line"]
    assert mcp_server.tail_log("live", "missing")[0].startswith("Log not found:")
    assert mcp_server.tail_log("unknown", "x") == ["Unknown kind: unknown"]


def test_version_resource(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('name = "fast-trade"\nversion = "9.9.9"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    fn = getattr(mcp_server.version_resource, "fn", mcp_server.version_resource)
    assert fn() == "9.9.9"
    pyproject.write_text("broken", encoding="utf-8")
    assert fn() == "unknown"


def test_dummy_mcp():
    dummy = mcp_server._DummyMCP()

    @dummy.tool
    def sample_tool():
        return "ok"

    @dummy.resource("demo")
    def sample_resource():
        return "resource"

    assert sample_tool() == "ok"
    assert sample_resource() == "resource"
    with pytest.raises(RuntimeError, match="fastmcp is not installed"):
        dummy.run()


def test_main_registers_tools(monkeypatch):
    registered = {"tools": [], "ran": False}

    class FakeMCP:
        def tool(self, fn):
            registered["tools"].append(fn.__name__)
            return fn

        def run(self):
            registered["ran"] = True

    monkeypatch.setattr(mcp_server, "mcp", FakeMCP())
    mcp_server.main()
    assert registered["ran"] is True
    assert "backtest" in registered["tools"]


def test_version_resource_open_failure(monkeypatch):
    def broken_open(*args, **kwargs):
        raise OSError("cannot open")

    monkeypatch.setattr("builtins.open", broken_open)
    fn = getattr(mcp_server.version_resource, "fn", mcp_server.version_resource)
    assert fn() == "unknown"


def test_portfolio_start_default_daemon(monkeypatch):
    captured = []

    def fake_run(args):
        captured.append(args)
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(args)}

    monkeypatch.setattr(mcp_server, "_run_ft", fake_run)
    mcp_server.portfolio_start("s.yml")
    assert "--daemon" in captured[0]


def test_mcp_main_block(monkeypatch):
    import sys
    from types import ModuleType

    fake_fastmcp = ModuleType("fastmcp")

    class FakeFastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self, fn):
            return fn

        def resource(self, _name):
            def decorator(fn):
                return fn

            return decorator

        def run(self):
            return None

    fake_fastmcp.FastMCP = FakeFastMCP
    monkeypatch.setitem(sys.modules, "fastmcp", fake_fastmcp)

    namespace = {"__name__": "__main__", "__file__": mcp_server.__file__}
    with open(mcp_server.__file__, encoding="utf-8") as handle:
        exec(compile(handle.read(), mcp_server.__file__, "exec"), namespace)
