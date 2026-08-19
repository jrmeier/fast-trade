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
    log_dir = archive / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "portfolio.jsonl"
    log_path.write_text('{"message": "a"}\n{"message": "b"}\n{"message": "c"}\n', encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))

    res = mcp_server.tail_log("demo", lines=2)
    assert res == ["b", "c"]


def test_portfolio_status_reads_state(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    state_dir = archive / "portfolio" / "demo"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    state_path.write_text(json.dumps({"cash": 123}), encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))

    res = mcp_server.portfolio_state("demo")
    assert res["state"]["cash"] == 123
    assert res["paths"]["state"].endswith("state.json")


def test_portfolio_status_uses_cli(monkeypatch):
    captured = {}

    def fake_run(*cli_args):
        captured["args"] = list(cli_args)
        return {"returncode": 0, "stdout": "ok", "stderr": "", "command": " ".join(cli_args)}

    monkeypatch.setattr(mcp_server, "_run_ft_cli", fake_run)
    res = mcp_server.portfolio_status("demo")
    assert res["stdout"] == "ok"
    assert captured["args"] == ["portfolio", "status", "demo"]


def test_ft_command_str_runs(monkeypatch):
    calls = {}

    def fake_run(cmd, capture_output=True, text=True):
        calls["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)
    res = mcp_server.ft_command_str("assets")

    assert res["returncode"] == 0
    assert calls["cmd"][0].endswith("python") or "python" in calls["cmd"][0]
    assert "--no-interactive" in calls["cmd"]


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


def test_assets_uses_cli(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "_run_ft_cli",
        lambda *args: {"returncode": 0, "stdout": "assets", "stderr": "", "command": " ".join(args)},
    )
    assert mcp_server.assets("coinbase")["stdout"] == "assets"


@pytest.mark.parametrize(
    "tool_name,args,expected",
    [
        ("download", ("BTCUSDT", "binanceus"), ["download", "BTCUSDT", "binanceus"]),
        ("backtests", (), ["backtests", "list"]),
        ("migrate_backtests", (), ["migrate_backtests"]),
        ("migrate_archive", (), ["migrate_archive"]),
        ("regime_train", ("cfg.yml", "data.csv"), ["regime_train", "cfg.yml", "data.csv", "--out", "regime_model.pkl"]),
        ("regime_apply", ("model.pkl", "data.csv"), ["regime_apply", "model.pkl", "data.csv", "--out", "regime_output.csv"]),
        ("validate", ("strategy.yml",), ["validate", "strategy.yml"]),
        ("update_archive", (), ["update_archive"]),
        ("evolve", ("evolver.yml",), ["evolve", "evolver.yml"]),
        (
            "screen_hmm",
            (),
            [
                "screen",
                "hmm",
                "--exchange",
                "coinbase",
                "--archive",
                "--lookback-days",
                "260",
                "--states",
                "3",
                "--simulations",
                "5000",
                "--seed",
                "42",
                "--max-products",
                "40",
            ],
        ),
    ],
)
def test_cli_parity_tools(monkeypatch, tool_name, args, expected):
    captured = {}

    def fake_run(*cli_args):
        captured["args"] = list(cli_args)
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cli_args)}

    monkeypatch.setattr(mcp_server, "_run_ft_cli", fake_run)
    getattr(mcp_server, tool_name)(*args)
    assert captured["args"] == expected


def test_logs_builds_cli_args(monkeypatch):
    captured = {}

    def fake_run(*cli_args):
        captured["args"] = list(cli_args)
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cli_args)}

    monkeypatch.setattr(mcp_server, "_run_ft_cli", fake_run)
    mcp_server.logs(name="demo", follow=True, tail=50)
    assert captured["args"] == [
        "logs",
        "--name",
        "demo",
        "--tail",
        "50",
        "--follow",
    ]


