import json
import os
import shlex
import subprocess
import sys
from typing import List, Optional

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover - fallback for environments without fastmcp
    FastMCP = None


class _DummyMCP:
    def __init__(self, *_args, **_kwargs):
        pass

    def tool(self, fn):
        return fn

    def resource(self, _name):
        def decorator(fn):
            return fn

        return decorator

    def run(self):
        raise RuntimeError("fastmcp is not installed")

from fast_trade.archive.cli import get_assets
from fast_trade.portfolio import load_state, portfolio_paths

mcp = FastMCP("fast-trade") if FastMCP is not None else _DummyMCP()


def _run_ft(args: List[str]) -> dict:
    cmd = [sys.executable, "-m", "fast_trade.cli"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": " ".join(cmd),
    }


def ft_command(args: List[str]) -> dict:
    """Run any `ft` CLI command with argument list."""
    return _run_ft(args)


def ft_command_str(command: str) -> dict:
    """Run any `ft` CLI command as a single string."""
    args = shlex.split(command)
    return _run_ft(args)


def list_strategies() -> List[str]:
    """List available strategy files under ft_archive/strategies."""
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    strategy_dir = os.path.join(archive_path, "strategies")
    if not os.path.isdir(strategy_dir):
        return []
    items = []
    for name in os.listdir(strategy_dir):
        if name.startswith("."):
            continue
        if name.endswith((".yml", ".yaml")):
            items.append(os.path.join(strategy_dir, name))
    return sorted(items)


def list_assets(exchange: str = "local") -> List[str]:
    """List assets from an exchange or local archive."""
    assets = get_assets(exchange=exchange)
    # get_assets may return tuples for local assets
    out = []
    for item in assets:
        if isinstance(item, tuple):
            out.append(f"{item[0]}:{item[1]}")
        else:
            out.append(str(item))
    return out


def backtest(
    strategy_path: str,
    save: bool = False,
    save_all: bool = False,
    plot: bool = False,
    mods: Optional[List[str]] = None,
) -> dict:
    """Run a backtest using the CLI."""
    args = ["backtest", strategy_path]
    if save:
        args.append("--save")
    if save_all:
        args.append("--all")
    if plot:
        args.append("--plot")
    if mods:
        args += ["--mods"] + mods
    return _run_ft(args)


def portfolio_start(
    strategy_path: str,
    symbol: str = "BTC-USD",
    name: Optional[str] = None,
    cash: Optional[float] = None,
    daemon: bool = True,
) -> dict:
    """Start a paper portfolio runner."""
    args = ["portfolio", "start", strategy_path, "--symbol", symbol]
    if name:
        args += ["--name", name]
    if cash is not None:
        args += ["--cash", str(cash)]
    if daemon:
        args.append("--daemon")
    else:
        args.append("--no-daemon")
    return _run_ft(args)


def portfolio_stop(name: str) -> dict:
    """Stop a running portfolio."""
    return _run_ft(["portfolio", "stop", name])


def portfolio_status(name: str) -> dict:
    """Read portfolio state from disk."""
    paths = portfolio_paths(name)
    state = load_state(paths["state"], {})
    return {"state": state, "paths": paths}


def tail_log(kind: str, identifier: str, lines: int = 200) -> List[str]:
    """Tail a log file. kind = live|stream|portfolio."""
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    if kind == "live":
        path = os.path.join(archive_path, "live_logs", f"{identifier}.jsonl")
        legacy = os.path.join(archive_path, "live_logs", f"{identifier}.log")
    elif kind == "stream":
        path = os.path.join(archive_path, "stream_logs", f"{identifier}.jsonl")
        legacy = os.path.join(archive_path, "stream_logs", f"{identifier}.log")
    elif kind == "portfolio":
        path = os.path.join(archive_path, "portfolio", identifier, "portfolio.jsonl")
        legacy = os.path.join(archive_path, "portfolio", identifier, "portfolio.log")
    else:
        return [f"Unknown kind: {kind}"]
    read_path = path if os.path.exists(path) else legacy
    if not os.path.exists(read_path):
        return [f"Log not found: {path}"]

    def _format_line(raw: str) -> str:
        try:
            payload = json.loads(raw)
        except Exception:
            return raw.rstrip("\n")
        if isinstance(payload, dict):
            if "line" in payload:
                return str(payload.get("line"))
            if "message" in payload:
                return str(payload.get("message"))
            if "event" in payload:
                return json.dumps(payload.get("event"), ensure_ascii=False)
        return json.dumps(payload, ensure_ascii=False)

    with open(read_path, "r", encoding="utf-8", errors="ignore") as fh:
        data = [_format_line(line) for line in fh.read().splitlines()[-lines:]]
    return data


@mcp.resource("fast-trade://version")
def version_resource() -> str:
    """Return package version from pyproject."""
    try:
        with open("pyproject.toml", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "unknown"


def main() -> None:
    # Register tools only when running the server
    mcp.tool(ft_command)
    mcp.tool(ft_command_str)
    mcp.tool(list_strategies)
    mcp.tool(list_assets)
    mcp.tool(backtest)
    mcp.tool(portfolio_start)
    mcp.tool(portfolio_stop)
    mcp.tool(portfolio_status)
    mcp.tool(tail_log)
    mcp.run()


if __name__ == "__main__":
    main()
