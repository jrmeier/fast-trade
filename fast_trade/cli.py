import datetime
import json
import os
import sys
import time
import subprocess
import signal
from pprint import pprint
from typing import Dict, List, Optional

import pandas as pd
import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.live import Live
from rich.table import Table

from fast_trade.archive.cli import download_asset, get_assets
from fast_trade.archive.db_helpers import connect_to_db, migrate_sqlite_to_parquet
from fast_trade.archive.update_archive import update_archive
from fast_trade.archive.update_kline import update_kline
from fast_trade.ml.evolver import optimize_strategy
from fast_trade.ml.regime import apply_regime_model, load_regime_model, train_regime_model, save_regime_model
from fast_trade.validate_backtest import validate_backtest
from fast_trade.build_data_frame import prepare_df
from fast_trade.run_backtest import compile_action_logic, determine_action_compiled
from fast_trade.cli_render import format_value as _format_value
from fast_trade.cli_render import render_kv_table as _render_kv_table
from fast_trade.cli_render import render_summary as _render_summary
from fast_trade.portfolio import (
    append_log as _append_portfolio_log,
    append_trades as _append_portfolio_trades,
    apply_action as _apply_portfolio_action,
    load_state as _load_portfolio_state,
    portfolio_paths as _portfolio_paths,
    save_state as _save_portfolio_state,
)

from .cli_helpers import (
    _load_json_or_yaml,
    create_plot,
    open_strat_file,
    render_plot_preview_from_data,
    save,
)
from .run_backtest import run_backtest

app = typer.Typer(help="Fast Trade CLI", add_completion=False)
portfolio_app = typer.Typer(help="Paper portfolio runner")
screen_app = typer.Typer(help="Market screening tools")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(screen_app, name="screen")
console = Console()

EXCHANGE_CHOICES = ["binancecom", "binanceus", "coinbase"]
ASSET_EXCHANGE_CHOICES = ["local", "binanceus", "binancecom", "coinbase"]
SCREEN_EXCHANGE_CHOICES = ["coinbase", "binanceus", "binancecom", "hyperliquid"]


def _apply_mods(strategy: Dict, mods: Optional[List[str]]) -> Dict:
    if not mods:
        return strategy

    if len(mods) % 2 != 0:
        raise typer.BadParameter("--mods must be key/value pairs: --mods freq 1H trailing_stop_loss 0.05")

    overrides: Dict[str, str] = {}
    i = 0
    while i < len(mods):
        overrides[mods[i]] = mods[i + 1]
        i += 2

    return {**strategy, **overrides}


def _format_log_line(raw: str) -> str:
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


@app.command()
def download(
    symbol: str = typer.Argument(..., help="Symbol to download"),
    exchange: str = typer.Argument(
        "binanceus",
        help="Exchange to download data from",
        show_default=True,
    ),
    start: str = typer.Option(
        None,
        "--start",
        help="Start date (ISO format). Defaults to 30 days ago.",
    ),
    end: str = typer.Option(
        None,
        "--end",
        help="End date (ISO format). Defaults to now.",
    ),
):
    if exchange not in EXCHANGE_CHOICES:
        raise typer.BadParameter(f"exchange must be one of {EXCHANGE_CHOICES}")

    if start is None:
        start = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
    if end is None:
        end = datetime.datetime.now(datetime.timezone.utc).isoformat()

    console.print(Panel.fit(f"Downloading [bold]{symbol}[/bold] from [bold]{exchange}[/bold]", style="blue"))
    console.print(f"[cyan]Range[/cyan] {start} → {end}")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )

    with progress:
        task = progress.add_task("Fetching klines", total=100)

        def update_progress(status_obj):
            perc = status_obj.get("perc_complete", 0)
            calls = status_obj.get("call_count")
            total_calls = status_obj.get("total_calls")
            desc = "Fetching klines"
            if calls is not None and total_calls is not None:
                desc = f"Fetching klines ({calls}/{total_calls})"
            try:
                completed = float(perc)
            except (TypeError, ValueError):
                completed = 0
            progress.update(task, completed=completed, description=desc)

        db_path = download_asset(
            symbol=symbol,
            exchange=exchange,
            start=start,
            end=end,
            progress_callback=update_progress,
        )

    console.print(f"[green]Downloaded[/green] to [bold]{db_path}[/bold]")


@app.command()
def assets(
    exchange: str = typer.Option(
        "local",
        "--exchange",
        help="Exchange to list assets from",
        show_default=True,
    )
):
    if exchange not in ASSET_EXCHANGE_CHOICES:
        raise typer.BadParameter(f"exchange must be one of {ASSET_EXCHANGE_CHOICES}")

    with console.status("Loading assets...", spinner="dots"):
        assets_list = get_assets(exchange=exchange)

    table = Table(title=f"Assets ({exchange})", box=box.SIMPLE_HEAVY)
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Asset", style="white")

    for idx, asset in enumerate(assets_list, start=1):
        table.add_row(str(idx), str(asset))

    console.print(table)