def test_cli_wrapper_optional_args(monkeypatch):
    captured = []

    def fake_run(*cli_args):
        captured.append(list(cli_args))
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cli_args)}

    monkeypatch.setattr(mcp_server, "_run_ft_cli", fake_run)

    mcp_server.download("BTCUSDT", start="2024-01-01", end="2024-02-01")
    mcp_server.backtest(
        "strategy.yml",
        live=True,
        details=True,
        show_strategy=True,
        preview=False,
        mods=["freq", "1H"],
    )
    mcp_server.backtests("show", run_id="run1", limit=5, last=2, index=3)
    mcp_server.migrate_backtests(limit=3)
    mcp_server.migrate_archive(limit=2)
    mcp_server.validate("strategy.yml", mods=["x", "1"])
    mcp_server.portfolio_start("s.yml", paper=False, once=True, daemon=False)
    mcp_server.screen_hmm(
        config="screen.yml",
        symbols=["BTC-USD"],
        live=True,
        horizons=[7, 30],
        json_out="out.json",
        md_out="out.md",
    )

    assert captured[0] == ["download", "BTCUSDT", "binanceus", "--start", "2024-01-01", "--end", "2024-02-01"]
    assert captured[1] == [
        "backtest",
        "strategy.yml",
        "--no-save",
        "--live",
        "--details",
        "--show-strategy",
        "--no-preview",
        "--mods",
        "freq",
        "1H",
    ]
    assert captured[2] == ["backtests", "show", "run1", "--limit", "5", "--last", "2", "--index", "3"]
    assert captured[3] == ["migrate_backtests", "--limit", "3"]
    assert captured[4] == ["migrate_archive", "--limit", "2"]
    assert captured[5] == ["validate", "strategy.yml", "--mods", "x", "1"]
    assert captured[6] == [
        "portfolio",
        "start",
        "s.yml",
        "--symbol",
        "BTC-USD",
        "--no-paper",
        "--once",
        "--no-daemon",
    ]
    assert captured[7][:3] == ["screen", "hmm", "screen.yml"]
    assert "--live" in captured[7]
    assert "--symbol" in captured[7]
    assert "--json-out" in captured[7]
    assert "--md-out" in captured[7]

    captured.clear()
    mcp_server.logs(name="demo", follow=False)
    assert captured[0] == ["logs", "--name", "demo", "--tail", "200", "--no-follow"]


def test_backtest_builds_cli_args(monkeypatch):
    captured = {}

    def fake_run(args):
        captured["args"] = args
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(args)}

    monkeypatch.setattr(mcp_server, "_run_ft", fake_run)
    mcp_server.backtest("strategy.yml", save=True, save_all=True, plot=True, mods=["a=1"])
    assert captured["args"] == [
        "--no-interactive",
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
        "--no-interactive",
        "portfolio",
        "start",
        "s.yml",
        "--symbol",
        "ETH-USD",
        "--name",
        "demo",
        "--cash",
        "100.0",
        "--paper",
        "--no-daemon",
    ]
    mcp_server.portfolio_stop("demo")
    assert captured[1] == ["--no-interactive", "portfolio", "stop", "demo"]


def test_ft_command_forwards(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "_run_ft",
        lambda args: {"returncode": 0, "stdout": "ok", "stderr": "", "command": "x"},
    )
    assert mcp_server.ft_command(["-h"])["stdout"] == "ok"


def test_tail_log_formats(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    log_dir = archive / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "portfolio.jsonl"
    log_path.write_text(
        '{"line": "line-msg"}\n{"message": "message-msg"}\n{"event": {"x": 1}}\nplain\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))
    res = mcp_server.tail_log("demo", lines=10)
    assert "line-msg" in res
    assert "message-msg" in res
    assert '"x": 1' in res[-2] or '"x": 1' in res[-1]
    assert "plain" in res


def test_tail_log_json_payload_fallback(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    log_dir = archive / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "portfolio.jsonl"
    log_path.write_text('{"foo": 1}\n', encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))
    res = mcp_server.tail_log("demo", lines=1)
    assert '"foo": 1' in res[0]


def test_tail_log_legacy_and_missing(tmp_path, monkeypatch):
    archive = tmp_path / "ft_archive"
    log_dir = archive / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    legacy = log_dir / "portfolio.log"
    legacy.write_text("legacy-line\n", encoding="utf-8")
    monkeypatch.setenv("ARCHIVE_PATH", str(archive))
    assert mcp_server.tail_log("demo") == ["legacy-line"]
    assert mcp_server.tail_log("missing")[0].startswith("Log not found:")


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
    for name in mcp_server.CLI_PARITY_TOOLS:
        assert name in registered["tools"]
    assert "hmm_screen" in registered["tools"]
    assert "portfolio_state" in registered["tools"]


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
    assert captured[0][:2] == ["--no-interactive", "portfolio"]
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
