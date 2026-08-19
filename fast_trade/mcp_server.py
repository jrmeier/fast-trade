import json
import os
import shlex
import subprocess
import sys
from typing import List, Optional

from fast_trade.archive.cli import get_assets
from fast_trade.fxmacrodata import build_macro_context
from fast_trade.portfolio import load_state, portfolio_paths

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


def _run_ft_cli(*args: str) -> dict:
    """Run an `ft` subcommand with interactive prompts disabled."""
    return _run_ft(["--no-interactive", *args])


def ft_command(args: List[str]) -> dict:
    """Run any `ft` CLI command with argument list."""
    return _run_ft(["--no-interactive", *args])


def ft_command_str(command: str) -> dict:
    """Run any `ft` CLI command as a single string."""
    args = shlex.split(command)
    return _run_ft(["--no-interactive", *args])


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


def download(
    symbol: str,
    exchange: str = "binanceus",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict:
    """Download archive candles via `ft download`."""
    args = ["download", symbol, exchange]
    if start:
        args += ["--start", start]
    if end:
        args += ["--end", end]
    return _run_ft_cli(*args)


def assets(exchange: str = "local") -> dict:
    """List assets via `ft assets`."""
    return _run_ft_cli("assets", "--exchange", exchange)


def list_assets(exchange: str = "local") -> List[str]:
    """List assets from an exchange or local archive (direct helper)."""
    asset_list = get_assets(exchange=exchange)
    out = []
    for item in asset_list:
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
    live: bool = False,
    details: bool = False,
    show_strategy: bool = False,
    preview: bool = True,
    mods: Optional[List[str]] = None,
) -> dict:
    """Run a backtest using `ft backtest`."""
    args = ["backtest", strategy_path]
    if save:
        args.append("--save")
    else:
        args.append("--no-save")
    if save_all:
        args.append("--all")
    if plot:
        args.append("--plot")
    if live:
        args.append("--live")
    if details:
        args.append("--details")
    if show_strategy:
        args.append("--show-strategy")
    if not preview:
        args.append("--no-preview")
    if mods:
        args += ["--mods"] + mods
    return _run_ft_cli(*args)


def backtests(
    action: str = "list",
    run_id: Optional[str] = None,
    limit: int = 10,
    last: int = 0,
    index: Optional[int] = None,
) -> dict:
    """Browse saved backtests via `ft backtests`."""
    args = ["backtests", action]
    if run_id:
        args.append(run_id)
    if limit != 10:
        args += ["--limit", str(limit)]
    if last:
        args += ["--last", str(last)]
    if index is not None:
        args += ["--index", str(index)]
    return _run_ft_cli(*args)


def migrate_backtests(limit: int = 0) -> dict:
    """Migrate saved backtests via `ft migrate_backtests`."""
    args = ["migrate_backtests"]
    if limit:
        args += ["--limit", str(limit)]
    return _run_ft_cli(*args)


def migrate_archive(limit: int = 0) -> dict:
    """Migrate archive sqlite files via `ft migrate_archive`."""
    args = ["migrate_archive"]
    if limit:
        args += ["--limit", str(limit)]
    return _run_ft_cli(*args)


def regime_train(
    config: str,
    data_path: str,
    out: str = "regime_model.pkl",
) -> dict:
    """Train a regime model via `ft regime_train`."""
    return _run_ft_cli("regime_train", config, data_path, "--out", out)


def regime_apply(
    model_path: str,
    data_path: str,
    out: str = "regime_output.csv",
) -> dict:
    """Apply a regime model via `ft regime_apply`."""
    return _run_ft_cli("regime_apply", model_path, data_path, "--out", out)


def validate(strategy_path: str, mods: Optional[List[str]] = None) -> dict:
    """Validate a strategy via `ft validate`."""
    args = ["validate", strategy_path]
    if mods:
        args += ["--mods"] + mods
    return _run_ft_cli(*args)


def logs(
    name: str,
    follow: bool = False,
    tail: int = 200,
) -> dict:
    """Tail portfolio logs via `ft logs`."""
    args = ["logs", "--name", name, "--tail", str(tail)]
    if follow:
        args.append("--follow")
    else:
        args.append("--no-follow")
    return _run_ft_cli(*args)


def update_archive() -> dict:
    """Update archive candles via `ft update_archive`."""
    return _run_ft_cli("update_archive")


def evolve(config: str) -> dict:
    """Run genetic-algorithm strategy evolution via `ft evolve`."""
    return _run_ft_cli("evolve", config)