@app.command()
def backtest(
    ctx: typer.Context,
    strategy: str = typer.Argument(..., help="Path or URL to strategy JSON"),
    mods: Optional[List[str]] = typer.Option(
        None, "--mods", help="Modifiers for strategy/backtest (key value pairs)",
    ),
    save_results: bool = typer.Option(
        False, "--save/--no-save", help="Save backtest results to archive",
    ),
    save_all: bool = typer.Option(
        False, "--all", help="Save full dataframes and trade logs",
    ),
    preview: bool = typer.Option(
        True, "--preview/--no-preview", help="Show a terminal preview of the saved plot",
    ),
    plot: bool = typer.Option(
        False, "--plot", help="Plot backtest results",
    ),
    live: bool = typer.Option(
        False, "--live", help="Refresh market data to the latest before backtest",
    ),
    details: bool = typer.Option(
        False, "--details", help="Show detailed metric sections",
    ),
    show_strategy: bool = typer.Option(
        False, "--show-strategy", help="Include strategy details in output",
    ),
):
    if strategy.endswith((".yml", ".yaml")):
        console.print("[yellow]YAML is supported but JSON is the default format[/yellow]")
    console.print(Panel.fit("Running backtest", style="magenta"))

    console.print("[cyan]Loading strategy[/cyan]")
    strat_obj = open_strat_file(strategy)
    strat_obj = _apply_mods(strat_obj, mods)

    console.print("[cyan]Executing backtest[/cyan]")
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    with progress:
        data_task = progress.add_task("Loading data", total=None)
        actions_task = progress.add_task("Processing actions", total=100)
        simulation_task = progress.add_task("Simulating trades", total=100)
        data_seen = {"value": False}

        def progress_callback(payload):
            phase = payload.get("phase")
            percent = payload.get("percent", 0)
            if phase == "data":
                if not data_seen["value"]:
                    progress.update(data_task, total=100)
                    data_seen["value"] = True
                progress.update(data_task, completed=percent)
            elif phase == "actions":
                progress.update(actions_task, completed=percent)
            elif phase == "simulation":
                progress.update(simulation_task, completed=percent)

        if live:
            console.print("[cyan]Refreshing market data[/cyan]")
            symbol = strat_obj.get("symbol")
            exchange = strat_obj.get("exchange")
            if not symbol or not exchange:
                raise typer.BadParameter("--live requires symbol and exchange in the strategy")
            now = datetime.datetime.now(datetime.timezone.utc)
            start_val = None
            archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
            db_path = os.path.join(archive_path, exchange, f"{symbol}.parquet")
            if os.path.exists(db_path):
                try:
                    df = pd.read_parquet(db_path)
                    if "date" in df.columns:
                        df = df.set_index("date")
                    df.index = pd.to_datetime(df.index)
                    latest = df.index.max()
                    if latest:
                        start_val = latest
                except Exception:
                    start_val = None
            if not start_val:
                start_val = strat_obj.get("start")
                if isinstance(start_val, str):
                    try:
                        start_val = datetime.datetime.fromisoformat(start_val)
                    except ValueError:
                        start_val = None
            if isinstance(start_val, datetime.datetime) and start_val.tzinfo is None:
                start_val = start_val.replace(tzinfo=datetime.timezone.utc)
            if not isinstance(start_val, datetime.datetime):
                start_val = now - datetime.timedelta(days=30)
            strat_obj["stop"] = now.isoformat()

            progress.update(data_task, description="Refreshing market data", total=100, completed=0)

            def update_progress(status_obj):
                perc = status_obj.get("perc_complete", 0)
                try:
                    completed = float(perc)
                except (TypeError, ValueError):
                    completed = 0
                progress.update(data_task, completed=completed)
                data_seen["value"] = True

            if start_val >= now - datetime.timedelta(minutes=1):
                progress.update(
                    data_task,
                    description="Market data up to date",
                    completed=100,
                )
                data_seen["value"] = True
            else:
                update_kline(
                    symbol=symbol,
                    exchange=exchange,
                    start_date=start_val,
                    end_date=now,
                    progress_callback=update_progress,
                )
                progress.update(data_task, completed=100)

        result = run_backtest(strat_obj, progress_callback=progress_callback)
        if not data_seen["value"]:
            progress.update(data_task, description="Using provided data", total=100, completed=100)

    summary = result.get("summary", {})

    if save_results:
        console.print("[cyan]Saving results[/cyan]")
        with console.status("Saving results...", spinner="dots"):
            save_result = save(result, save_all=save_all)
        save_path = save_result["path"]
        console.print(f"[green]Saved[/green] backtest results to [bold]{save_path}[/bold]")
        if preview:
            console.print("[cyan]Plot preview[/cyan]")
            render_plot_preview_from_data(result.get("df"), result.get("trade_df"))
            if save_result["plot_format"] == "html":
                console.print(f"[yellow]PNG export unavailable. Saved HTML plot at {save_result['plot_path']}[/yellow]")

    if plot:
        console.print("[cyan]Rendering plot[/cyan]")
        with console.status("Rendering plot...", spinner="dots"):
            create_plot(result.get("df"), result.get("trade_df"), show=True)
        console.print("[green]Plot rendered[/green]")

    # convert seconds to minutes where present
    for key in ["mean_trade_len", "max_trade_held", "min_trade_len", "median_trade_len"]:
        try:
            summary[key] = summary.get(key) / 60
        except Exception:
            summary[key] = 0

    _render_summary(summary, details=details, show_strategy=show_strategy)
    if ctx.obj.get("interactive") and not details:
        if Confirm.ask("Show detailed metrics?", default=False):
            show_strat = Confirm.ask("Include strategy details?", default=False)
            _render_summary(summary, details=True, show_strategy=show_strat)


