import json
import os
from types import SimpleNamespace

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