def portfolio_start(
    strategy_path: str,
    symbol: str = "BTC-USD",
    name: Optional[str] = None,
    cash: Optional[float] = None,
    paper: bool = True,
    once: bool = False,
    daemon: bool = True,
) -> dict:
    """Start a paper portfolio via `ft portfolio start`."""
    args = ["portfolio", "start", strategy_path, "--symbol", symbol]
    if name:
        args += ["--name", name]
    if cash is not None:
        args += ["--cash", str(cash)]
    if paper:
        args.append("--paper")
    else:
        args.append("--no-paper")
    if once:
        args.append("--once")
    if daemon:
        args.append("--daemon")
    else:
        args.append("--no-daemon")
    return _run_ft_cli(*args)


def portfolio_stop(name: str) -> dict:
    """Stop a running portfolio via `ft portfolio stop`."""
    return _run_ft_cli("portfolio", "stop", name)


def portfolio_status(name: str) -> dict:
    """Show portfolio status via `ft portfolio status`."""
    return _run_ft_cli("portfolio", "status", name)


def portfolio_state(name: str) -> dict:
    """Read portfolio state JSON directly from disk."""
    paths = portfolio_paths(name)
    state = load_state(paths["state"], {})
    return {"state": state, "paths": paths}


def screen_hmm(
    config: Optional[str] = None,
    exchange: str = "coinbase",
    symbols: Optional[List[str]] = None,
    live: bool = False,
    lookback_days: int = 260,
    horizons: Optional[List[int]] = None,
    states: int = 3,
    simulations: int = 5000,
    seed: int = 42,
    max_products: int = 40,
    json_out: Optional[str] = None,
    md_out: Optional[str] = None,
) -> dict:
    """Run an HMM forecast screen via `ft screen hmm`."""
    args = ["screen", "hmm"]
    if config:
        args.append(config)
    args += ["--exchange", exchange]
    if symbols:
        for symbol in symbols:
            args += ["--symbol", symbol]
    if live:
        args.append("--live")
    else:
        args.append("--archive")
    args += [
        "--lookback-days",
        str(lookback_days),
        "--states",
        str(states),
        "--simulations",
        str(simulations),
        "--seed",
        str(seed),
        "--max-products",
        str(max_products),
    ]
    if horizons:
        for horizon in horizons:
            args += ["--horizon", str(horizon)]
    if json_out:
        args += ["--json-out", json_out]
    if md_out:
        args += ["--md-out", md_out]
    return _run_ft_cli(*args)


def tail_log(name: str, lines: int = 200) -> List[str]:
    """Tail a portfolio JSONL log."""
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    path = os.path.join(archive_path, "portfolio", name, "portfolio.jsonl")
    legacy = os.path.join(archive_path, "portfolio", name, "portfolio.log")
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


def fxmacrodata_macro_context(
    base: str,
    quote: str = "usd",
    indicator: str = "policy_rate",
    limit: int = 10,
) -> dict:
    """Fetch FXMacroData macro context for an FX pair."""
    return build_macro_context(
        base=base,
        quote=quote,
        indicator=indicator,
        limit=limit,
    )


def hmm_screen(
    exchange: str = "coinbase",
    symbols: Optional[List[str]] = None,
    live: bool = False,
    lookback_days: int = 260,
    horizons: Optional[List[int]] = None,
    states: int = 3,
    simulations: int = 500,
    seed: int = 42,
    max_products: int = 20,
) -> dict:
    """Run an HMM forecast screen and return ranked JSON results."""
    from fast_trade.ml.hmm_data import screen_from_config

    config = {
        "exchange": exchange,
        "symbols": list(symbols or []),
        "live": live,
        "settings": {
            "lookback_days": lookback_days,
            "horizons": horizons or [7, 30, 60],
            "states": states,
            "simulations": simulations,
            "seed": seed,
            "max_products": max_products,
        },
    }
    return screen_from_config(config)


CLI_PARITY_TOOLS = [
    "download",
    "assets",
    "backtest",
    "backtests",
    "migrate_backtests",
    "migrate_archive",
    "regime_train",
    "regime_apply",
    "validate",
    "logs",
    "update_archive",
    "evolve",
    "portfolio_start",
    "portfolio_stop",
    "portfolio_status",
    "screen_hmm",
]


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


def _register_tool(fn):
    return mcp.tool(fn)


def main() -> None:
    _register_tool(ft_command)
    _register_tool(ft_command_str)
    _register_tool(list_strategies)
    _register_tool(list_assets)
    for name in CLI_PARITY_TOOLS:
        _register_tool(globals()[name])
    _register_tool(portfolio_state)
    _register_tool(tail_log)
    _register_tool(fxmacrodata_macro_context)
    _register_tool(hmm_screen)
    mcp.run()


if __name__ == "__main__":
    main()