@app.command("backtests")
def backtests_cmd(
    ctx: typer.Context,
    action: str = typer.Argument("list", help="list, pick, show, or latest"),
    run_id: Optional[str] = typer.Argument(None, help="Run folder name when using show"),
    limit: int = typer.Option(10, "--limit", help="Limit number of results for list"),
    last: int = typer.Option(0, "--last", help="Show the last N runs (for list)"),
    index: Optional[int] = typer.Option(
        None, "--index", help="Show Nth most recent run (1 = latest)"
    ),
):
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    backtests_path = os.path.join(archive_path, "backtests")
    if not os.path.isdir(backtests_path):
        console.print("[red]No backtests directory found[/red]")
        raise typer.Exit(code=1)

    runs = sorted(os.listdir(backtests_path), reverse=True)
    runs = [r for r in runs if os.path.isdir(os.path.join(backtests_path, r))]

    def pick_from_runs(runs_to_pick):
        table = Table(title="Pick a Backtest", box=box.SIMPLE_HEAVY)
        table.add_column("#", style="cyan", no_wrap=True)
        table.add_column("Run ID", style="white")
        for idx, run in enumerate(runs_to_pick, start=1):
            table.add_row(str(idx), run)
        console.print(table)

        choice = IntPrompt.ask("Select run number", default=1)
        if choice < 1 or choice > len(runs_to_pick):
            console.print("[red]Selection out of range[/red]")
            raise typer.Exit(code=1)
        return runs_to_pick[choice - 1]

    if action == "list":
        if last > 0:
            runs = runs[:last]
        elif limit:
            runs = runs[:limit]
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        table = Table(title="Saved Backtests", box=box.SIMPLE_HEAVY)
        table.add_column("Run ID", style="cyan", no_wrap=True)
        table.add_column("Summary", style="white")
        with progress:
            task = progress.add_task("Loading summaries", total=len(runs))
            for run in runs:
                summary_text = ""
                try:
                    summary = _load_backtest_summary(os.path.join(backtests_path, run))
                    summary_text = (
                        f"return_perc={summary.get('return_perc', 0):.2f}, "
                        f"num_trades={summary.get('num_trades', 0)}"
                    )
                except Exception:
                    summary_text = "summary unreadable"
                table.add_row(run, summary_text)
                progress.update(task, advance=1)
        console.print(table)
        if ctx.obj.get("interactive") and runs:
            if Confirm.ask("Open a run?", default=False):
                selected_run = pick_from_runs(runs)
                action = "show"
                run_id = selected_run
            else:
                return
        else:
            return

    if action == "pick":
        if not ctx.obj.get("interactive"):
            console.print("[red]Interactive mode is not available in this shell[/red]")
            console.print("Use `ft backtests show --index N` instead.")
            raise typer.Exit(code=1)
        if not runs:
            console.print("[red]No saved backtests found[/red]")
            raise typer.Exit(code=1)
        if last > 0:
            runs = runs[:last]

        selected_run = pick_from_runs(runs)
        action = "show"
        run_id = selected_run

    if action in ["show", "latest"]:
        selected_run = run_id
        if action == "latest":
            if not runs:
                console.print("[red]No saved backtests found[/red]")
                raise typer.Exit(code=1)
            selected_run = runs[0]
        elif index is not None:
            if index < 1 or index > len(runs):
                console.print("[red]Index out of range[/red]")
                raise typer.Exit(code=1)
            selected_run = runs[index - 1]
        elif not selected_run:
            console.print("[red]Run ID, --index, or latest required[/red]")
            raise typer.Exit(code=1)

        run_path = os.path.join(backtests_path, selected_run)
        try:
            summary = _load_backtest_summary(run_path)
        except Exception:
            console.print("[red]summary.yml or summary.json not found for run[/red]")
            raise typer.Exit(code=1)
        console.print(Panel.fit(f"Backtest {selected_run}", style="blue"))
        _render_summary(summary, details=True, show_strategy=False)
        console.print(f"[green]Files[/green] {run_path}")
        return

    console.print("[red]Unknown action. Use list, pick, show, or latest.[/red]")
    raise typer.Exit(code=1)


@app.command("migrate_backtests")
def migrate_backtests_cmd(
    limit: int = typer.Option(0, "--limit", help="Limit number of backtests to migrate"),
):
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    backtests_path = os.path.join(archive_path, "backtests")
    if not os.path.isdir(backtests_path):
        console.print("[red]No backtests directory found[/red]")
        raise typer.Exit(code=1)

    runs = sorted(os.listdir(backtests_path), reverse=True)
    runs = [r for r in runs if os.path.isdir(os.path.join(backtests_path, r))]
    if limit and limit > 0:
        runs = runs[:limit]

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    with progress:
        task = progress.add_task("Migrating backtests", total=len(runs))
        for run in runs:
            run_path = os.path.join(backtests_path, run)
            df_db = os.path.join(run_path, "dataframe.db")
            trade_db = os.path.join(run_path, "trade_log.db")
            df_parquet = os.path.join(run_path, "dataframe.parquet")
            trade_parquet = os.path.join(run_path, "trade_log.parquet")
            summary_json = os.path.join(run_path, "summary.json")
            summary_yml = os.path.join(run_path, "summary.yml")

            try:
                if os.path.exists(df_db) and not os.path.exists(df_parquet):
                    con = connect_to_db(df_db)
                    df = pd.read_sql_query("SELECT * FROM dataframe", con)
                    if "date" in df.columns:
                        df = df.set_index("date")
                    df.to_parquet(df_parquet, index=True)
                if os.path.exists(trade_db) and not os.path.exists(trade_parquet):
                    con = connect_to_db(trade_db)
                    df = pd.read_sql_query("SELECT * FROM trade_log", con)
                    if "date" in df.columns:
                        df = df.set_index("date")
                    df.to_parquet(trade_parquet, index=True)
                if os.path.exists(summary_json) and not os.path.exists(summary_yml):
                    with open(summary_json, "r") as fh:
                        summary = json.load(fh)
                    try:
                        import yaml

                        with open(summary_yml, "w") as out:
                            yaml.safe_dump(summary, out, sort_keys=False)
                        os.remove(summary_json)
                    except Exception:
                        pass
            except Exception as exc:
                console.print(f"[red]Migration failed for {run}: {exc}[/red]")

            progress.update(task, advance=1)

    console.print("[green]Migration complete[/green]")


@app.command("migrate_archive")
def migrate_archive_cmd(
    limit: int = typer.Option(0, "--limit", help="Limit number of symbols to migrate"),
):
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    if not os.path.isdir(archive_path):
        console.print("[red]Archive directory not found[/red]")
        raise typer.Exit(code=1)

    work_items = []
    for exchange in os.listdir(archive_path):
        exchange_path = os.path.join(archive_path, exchange)
        if not os.path.isdir(exchange_path):
            continue
        for fname in os.listdir(exchange_path):
            if fname.endswith(".sqlite"):
                work_items.append((exchange, fname))

    if limit and limit > 0:
        work_items = work_items[:limit]

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    with progress:
        task = progress.add_task("Migrating archive", total=len(work_items))
        for exchange, fname in work_items:
            sqlite_path = os.path.join(archive_path, exchange, fname)
            parquet_path = os.path.join(
                archive_path, exchange, fname.replace(".sqlite", ".parquet")
            )
            if not os.path.exists(parquet_path):
                try:
                    migrate_sqlite_to_parquet(sqlite_path, parquet_path)
                except Exception as exc:
                    console.print(f"[red]Migration failed for {fname}: {exc}[/red]")
            progress.update(task, advance=1)

    console.print("[green]Archive migration complete[/green]")


@app.command("regime_train")
def regime_train_cmd(
    config: str = typer.Argument(..., help="Path to regime config YAML"),
    data_path: str = typer.Argument(..., help="Path to OHLCV data (CSV)"),
    out: str = typer.Option("regime_model.pkl", "--out", help="Output model path"),
):
    cfg = _load_json_or_yaml(config)
    df = pd.read_csv(data_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    model = train_regime_model(df, cfg)
    save_regime_model(model, out)
    console.print(f"[green]Saved[/green] regime model to [bold]{out}[/bold]")


@app.command("regime_apply")
def regime_apply_cmd(
    model_path: str = typer.Argument(..., help="Path to regime model"),
    data_path: str = typer.Argument(..., help="Path to OHLCV data (CSV)"),
    out: str = typer.Option("regime_output.csv", "--out", help="Output CSV path"),
):
    model = load_regime_model(model_path)
    df = pd.read_csv(data_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    res = apply_regime_model(df, model)
    res.to_csv(out)
    console.print(f"[green]Saved[/green] regime output to [bold]{out}[/bold]")


@screen_app.command("hmm")
def screen_hmm_cmd(
    config: Optional[str] = typer.Argument(
        None,
        help="Optional YAML/JSON screen config path",
    ),
    exchange: str = typer.Option(
        "coinbase",
        "--exchange",
        help="Exchange/universe source",
    ),
    symbol: Optional[List[str]] = typer.Option(
        None,
        "--symbol",
        help="Symbol to screen; repeatable",
    ),
    live: bool = typer.Option(
        False,
        "--live/--archive",
        help="Fetch live candles (coinbase/hyperliquid) instead of archive parquet",
    ),
    lookback_days: int = typer.Option(260, "--lookback-days"),
    horizons: Optional[List[int]] = typer.Option(
        None,
        "--horizon",
        help="Forecast horizon in days; repeatable",
    ),
    states: int = typer.Option(3, "--states"),
    simulations: int = typer.Option(5000, "--simulations"),
    seed: int = typer.Option(42, "--seed"),
    max_products: int = typer.Option(40, "--max-products"),
    json_out: Optional[str] = typer.Option(None, "--json-out"),
    md_out: Optional[str] = typer.Option(None, "--md-out"),
):
    """Run an HMM forecast screen across a symbol universe."""
    from fast_trade.ml.hmm_data import screen_from_config

    cfg: Dict = {}
    if config:
        cfg = _load_json_or_yaml(config)
    if exchange not in SCREEN_EXCHANGE_CHOICES and not cfg.get("exchange"):
        raise typer.BadParameter(f"exchange must be one of {SCREEN_EXCHANGE_CHOICES}")

    cfg.setdefault("settings", {})
    cfg.setdefault("filters", {})
    cfg.setdefault("outputs", {})
    cfg["exchange"] = exchange or cfg.get("exchange") or "coinbase"
    if symbol:
        cfg["symbols"] = list(symbol)
    cfg["live"] = live if config is None else bool(cfg.get("live", live))
    if live:
        cfg["live"] = True
    cfg["settings"]["lookback_days"] = lookback_days
    if horizons:
        cfg["settings"]["horizons"] = list(horizons)
    cfg["settings"]["states"] = states
    cfg["settings"]["simulations"] = simulations
    cfg["settings"]["seed"] = seed
    cfg["settings"]["max_products"] = max_products
    if json_out:
        cfg["outputs"]["json_out"] = json_out
    if md_out:
        cfg["outputs"]["md_out"] = md_out
    cfg["outputs"].setdefault(
        "title",
        f"{str(cfg['exchange']).title()} HMM Screener",
    )

    payload = screen_from_config(cfg)
    console.print(
        f"[green]Screened[/green] {len(payload['results'])} symbol(s), "
        f"skipped {len(payload['skipped'])}"
    )
    if payload["results"]:
        top = payload["results"][0]
        console.print(
            f"Top: [bold]{top['symbol']}[/bold] score={top['score']:.2f} "
            f"price={top['price']}"
        )
    if cfg["outputs"].get("json_out"):
        console.print(f"Wrote {cfg['outputs']['json_out']}")
    if cfg["outputs"].get("md_out"):
        console.print(f"Wrote {cfg['outputs']['md_out']}")


def _load_backtest_run(backtests_path: str, run_id: str):
    run_path = os.path.join(backtests_path, run_id)
    summary = _load_backtest_summary(run_path)

    trade_path = os.path.join(run_path, "trade_log.parquet")
    df_path = os.path.join(run_path, "dataframe.parquet")
    trade_df = pd.read_parquet(trade_path) if os.path.exists(trade_path) else None
    df = pd.read_parquet(df_path) if os.path.exists(df_path) else None
    if trade_df is not None and "date" in trade_df.columns:
        trade_df = trade_df.set_index("date")
    if df is not None and "date" in df.columns:
        df = df.set_index("date")

    return run_path, summary, trade_df, df


def _load_backtest_summary(run_path: str) -> dict:
    summary_yml = os.path.join(run_path, "summary.yml")
    summary_json = os.path.join(run_path, "summary.json")

    if os.path.exists(summary_yml):
        return _load_json_or_yaml(summary_yml)
    if os.path.exists(summary_json):
        summary = _load_json_or_yaml(summary_json)
        try:
            import yaml

            with open(summary_yml, "w") as out:
                yaml.safe_dump(summary, out, sort_keys=False)
        except Exception:
            pass
        return summary

    raise FileNotFoundError("summary.yml or summary.json not found")


def _max_datapoint_periods(backtest: dict) -> int:
    max_period = 0
    for dp in backtest.get("datapoints", []):
        args = dp.get("args", [])
        periods = [int(a) for a in args if isinstance(a, int)]
        if periods:
            max_period = max(max_period, max(periods))
    return max_period


def _load_latest_ohlcv(exchange: str, symbol: str, lookback_rows: int) -> pd.DataFrame:
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    path = os.path.join(archive_path, exchange, f"{symbol}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Archive not found: {path}")
    from fast_trade.archive.db_helpers import _safe_read_parquet, get_kline

    df = _safe_read_parquet(path)
    if df is None:
        # parquet was corrupted; it has been removed. Rebuild from source.
        df = get_kline(symbol, exchange, freq="1Min")
    if "date" in df.columns:
        df = df.set_index("date")
    df.index = pd.to_datetime(df.index)
    if lookback_rows and len(df) > lookback_rows:
        df = df.tail(lookback_rows)
    return df


@app.command()
def validate(
    strategy: str = typer.Argument(..., help="Path or URL to strategy JSON"),
    mods: Optional[List[str]] = typer.Option(
        None, "--mods", help="Modifiers for strategy/backtest (key value pairs)",
    ),
):
    strat_obj = open_strat_file(strategy)
    strat_obj = _apply_mods(strat_obj, mods)

    with console.status("Validating strategy...", spinner="dots"):
        errors = validate_backtest(strat_obj)

    if errors.get("has_error"):
        console.print("[red]Validation errors found[/red]")
        pprint(errors)
        raise typer.Exit(code=1)

    console.print("[green]Strategy is valid[/green]")


@app.command("logs")
def logs_cmd(
    name: str = typer.Option(..., "--name", help="Portfolio name"),
    follow: bool = typer.Option(
        False,
        "--follow/--no-follow",
        help="Follow logs as they are written",
        show_default=True,
    ),
    tail: int = typer.Option(
        200,
        "--tail",
        help="Number of lines to show before follow",
        show_default=True,
    ),
):
    paths = _portfolio_paths(name)
    read_path = paths["log"]
    legacy_path = read_path.replace(".jsonl", ".log")

    if not os.path.exists(read_path) and not os.path.exists(legacy_path):
        console.print(f"[red]No portfolio log found:[/red] {read_path}")
        raise typer.Exit(code=1)

    read_path = read_path if os.path.exists(read_path) else legacy_path
    console.print(Panel.fit(f"Portfolio log — {name}", style="blue"))

    def _tail_file(path: str, max_lines: int) -> List[str]:
        if max_lines <= 0 or not os.path.exists(path):
            return []
        from collections import deque

        lines = deque(maxlen=max_lines)
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                lines.append(line.rstrip("\n"))
        return list(lines)

    for line in _tail_file(read_path, tail):
        console.print(_format_log_line(line))

    if not follow:
        return

    console.print("[cyan]Following logs. Press Ctrl+C to stop.[/cyan]")
    position = None
    while True:
        try:
            if position is None or position.closed:
                position = open(read_path, "r", encoding="utf-8", errors="ignore")
                position.seek(0, os.SEEK_END)
            while True:
                line = position.readline()
                if not line:
                    break
                console.print(_format_log_line(line))
        except Exception:
            pass
        time.sleep(0.25)


@app.command("update_archive")
def update_archive_cmd():
    console.print(Panel.fit("Updating archive", style="yellow"))
    update_archive()
    console.print("[green]Archive update complete[/green]")


@portfolio_app.command("start")
def portfolio_start_cmd(
    strategy: str = typer.Argument(..., help="Path to strategy YAML"),
    symbol: str = typer.Option("BTC-USD", "--symbol", help="Symbol to trade"),
    name: Optional[str] = typer.Option(None, "--name", help="Portfolio name"),
    cash: Optional[float] = typer.Option(None, "--cash", help="Starting cash (overrides strategy base_balance)"),
    paper: bool = typer.Option(True, "--paper/--no-paper", help="Paper mode only", show_default=True),
    once: bool = typer.Option(False, "--once", help="Run a single cycle and exit", show_default=True),
    daemon: bool = typer.Option(True, "--daemon/--no-daemon", help="Run in background", show_default=True),
):
    if not paper:
        console.print("[red]Live trading is not supported. Use --paper.[/red]")
        raise typer.Exit(code=1)

    strategy_obj = open_strat_file(strategy)
    if not isinstance(strategy_obj, dict):
        console.print("[red]Invalid strategy[/red]")
        raise typer.Exit(code=1)

    strategy_obj = {**strategy_obj}
    strategy_obj["symbol"] = symbol
    exchange = strategy_obj.get("exchange", "coinbase")
    freq = strategy_obj.get("freq", "1Min")
    interval = pd.Timedelta(freq)
    lookback = max(200, _max_datapoint_periods(strategy_obj) + 10)

    base_balance = float(strategy_obj.get("base_balance", 10000))
    if cash is not None:
        base_balance = float(cash)

    lot_size_perc = float(strategy_obj.get("lot_size_perc", 1.0))
    max_lot_size = float(strategy_obj.get("max_lot_size", 0.0))

    if not name:
        base_name = os.path.splitext(os.path.basename(strategy))[0]
        safe_symbol = symbol.replace("/", "-")
        name = f"{base_name}-{safe_symbol}"

    paths = _portfolio_paths(name)
    if daemon:
        log_path = paths["log"]
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        cmd = [
            "ft",
            "portfolio",
            "start",
            strategy,
            "--symbol",
            symbol,
            "--name",
            name,
            "--paper",
            "--no-daemon",
        ]
        if cash is not None:
            cmd += ["--cash", str(cash)]
        if once:
            cmd += ["--once"]
        with open(log_path, "a", encoding="utf-8") as out:
            proc = subprocess.Popen(
                cmd,
                stdout=out,
                stderr=out,
                start_new_session=True,
            )
        try:
            with open(paths["pid"], "w", encoding="utf-8") as fh:
                fh.write(str(proc.pid))
        except Exception:
            pass
        console.print(f"[green]Portfolio started in background[/green] pid={proc.pid}")
        console.print(f"[cyan]Log[/cyan] {log_path}")
        return
    state = _load_portfolio_state(
        paths["state"],
        {
            "name": name,
            "symbol": symbol,
            "exchange": exchange,
            "cash": base_balance,
            "position_qty": 0.0,
            "avg_price": 0.0,
            "equity": base_balance,
            "last_action": "INIT",
            "last_price": None,
            "last_data_ts": None,
            "started_at": datetime.datetime.utcnow().isoformat(),
        },
    )

    console.print(Panel.fit(f"Portfolio {name} — {symbol} ({exchange})", style="blue"))
    console.print(f"[cyan]State[/cyan] cash={state.get('cash')} position={state.get('position_qty')}")
    compiled_action_logic = compile_action_logic(strategy_obj)

    def _run_cycle():
        nonlocal state
        try:
            df = _load_latest_ohlcv(exchange, symbol, lookback)
        except Exception as exc:
            msg = f"{datetime.datetime.utcnow().isoformat()} | ERROR | load_data={exc}"
            _append_portfolio_log(paths["log"], msg)
            console.print(f"[red]{msg}[/red]")
            return

        if df.empty:
            msg = f"{datetime.datetime.utcnow().isoformat()} | WARN | empty_df"
            _append_portfolio_log(paths["log"], msg)
            console.print(f"[yellow]{msg}[/yellow]")
            return

        df = prepare_df(df, strategy_obj)
        if df.empty:
            msg = f"{datetime.datetime.utcnow().isoformat()} | WARN | empty_df_after_prepare"
            _append_portfolio_log(paths["log"], msg)
            console.print(f"[yellow]{msg}[/yellow]")
            return

        frames = list(df.tail(10).itertuples())
        if not frames:
            msg = f"{datetime.datetime.utcnow().isoformat()} | WARN | no_frames"
            _append_portfolio_log(paths["log"], msg)
            console.print(f"[yellow]{msg}[/yellow]")
            return
        frame = frames[-1]
        last_frames = list(reversed(frames))
        action = determine_action_compiled(frame, compiled_action_logic, last_frames=last_frames)

        last_ts = df.index[-1]
        last_price = float(getattr(frame, "close", 0.0))
        state["last_price"] = last_price
        state["last_data_ts"] = str(last_ts)

        state, executed, action = _apply_portfolio_action(
            state,
            action,
            last_price,
            lot_size_perc,
            max_lot_size,
        )
        cash_bal = float(state.get("cash", 0.0))
        position_qty = float(state.get("position_qty", 0.0))
        equity = float(state.get("equity", 0.0))
        state["last_action"] = action
        state["updated_at"] = datetime.datetime.utcnow().isoformat()

        log_line = (
            f"{state['updated_at']} | {action.upper()} | close={_format_value(last_price)} "
            f"| cash={_format_value(cash_bal)} | pos={_format_value(position_qty)} | equity={_format_value(equity)}"
        )
        _append_portfolio_log(paths["log"], log_line)
        console.print(log_line)

        if executed:
            trade = {
                "ts": state["updated_at"],
                "symbol": symbol,
                "side": executed["side"],
                "price": executed["price"],
                "qty": executed["qty"],
                "notional": executed["notional"],
                "cash_after": cash_bal,
                "position_qty_after": position_qty,
                "equity_after": equity,
            }
            _append_portfolio_trades(paths["trades"], [trade])

        _save_portfolio_state(paths["state"], state)

    try:
        while True:
            _run_cycle()
            if once:
                break
            now = datetime.datetime.utcnow()
            interval_seconds = max(60, int(interval.total_seconds()))
            next_run = now + datetime.timedelta(seconds=interval_seconds)
            next_run = next_run - datetime.timedelta(
                seconds=next_run.second % interval_seconds, microseconds=next_run.microsecond
            )
            sleep_for = max(1.0, (next_run - now).total_seconds())
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        console.print("[yellow]Portfolio stopped[/yellow]")
    finally:
        if os.path.exists(paths["pid"]):
            try:
                os.remove(paths["pid"])
            except Exception:
                pass


@portfolio_app.command("status")
def portfolio_status_cmd(
    name: str = typer.Argument(..., help="Portfolio name"),
):
    paths = _portfolio_paths(name)
    state = _load_portfolio_state(paths["state"], {})
    if not state:
        console.print("[red]No portfolio state found[/red]")
        raise typer.Exit(code=1)
    rows = [[k, _format_value(v)] for k, v in state.items()]
    if os.path.exists(paths["pid"]):
        try:
            with open(paths["pid"], "r", encoding="utf-8") as fh:
                pid = int(fh.read().strip())
            os.kill(pid, 0)
            rows.append(["runner_pid", str(pid)])
            rows.append(["runner_status", "running"])
        except Exception:
            rows.append(["runner_status", "stale_pid"])
    _render_kv_table(f"Portfolio {name}", rows)


@portfolio_app.command("stop")
def portfolio_stop_cmd(
    name: str = typer.Argument(..., help="Portfolio name"),
):
    paths = _portfolio_paths(name)
    if not os.path.exists(paths["pid"]):
        console.print("[yellow]No running portfolio found[/yellow]")
        return
    try:
        with open(paths["pid"], "r", encoding="utf-8") as fh:
            pid = int(fh.read().strip())
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Stopped portfolio[/green] pid={pid}")
    except Exception as exc:
        console.print(f"[red]Unable to stop portfolio:[/red] {exc}")
    try:
        os.remove(paths["pid"])
    except Exception:
        pass


@app.command("evolve")
def evolve_cmd(
    config: str = typer.Argument(..., help="Path to evolver config JSON"),
):
    if config.endswith((".yml", ".yaml")):
        console.print("[yellow]YAML is supported but JSON is the default format[/yellow]")
    try:
        config_payload = _load_json_or_yaml(config)
    except Exception as exc:
        raise typer.BadParameter(f"Unable to read config file: {exc}")

    strategy_payload = config_payload.get("strategy")
    strategy_path = config_payload.get("strategy_path")
    if strategy_path:
        base_strategy = open_strat_file(strategy_path)
    elif strategy_payload:
        base_strategy = strategy_payload
    else:
        raise typer.BadParameter("Config must include strategy or strategy_path")

    genes_payload = config_payload.get("genes")
    if not genes_payload:
        raise typer.BadParameter("Config must include genes")

    genes_list = []
    if isinstance(genes_payload, list):
        for item in genes_payload:
            if isinstance(item, dict):
                name = item.get("name")
                space = item.get("space")
                if not name or space is None:
                    raise typer.BadParameter("Each gene dict must have name and space")
                genes_list.append((name, space))
            elif isinstance(item, list) and len(item) == 2:
                genes_list.append((item[0], item[1]))
            else:
                raise typer.BadParameter("Genes must be list of {name, space} or [name, space]")
    else:
        raise typer.BadParameter("Genes must be a list")

    settings = config_payload.get("settings", {})
    fitness_config = config_payload.get("fitness")
    generations = settings.get("num_generations", 50)
    parents = settings.get("num_parents_mating", 10)
    population = settings.get("sol_per_pop", 10)
    mutation = settings.get("mutation_percent_genes", 50)
    mutation_type = settings.get("mutation_type", "random")
    crossover = settings.get("crossover_type", "single_point")
    selection = settings.get("parent_selection_type", "sss")
    tournament = settings.get("K_tournament", 4)
    parallel_processing = settings.get("parallel_processing")
    if not parallel_processing:
        threads = settings.get("threads", 4)
        parallel_processing = ["thread", threads]

    console.print(Panel.fit("Evolving strategy", style="magenta"))
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )

    status = {"best": None, "current": None, "gen": 0, "total": generations, "best_genes": None}

    def build_status_table():
        table = Table(title="Evolution Status", box=box.SIMPLE_HEAVY)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("Generation", f"{status['gen']}/{status['total']}")
        table.add_row("Current Fitness", str(status["current"]))
        table.add_row("Best Fitness", str(status["best"]))
        if status["best_genes"]:
            best_preview = ", ".join(f"{k}={v}" for k, v in status["best_genes"][:5])
            table.add_row("Best Genes", best_preview)
        return table

    def progress_callback(payload):
        status["gen"] = payload.get("generation", status["gen"])
        status["total"] = payload.get("total_generations", status["total"])
        if "fitness" in payload:
            status["current"] = payload.get("fitness")
        if payload.get("best_fitness") is not None:
            status["best"] = payload.get("best_fitness")
        if payload.get("best_genes") is not None:
            status["best_genes"] = payload.get("best_genes")

    with Live(build_status_table(), console=console, refresh_per_second=4) as live:
        with progress:
            ga_task = progress.add_task("Running generations", total=generations)

            def wrapped_progress_callback(payload):
                progress_callback(payload)
                progress.update(
                    ga_task,
                    total=status["total"],
                    completed=status["gen"],
                    description="Running generations",
                )
                live.update(build_status_table())

            best_genes, best_fitness = optimize_strategy(
                base_strategy=base_strategy,
                genes=genes_list,
                num_generations=generations,
                num_parents_mating=parents,
                sol_per_pop=population,
                mutation_percent_genes=mutation,
                crossover_type=crossover,
                parent_selection_type=selection,
                K_tournament=tournament,
                mutation_type=mutation_type,
                parallel_processing=parallel_processing,
                progress_callback=wrapped_progress_callback,
                fitness_config=fitness_config,
            )

    table = Table(title="Best Solution", box=box.SIMPLE_HEAVY)
    table.add_column("Gene", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for name, value in best_genes:
        table.add_row(str(name), str(value))
    console.print(table)
    console.print(f"[green]Best fitness[/green] {best_fitness}")


@app.callback()
def cli_callback(
    ctx: typer.Context,
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Enable interactive prompts when supported",
    ),
):
    """Fast Trade CLI."""
    ctx.ensure_object(dict)
    ctx.obj["interactive"] = (
        interactive and sys.stdin.isatty() and sys.stdout.isatty()
    )


def main():
    try:
        app()
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
