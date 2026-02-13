import datetime
import json
import os
import sys
import time
import threading
import shlex
import subprocess
import signal
from pprint import pprint
from typing import Dict, List, Optional, Deque, Tuple
from collections import deque

import pandas as pd
import requests
import typer
from rich import box
from rich.console import Console, Group
from rich.align import Align
from rich.columns import Columns
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.history import FileHistory
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
from rich.text import Text

from fast_trade.archive.cli import download_asset, get_assets
from fast_trade.archive.db_helpers import connect_to_db, migrate_sqlite_to_parquet
from fast_trade.archive.update_archive import update_archive
from fast_trade.archive.update_kline import update_kline
from fast_trade.ml.evolver import optimize_strategy
from fast_trade.ml.regime import apply_regime_model, load_regime_model, train_regime_model, save_regime_model
from fast_trade.validate_backtest import validate_backtest
from fast_trade.build_data_frame import prepare_df
from fast_trade.run_backtest import determine_action
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
app.add_typer(portfolio_app, name="portfolio")
console = Console()

EXCHANGE_CHOICES = ["binancecom", "binanceus", "coinbase"]
ASSET_EXCHANGE_CHOICES = ["local", "binanceus", "binancecom", "coinbase"]
_WIDGET_CACHE: Dict[str, Dict[str, object]] = {}


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


def _render_trades_table(trade_df: pd.DataFrame, page: int, page_size: int):
    if trade_df is None or trade_df.empty:
        console.print("[yellow]No trade log available. Run backtest with --save --all[/yellow]")
        return
    start = page * page_size
    end = start + page_size
    view = trade_df.iloc[start:end]
    if view.empty:
        console.print("[yellow]No more trades[/yellow]")
        return
    table = Table(title=f"Trades (page {page + 1})", box=box.SIMPLE_HEAVY)
    cols = list(view.columns)
    if "action" not in cols and "action" in trade_df.columns:
        cols = ["action"] + cols
    cols = cols[:6]
    table.add_column("date", style="cyan", no_wrap=True)
    for col in cols:
        table.add_column(col, style="white")
    for idx, row in view.iterrows():
        values = [str(row.get(c, "")) for c in cols]
        table.add_row(str(idx), *values)
    console.print(table)


def _render_summary_page(summary: dict):
    _render_summary(summary, details=False, show_strategy=False)


def _render_tearsheet(summary: dict):
    headline_keys = [
        "return_perc",
        "market_adjusted_return",
        "sharpe_ratio",
        "max_drawdown",
        "num_trades",
        "win_perc",
        "loss_perc",
        "total_fees",
        "equity_final",
        "equity_peak",
        "test_duration",
    ]
    headline_rows = []
    for key in headline_keys:
        if key in summary:
            headline_rows.append([key, _format_value(summary.get(key))])

    section_keys = [
        "position_metrics",
        "trade_quality",
        "market_exposure",
        "effective_trades",
        "drawdown_metrics",
        "risk_metrics",
        "trade_streaks",
        "time_analysis",
        "rules",
    ]

    groups = []
    if headline_rows:
        lines = ["Summary"]
        for k, v in headline_rows:
            lines.append(f"{k}: {v}")
        groups.append("\n".join(lines))

    strategy = summary.get("strategy")
    if isinstance(strategy, dict) and strategy:
        strat_name = strategy.get("name")
        lines = [f"Strategy{(' - ' + str(strat_name)) if strat_name else ''}"]
        for k, v in strategy.items():
            lines.append(f"{k}: {_format_value(v)}")
        groups.append("\n".join(lines))

    for section_key in section_keys:
        section = summary.get(section_key)
        if isinstance(section, dict) and section:
            lines = [section_key.replace("_", " ").title()]
            for k, v in section.items():
                lines.append(f"{k}: {_format_value(v)}")
            groups.append("\n".join(lines))

    remaining = []
    for key, value in summary.items():
        if key in headline_keys:
            continue
        if isinstance(value, dict):
            continue
        remaining.append([key, _format_value(value)])
    if remaining:
        lines = ["Other"]
        for k, v in remaining:
            lines.append(f"{k}: {v}")
        groups.append("\n".join(lines))

    if not groups:
        console.print("[yellow]No summary data available[/yellow]")
        return

    # Auto-fit dense columns, keep groups intact
    group_texts = [Text(g) for g in groups]
    cols = Columns(group_texts, expand=False, equal=False, column_first=True, padding=(0, 2))
    console.print(Panel.fit(cols, padding=(0, 1)))


def _format_stream_line(payload: dict) -> List[str]:
    channel = payload.get("channel") or "unknown"
    ts = payload.get("timestamp") or datetime.datetime.utcnow().isoformat()
    events = payload.get("events") or []
    lines = []
    for event in events:
        product_id = event.get("product_id") or ""
        ev_type = event.get("type") or ""
        if channel == "market_trades":
            trades = event.get("trades") or []
            for t in trades[:5]:
                side = t.get("side")
                price = t.get("price")
                size = t.get("size")
                lines.append(f"{ts} {channel} {product_id} {side} {price} {size}")
        elif channel == "level2":
            updates = event.get("updates") or []
            for u in updates[:5]:
                side = u.get("side")
                price = u.get("price_level") or u.get("price")
                size = u.get("new_quantity") or u.get("size")
                lines.append(f"{ts} {channel} {product_id} {ev_type} {side} {price} {size}")
        else:
            lines.append(f"{ts} {channel} {product_id} {ev_type}")
    return lines or [f"{ts} {channel} (no events)"]


def _parse_trade_time(value: str) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _minute_floor(dt: datetime.datetime) -> datetime.datetime:
    return dt.replace(second=0, microsecond=0)


def _update_candle(candle: dict, price: float, size: float) -> None:
    if candle["open"] is None:
        candle["open"] = price
        candle["high"] = price
        candle["low"] = price
        candle["close"] = price
        candle["volume"] = size
        return
    candle["high"] = max(candle["high"], price)
    candle["low"] = min(candle["low"], price)
    candle["close"] = price
    candle["volume"] += size


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


def _append_klines_to_archive(symbol: str, rows: List[Tuple[datetime.datetime, dict]]) -> None:
    if not rows:
        return
    import pandas as pd
    from fast_trade.archive.db_helpers import _atomic_write_parquet, _safe_read_parquet

    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    exchange = "coinbase"
    out_path = os.path.join(archive_path, exchange, f"{symbol}.parquet")
    new_df = pd.DataFrame(
        {
            "open": [r[1]["open"] for r in rows],
            "close": [r[1]["close"] for r in rows],
            "high": [r[1]["high"] for r in rows],
            "low": [r[1]["low"] for r in rows],
            "volume": [r[1]["volume"] for r in rows],
        },
        index=pd.to_datetime([r[0] for r in rows]),
    )
    new_df.index.name = "date"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.exists(out_path):
        existing = _safe_read_parquet(out_path)
        if existing is None:
            merged = new_df
        else:
            existing.index = pd.to_datetime(existing.index)
            # drop overlapping minutes, then append
            existing = existing[~existing.index.isin(new_df.index)]
            merged = pd.concat([existing, new_df]).sort_index()
    else:
        merged = new_df
    _atomic_write_parquet(merged, out_path, index=True)


def _append_trades_parquet(symbol: str, trades: List[dict]) -> None:
    if not trades:
        return
    import pandas as pd
    from fast_trade.archive.db_helpers import _atomic_write_parquet, _safe_read_parquet

    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    exchange = "coinbase"
    out_dir = os.path.join(archive_path, exchange, "trades")
    os.makedirs(out_dir, exist_ok=True)
    day = trades[0]["ts"][:10]
    out_path = os.path.join(out_dir, f"{symbol}-{day}.parquet")
    df = pd.DataFrame(trades)
    if os.path.exists(out_path):
        existing = _safe_read_parquet(out_path)
        if existing is None:
            merged = df
        else:
            merged = pd.concat([existing, df]).drop_duplicates(subset=["trade_id"], keep="last")
        _atomic_write_parquet(merged, out_path, index=False)
    else:
        _atomic_write_parquet(df, out_path, index=False)


def _render_position_page(summary: dict):
    section = summary.get("position_metrics", {})
    if not isinstance(section, dict) or not section:
        console.print("[yellow]No position metrics available[/yellow]")
        return
    rows = [[k, str(v)] for k, v in section.items()]
    _render_kv_table("Position Metrics", rows)


def _render_graph_page(run_path: str, df: pd.DataFrame, trade_df: pd.DataFrame):
    plot_png = os.path.join(run_path, "plot.png")
    plot_html = os.path.join(run_path, "plot.html")
    if os.path.exists(plot_png) or os.path.exists(plot_html):
        console.print(f"[cyan]Plot[/cyan] {plot_png if os.path.exists(plot_png) else plot_html}")
    if df is not None and not df.empty:
        console.print("[cyan]Plot preview[/cyan]")
        render_plot_preview_from_data(df, trade_df)
    else:
        console.print("[yellow]No dataframe available. Run backtest with --save --all[/yellow]")


def _dashboard_table(title: str, rows: List[List[str]]) -> Panel:
    table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in rows:
        table.add_row(key, value)
    return Panel.fit(table, padding=(0, 1))


def _dashboard_text(title: str, lines: List[str]) -> Panel:
    body = Text("\n".join(lines))
    return Panel.fit(body, title=title, padding=(0, 1))


def _widget_weather_nyc() -> Panel:
    cache_key = "weather_nyc"
    now = time.time()
    cached = _WIDGET_CACHE.get(cache_key)
    if cached and (now - cached.get("ts", 0)) < 300:
        return cached["panel"]  # type: ignore[return-value]

    title = "NYC Weather"

    def fetch():
        try:
            resp = requests.get("https://wttr.in/New%20York?format=j1", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            current = (data.get("current_condition") or [{}])[0]
            temp_f = current.get("temp_F")
            temp_c = current.get("temp_C")
            desc = ((current.get("weatherDesc") or [{}])[0]).get("value")
            humidity = current.get("humidity")
            wind = current.get("windspeedMiles")
            lines = [
                f"{desc}" if desc else "Conditions unavailable",
                f"Temp: {temp_f}F / {temp_c}C" if temp_f and temp_c else "Temp: n/a",
                f"Humidity: {humidity}%" if humidity else "Humidity: n/a",
                f"Wind: {wind} mph" if wind else "Wind: n/a",
            ]
            panel = _dashboard_text(title, lines)
        except Exception:
            panel = _dashboard_text(title, ["Weather unavailable"])
        _WIDGET_CACHE[cache_key] = {"ts": time.time(), "panel": panel, "fetching": False}

    if not cached or not cached.get("fetching"):
        _WIDGET_CACHE[cache_key] = {"ts": cached.get("ts", 0) if cached else 0, "panel": cached.get("panel") if cached else _dashboard_text(title, ["Loading..."]), "fetching": True}
        threading.Thread(target=fetch, daemon=True).start()

    return _WIDGET_CACHE[cache_key]["panel"]  # type: ignore[return-value]


def _build_dashboard_layout(
    run_id: str,
    run_path: str,
    summary: dict,
    trade_df: pd.DataFrame,
    df: pd.DataFrame,
    runs: List[str],
    archive_path: str,
    stream_info: Optional[dict] = None,
) -> Panel:
    width = console.size.width
    height = console.size.height
    metrics_keys = [
        ("return_perc", "Return %"),
        ("cagr_perc", "CAGR %"),
        ("sharpe", "Sharpe"),
        ("sortino", "Sortino"),
        ("max_drawdown_perc", "Max DD %"),
        ("num_trades", "Trades"),
        ("win_rate", "Win Rate"),
    ]
    metrics_rows = []
    for key, label in metrics_keys:
        if key in summary:
            metrics_rows.append([label, _format_value(summary.get(key))])
    if not metrics_rows:
        metrics_rows = [["Metrics", "No summary metrics available"]]

    strategy = summary.get("strategy", {}) if isinstance(summary.get("strategy"), dict) else {}
    strat_rows = []
    for key in ["name", "symbol", "exchange", "timeframe", "start", "end"]:
        if key in strategy:
            strat_rows.append([key, str(strategy.get(key))])
    if not strat_rows:
        strat_rows = [["Strategy", "No strategy in summary"]]

    # Keep panels readable in shorter terminals
    if height >= 45:
        max_recent = 6
        max_shortcuts = 5
    elif height >= 35:
        max_recent = 4
        max_shortcuts = 4
    else:
        max_recent = 3
        max_shortcuts = 3

    recent_lines = runs[:max_recent] if runs else []
    if not recent_lines:
        recent_lines = ["No recent runs"]

    archive_rows = [
        ["Archive", archive_path],
        ["Backtests", str(len(runs))],
    ]
    data_dirs = 0
    if os.path.isdir(archive_path):
        data_dirs = len([d for d in os.listdir(archive_path) if os.path.isdir(os.path.join(archive_path, d))])
    archive_rows.append(["Data dirs", str(data_dirs)])

    shortcuts = [
        "TR trades  SUM summary  TS tearsheet  GP graph  POS positions",
        "LIVE START [SYMBOL]  LIVE STOP",
        "STREAM view  STREAM VIEW live  STREAM START <PRODUCT> channels=trades,level2  STREAM STOP",
        "NEW STRAT  EDIT STRAT  OPEN STRAT",
        "OPEN BT   OPEN STRAT   EDIT STRAT   EDIT BT",
        "BT [SAVE] [PLOT] [MODS k v ...]   UA update archive   N/P page",
        "HELP   Q quit",
    ]
    shortcuts = shortcuts[:max_shortcuts]

    status_rows = [
        ["Run ID", run_id],
        ["Backtests", str(len(runs))],
        ["Archive", archive_path],
    ]
    status_panel = _dashboard_table("App Status", status_rows)
    archive_panel = _dashboard_table("Archive", archive_rows)
    recent_panel = _dashboard_text("Recent Runs", recent_lines)
    stream_panel = _build_stream_panel(stream_info or {"status": "n/a", "product": "n/a", "channels": [], "mps": 0.0})
    shortcuts_panel = _dashboard_text("Shortcuts", shortcuts)
    weather_panel = _widget_weather_nyc()

    stream_lines = [
        f"Status: {stream_info.get('status', 'n/a') if stream_info else 'n/a'}",
        f"Product: {stream_info.get('product', 'n/a') if stream_info else 'n/a'}",
        f"Channels: {', '.join(stream_info.get('channels', [])) if stream_info else 'n/a'}",
        f"Msg/sec: {stream_info.get('mps', 0.0):.2f}" if stream_info else "Msg/sec: 0.00",
    ]
    live_info = stream_info.get("live") if stream_info and stream_info.get("live") else {}
    live_lines = [
        f"Status: {live_info.get('status', 'n/a')}",
        f"Symbol: {live_info.get('symbol', 'n/a')}",
        f"Action: {live_info.get('action', 'n/a')}",
        f"Time: {live_info.get('time', 'n/a')}",
    ]
    weather_panel = _widget_weather_nyc()

    groups = [
        Text("Shortcuts\n" + "\n".join(shortcuts)),
        Text("Recent Runs\n" + "\n".join(recent_lines)),
        Text("App Status\n" + "\n".join([f"{k}: {v}" for k, v in status_rows])),
        Text("Archive\n" + "\n".join([f"{k}: {v}" for k, v in archive_rows])),
        Text("Stream\n" + "\n".join(stream_lines)),
        Text("Live\n" + "\n".join(live_lines)),
        weather_panel,
    ]

    cols = Columns(
        [Text(g.plain) if isinstance(g, Text) else g for g in groups],
        expand=False,
        equal=False,
        column_first=False,
        padding=(0, 2),
    )
    panel = Panel.fit(cols, padding=(0, 1))
    return panel


def _render_dashboard(
    run_id: str,
    run_path: str,
    summary: dict,
    trade_df: pd.DataFrame,
    df: pd.DataFrame,
    runs: List[str],
    archive_path: str,
    stream_info: Optional[dict] = None,
):
    layout = _build_dashboard_layout(
        run_id, run_path, summary, trade_df, df, runs, archive_path, stream_info=stream_info
    )
    console.print(layout)


def _build_stream_panel(stream_info: dict) -> Panel:
    stream_rows = [
        ["Status", stream_info.get("status", "n/a")],
        ["Product", stream_info.get("product", "n/a")],
        ["Channels", ", ".join(stream_info.get("channels", [])) or "n/a"],
        ["Msg/sec", f"{stream_info.get('mps', 0):.2f}"],
    ]
    return _dashboard_table("Stream", stream_rows)


def _stringify_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2)
    return str(value)


def _parse_input_value(raw: str):
    if raw is None:
        return raw
    text = raw.strip()
    if text == "":
        return raw
    try:
        return json.loads(text)
    except Exception:
        return raw


def _render_dict_table(title: str, data: dict) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=True)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in data.items():
        table.add_row(str(key), _stringify_value(value))
    console.print(table)


def _edit_dict_interactive(title: str, data: dict) -> Optional[dict]:
    session = PromptSession()
    updated = dict(data)
    instructions = (
        "Enter key to edit. Commands: S=save, Q=cancel, R=refresh. "
        "Use JSON for lists/dicts/booleans/numbers. Plain text is treated as string."
    )
    while True:
        console.print(Panel.fit(title, style="blue"))
        _render_dict_table(title, updated)
        console.print(f"[cyan]{instructions}[/cyan]")
        key = session.prompt("Edit> ").strip()
        if key == "":
            continue
        key_upper = key.upper()
        if key_upper in ["S", "SAVE"]:
            return updated
        if key_upper in ["Q", "QUIT", "CANCEL"]:
            console.print("[yellow]Edit canceled[/yellow]")
            return None
        if key_upper in ["R", "REFRESH"]:
            continue

        if key not in updated:
            if not Confirm.ask(f"Key '{key}' not found. Add it?", default=False):
                continue

        current = updated.get(key)
        console.print(Panel.fit(f"{key} (current)", style="cyan"))
        console.print(_stringify_value(current))
        raw_val = session.prompt("New value (blank to keep): ")
        if raw_val.strip() == "":
            continue
        updated[key] = _parse_input_value(raw_val)


def _save_yaml_or_json(out_path: str, payload: dict) -> None:
    try:
        import yaml
    except Exception:
        yaml = None
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as fh:
        if yaml is not None and out_path.endswith((".yml", ".yaml")):
            yaml.safe_dump(payload, fh, sort_keys=False)
        else:
            json.dump(payload, fh, indent=2)


def _edit_strategy_interactive(strategy: dict, run_path: str, out_path: Optional[str] = None) -> Optional[str]:
    updated = _edit_dict_interactive("Strategy Editor", strategy)
    if updated is None:
        return None
    if not out_path:
        out_path = os.path.join(run_path, "strategy.override.yml")
    _save_yaml_or_json(out_path, updated)
    console.print(f"[green]Saved[/green] edited strategy to [bold]{out_path}[/bold]")
    return out_path


def _edit_backtest_interactive(summary: dict, run_path: str) -> Optional[dict]:
    updated = _edit_dict_interactive("Backtest Summary Editor", summary)
    if updated is None:
        return None
    out_path = os.path.join(run_path, "summary.yml")
    _save_yaml_or_json(out_path, updated)
    console.print(f"[green]Saved[/green] edited summary to [bold]{out_path}[/bold]")
    return updated


def _create_strategy_interactive(default_name: Optional[str] = None) -> Optional[str]:
    session = PromptSession()
    if default_name is None:
        archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
        default_name = os.path.join(archive_path, "strategies", "strategy.new.yml")
    template = {
        "name": "New Strategy",
        "symbol": "BTCUSDT",
        "exchange": "binanceus",
        "freq": "1H",
        "start": "2024-01-01",
        "stop": "2024-12-31",
        "base_balance": 1000,
        "lot_size_perc": 1.0,
        "max_lot_size": 0.0,
        "comission": 0.0,
        "trailing_stop_loss": 0.0,
        "enter": [],
        "exit": [],
    }
    updated = _edit_dict_interactive("New Strategy", template)
    if updated is None:
        return None
    out_path = session.prompt(f"Save as [{default_name}]: ").strip() or default_name
    _save_yaml_or_json(out_path, updated)
    console.print(f"[green]Saved[/green] new strategy to [bold]{out_path}[/bold]")
    return out_path


def _list_strategy_files() -> List[str]:
    files: List[str] = []
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    strategy_dir = os.path.join(archive_path, "strategies")
    cwd = os.getcwd()

    def _collect(dir_path: str) -> List[str]:
        if not os.path.isdir(dir_path):
            return []
        collected = []
        for name in os.listdir(dir_path):
            if not name.endswith((".yml", ".yaml")):
                continue
            if name.startswith("."):
                continue
            collected.append(os.path.join(dir_path, name))
        return sorted(collected)

    archive_files = _collect(strategy_dir)
    cwd_files = _collect(cwd)
    files.extend(archive_files)
    for path in cwd_files:
        if path not in files:
            files.append(path)
    return files


def _pick_from_list(session: PromptSession, title: str, items: List[str]) -> Optional[str]:
    if not items:
        return None
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Item", style="white")
    for idx, item in enumerate(items, start=1):
        table.add_row(str(idx), item)
    console.print(table)
    raw = session.prompt("Select number: ").strip()
    try:
        choice = int(raw)
    except Exception:
        console.print("[red]Invalid selection[/red]")
        return None
    if choice < 1 or choice > len(items):
        console.print("[red]Selection out of range[/red]")
        return None
    return items[choice - 1]


@app.command("terminal")
def terminal_cmd(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Run ID to open"),
    index: Optional[int] = typer.Option(None, "--index", help="Nth most recent run (1 = latest)"),
    page_size: int = typer.Option(20, "--page-size", help="Rows per page"),
):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        console.print("[red]Terminal mode requires an interactive TTY[/red]")
        raise typer.Exit(code=1)

    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    backtests_path = os.path.join(archive_path, "backtests")
    if not os.path.isdir(backtests_path):
        console.print("[red]No backtests directory found[/red]")
        raise typer.Exit(code=1)

    runs = sorted(os.listdir(backtests_path), reverse=True)
    runs = [r for r in runs if os.path.isdir(os.path.join(backtests_path, r))]
    if not runs:
        console.print("[red]No saved backtests found[/red]")
        raise typer.Exit(code=1)

    if index is not None:
        if index < 1 or index > len(runs):
            console.print("[red]Index out of range[/red]")
            raise typer.Exit(code=1)
        run_id = runs[index - 1]
    elif not run_id:
        run_id = runs[0]

    try:
        run_path, summary, trade_df, df = _load_backtest_run(backtests_path, run_id)
    except Exception as exc:
        console.print(f"[red]Unable to load run: {exc}[/red]")
        raise typer.Exit(code=1)

    history_path = os.path.join(archive_path, "terminal_history.txt")
    live_log_dir = os.path.join(archive_path, "live_logs")
    stream_log_dir = os.path.join(archive_path, "stream_logs")
    live_log_path = os.path.join(live_log_dir, f"{run_id}.log")
    stream_log_path = os.path.join(stream_log_dir, f"{run_id}.log")
    last_strat_path_file = os.path.join(archive_path, "last_strategy_path.txt")
    session = PromptSession(history=FileHistory(history_path))
    completer = NestedCompleter.from_nested_dict(
        {
            "DB": None,
            "TR": None,
            "SUM": None,
            "TS": None,
            "GP": None,
            "POS": None,
            "HELP": None,
            "Q": None,
            "N": None,
            "P": None,
            "UA": None,
            "LIVE": {
                "START": None,
                "STOP": None,
                "VIEW": None,
            },
            "STREAM": {
                "START": None,
                "STOP": None,
                "VIEW": None,
            },
            "LOGS": {
                "LIVE": None,
                "STREAM": None,
                "ALL": None,
            },
            "LOG": {
                "LIVE": None,
                "STREAM": None,
                "ALL": None,
            },
            "OPEN": {
                "STRAT": None,
                "STRATEGY": None,
                "BT": None,
                "BACKTEST": None,
            },
            "SHOW": {
                "STRAT": None,
                "STRATEGY": None,
            },
            "EDIT": {
                "STRAT": None,
                "STRATEGY": None,
                "BT": None,
                "BACKTEST": None,
            },
            "NEW": {
                "STRAT": None,
                "STRATEGY": None,
            },
            "BT": {
                "SAVE": None,
                "PLOT": None,
                "MODS": None,
            },
            "BACKTEST": {
                "SAVE": None,
                "PLOT": None,
                "MODS": None,
            },
            "PORTFOLIO": {
                "START": None,
                "STATUS": None,
                "STOP": None,
            },
            "PORT": {
                "START": None,
                "STATUS": None,
                "STOP": None,
            },
        }
    )
    current_page = "DB"
    trade_page = 0
    current_strategy_path = None
    if os.path.exists(last_strat_path_file):
        try:
            saved_path = open(last_strat_path_file, "r").read().strip()
            if saved_path and os.path.exists(saved_path):
                current_strategy_path = saved_path
        except Exception:
            current_strategy_path = None
    last_result = None
    stream_buffer: Deque[str] = deque(maxlen=200)
    stream_thread: Optional[threading.Thread] = None
    stream_stop_event: Optional[threading.Event] = None
    stream_status = "stopped"
    stream_product = None
    stream_channels: List[str] = []
    stream_msg_total = 0
    stream_rate_start = time.time()
    live_thread: Optional[threading.Thread] = None
    live_stop_event: Optional[threading.Event] = None
    live_status = "stopped"
    live_last_action = "n/a"
    live_last_time = "n/a"
    live_symbol = None
    live_history: Deque[str] = deque(maxlen=200)

    def _append_log_line(path: str, line: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line.rstrip("\n") + "\n")
        except Exception:
            # Avoid breaking live/stream loops due to logging issues.
            pass

    def _current_stream_info() -> dict:
        elapsed = max(1e-6, time.time() - stream_rate_start)
        mps = stream_msg_total / elapsed if stream_status in ["running", "connecting", "reconnecting"] else 0.0
        return {
            "status": stream_status,
            "product": stream_product or "n/a",
            "channels": stream_channels,
            "mps": mps,
        }

    def _current_live_info() -> dict:
        return {
            "status": live_status,
            "symbol": live_symbol or "n/a",
            "action": live_last_action,
            "time": live_last_time,
        }

    def _start_stream(symbol: str, channels: List[str]) -> None:
        nonlocal stream_thread, stream_stop_event, stream_status, stream_product, stream_channels
        nonlocal stream_msg_total, stream_rate_start

        stream_stop_event = threading.Event()
        stream_status = "starting"
        stream_product = symbol
        stream_channels = channels
        stream_msg_total = 0
        stream_rate_start = time.time()

        def _run_stream():
            nonlocal stream_status
            try:
                import asyncio
                import websockets
            except Exception as exc:
                stream_status = f"error: {exc}"
                msg = f"ERROR {exc}"
                stream_buffer.append(msg)
                _append_log_line(stream_log_path, msg)
                return

            async def runner():
                nonlocal stream_status
                url = "wss://advanced-trade-ws.coinbase.com"
                backoff = 1.0
                candles: Dict[datetime.datetime, dict] = {}
                trade_buffer: List[dict] = []
                seen_trades: Dict[str, float] = {}
                last_kline_flush = time.time()
                last_trade_flush = time.time()
                while not stream_stop_event.is_set():
                    try:
                        stream_status = "connecting"
                        async with websockets.connect(
                            url, ping_interval=20, ping_timeout=20, max_size=10 * 1024 * 1024
                        ) as ws:
                            sub = {
                                "type": "subscribe",
                                "product_ids": [symbol],
                                "channel": None,
                            }
                            for ch in channels:
                                if ch == "trades":
                                    ch = "market_trades"
                                sub["channel"] = ch
                                await ws.send(json.dumps(sub))
                            stream_status = "running"
                            while not stream_stop_event.is_set():
                                try:
                                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                except asyncio.TimeoutError:
                                    if time.time() - last_kline_flush >= 60:
                                        now_dt = datetime.datetime.utcnow()
                                        cutoff = _minute_floor(now_dt)
                                        ready = [(k, v) for k, v in candles.items() if k < cutoff and v["open"] is not None]
                                        if ready:
                                            _append_klines_to_archive(symbol, ready)
                                            _append_log_line(
                                                stream_log_path,
                                                f"KLINES_FLUSH count={len(ready)} through={cutoff.isoformat()}",
                                            )
                                            for k, _ in ready:
                                                candles.pop(k, None)
                                        # also write current in-progress minute (do not remove)
                                        current = candles.get(cutoff)
                                        if current and current["open"] is not None:
                                            _append_klines_to_archive(symbol, [(cutoff, current)])
                                            _append_log_line(
                                                stream_log_path,
                                                f"KLINES_FLUSH count=1 through={cutoff.isoformat()} current=1",
                                            )
                                        last_kline_flush = time.time()
                                    if trade_buffer and time.time() - last_trade_flush >= 60:
                                        trade_count = len(trade_buffer)
                                        _append_trades_parquet(symbol, trade_buffer)
                                        _append_log_line(
                                            stream_log_path,
                                            f"TRADES_FLUSH count={trade_count}",
                                        )
                                        trade_buffer = []
                                        last_trade_flush = time.time()
                                        # prune seen cache
                                        cutoff_ts = time.time() - 3600
                                        seen_trades = {k: v for k, v in seen_trades.items() if v >= cutoff_ts}
                                    continue
                                nonlocal stream_msg_total
                                stream_msg_total += 1
                                try:
                                    payload = json.loads(raw)
                                    for line in _format_stream_line(payload):
                                        stream_buffer.append(line)
                                        _append_log_line(stream_log_path, line)
                                    if payload.get("channel") == "market_trades":
                                        events = payload.get("events") or []
                                        for event in events:
                                            trades = event.get("trades") or []
                                            for t in trades:
                                                trade_id = t.get("trade_id")
                                                if trade_id:
                                                    now_ts = time.time()
                                                    last_seen = seen_trades.get(trade_id)
                                                    if last_seen and now_ts - last_seen < 3600:
                                                        continue
                                                    seen_trades[trade_id] = now_ts
                                                t_time = _parse_trade_time(t.get("time"))
                                                if not t_time:
                                                    continue
                                                minute = _minute_floor(t_time)
                                                price = float(t.get("price"))
                                                size = float(t.get("size"))
                                                trade_buffer.append(
                                                    {
                                                        "ts": t.get("time"),
                                                        "product_id": t.get("product_id") or symbol,
                                                        "trade_id": trade_id,
                                                        "price": price,
                                                        "size": size,
                                                        "side": t.get("side"),
                                                    }
                                                )
                                                candle = candles.setdefault(
                                                    minute,
                                                    {"open": None, "high": None, "low": None, "close": None, "volume": 0.0},
                                                )
                                                _update_candle(candle, price, size)
                                        now_dt = datetime.datetime.utcnow()
                                        cutoff = _minute_floor(now_dt)
                                        ready = [(k, v) for k, v in candles.items() if k < cutoff and v["open"] is not None]
                                        if ready:
                                            _append_klines_to_archive(symbol, ready)
                                            _append_log_line(
                                                stream_log_path,
                                                f"KLINES_FLUSH count={len(ready)} through={cutoff.isoformat()}",
                                            )
                                            for k, _ in ready:
                                                candles.pop(k, None)
                                            last_kline_flush = time.time()
                                        # also write current in-progress minute (do not remove)
                                        current = candles.get(cutoff)
                                        if current and current["open"] is not None:
                                            _append_klines_to_archive(symbol, [(cutoff, current)])
                                            _append_log_line(
                                                stream_log_path,
                                                f"KLINES_FLUSH count=1 through={cutoff.isoformat()} current=1",
                                            )
                                    if trade_buffer and time.time() - last_trade_flush >= 60:
                                        trade_count = len(trade_buffer)
                                        _append_trades_parquet(symbol, trade_buffer)
                                        _append_log_line(
                                            stream_log_path,
                                            f"TRADES_FLUSH count={trade_count}",
                                        )
                                        trade_buffer = []
                                        last_trade_flush = time.time()
                                        # prune seen cache
                                        cutoff_ts = time.time() - 3600
                                        seen_trades = {k: v for k, v in seen_trades.items() if v >= cutoff_ts}
                                except Exception:
                                    msg = raw[:500]
                                    stream_buffer.append(msg)
                                    _append_log_line(stream_log_path, msg)
                    except Exception as exc:
                        stream_status = f"reconnecting: {exc}"
                        msg = f"ERROR {exc}"
                        stream_buffer.append(msg)
                        _append_log_line(stream_log_path, msg)
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 30.0)
                stream_status = "stopped"

            asyncio.run(runner())

        stream_thread = threading.Thread(target=_run_stream, daemon=True)
        stream_thread.start()

    def _terminal_handles(parts: List[str], cmd: str) -> bool:
        if not parts:
            return True
        token = parts[0]
        if cmd in ["Q", "QUIT", "EXIT", "SAVE", "S", "N", "NEXT", "P", "PREV", "PREVIOUS", "HELP", "H", "?"]:
            return True
        if token in [
            "DB",
            "DASH",
            "DASHBOARD",
            "TR",
            "TRADE",
            "TRADES",
            "SUM",
            "SUMMARY",
            "TS",
            "TEAR",
            "TEARSHEET",
            "GP",
            "GRAPH",
            "POS",
            "POSITIONS",
            "LIVE",
            "STREAM",
            "LOG",
            "LOGS",
            "OPEN",
            "SHOW",
            "EDIT",
            "NEW",
            "BT",
            "BACKTEST",
            "UA",
            "UPDATE",
            "UPDATE_ARCHIVE",
        ]:
            return True
        return False

    def render_page():
        if current_page != "DB":
            console.clear()
        console.print(Panel.fit(f"FT Terminal — {run_id}", style="blue"))
        if current_page == "DB":
            stream_info = _current_stream_info()
            stream_info["live"] = _current_live_info()
            _render_dashboard(
                run_id, run_path, summary, trade_df, df, runs, archive_path, stream_info=stream_info
            )
        elif current_page == "TR":
            _render_trades_table(trade_df, trade_page, page_size)
        elif current_page == "SUM":
            _render_summary_page(summary)
        elif current_page == "TS":
            _render_tearsheet(summary)
        elif current_page == "GP":
            _render_graph_page(run_path, df, trade_df)
        elif current_page == "POS":
            _render_position_page(summary)
        elif current_page == "STREAM":
            console.print(Panel.fit(f"Stream: {stream_status}", style="blue"))
            if not stream_buffer:
                console.print("[yellow]No stream data yet[/yellow]")
            else:
                console.print("\n".join(list(stream_buffer)[-50:]))
        elif current_page == "LIVE":
            console.print(Panel.fit(f"Live: {live_status}", style="blue"))
            if not live_history:
                console.print("[yellow]No live actions yet[/yellow]")
            else:
                console.print("\n".join(list(live_history)[-50:]))
        elif current_page == "HELP":
            console.print(
                "[cyan]Shortcuts:[/cyan] DB (dashboard), TR (trades), SUM (summary), TS (tearsheet), "
                "GP (graph), POS (positions), LIVE START/STOP/VIEW [SYMBOL], STREAM (view), STREAM VIEW (live), "
                "LOGS [LIVE|STREAM|ALL] [FOLLOW], PORTFOLIO START|STATUS|STOP, NEW STRAT, "
                "STREAM START <PRODUCT> channels=trades,level2, "
                "STREAM STOP, EDIT STRAT, EDIT BT, BT [SAVE] [PLOT] [MODS k v ...], "
                "UA (update archive), N/P (page), Q (quit). "
                "Any other command runs the equivalent `ft <command>`."
            )

    render_page()
    while True:
        raw_cmd = session.prompt("FT> ", completer=completer).strip()
        cmd = raw_cmd.upper()
        parts = cmd.split()
        if cmd in ["Q", "QUIT", "EXIT"]:
            break
        if len(parts) >= 2 and parts[0] in ["DB", "DASH", "DASHBOARD"] and parts[1] == "LIVE":
            current_page = "DB"
        elif cmd in ["DB", "DASH", "DASHBOARD"]:
            current_page = "DB"
        elif cmd in ["TR", "TRADE", "TRADES"]:
            current_page = "TR"
        elif cmd in ["SUM", "SUMMARY"]:
            current_page = "SUM"
        elif cmd in ["TS", "TEAR", "TEARSHEET"]:
            current_page = "TS"
        elif cmd in ["GP", "GRAPH"]:
            current_page = "GP"
        elif cmd in ["POS", "POSITIONS"]:
            current_page = "POS"
        elif parts[:2] == ["LIVE", "START"]:
            if live_thread and live_thread.is_alive():
                console.print("[yellow]Live runner already running[/yellow]")
            else:
                if current_strategy_path and os.path.exists(current_strategy_path):
                    try:
                        strat_obj = open_strat_file(current_strategy_path)
                    except Exception as exc:
                        console.print(f"[red]Unable to load selected strategy:[/red] {exc}")
                        strat_obj = None
                else:
                    strat_obj = summary.get("strategy")
                if not isinstance(strat_obj, dict) or not strat_obj:
                    console.print("[red]No strategy selected for live run[/red]")
                else:
                    live_symbol = strat_obj.get("symbol", "BTC-USD")
                    if len(parts) >= 3:
                        live_symbol = parts[2]
                        strat_obj["symbol"] = live_symbol
                    live_stop_event = threading.Event()
                    live_status = "running"

                    # Ensure stream is running (market_trades by default)
                    if stream_thread and stream_thread.is_alive():
                        if stream_product != live_symbol:
                            console.print(
                                f"[yellow]Restarting stream for {live_symbol} (was {stream_product})[/yellow]"
                            )
                            if stream_stop_event:
                                stream_stop_event.set()
                            try:
                                stream_thread.join(timeout=2.0)
                            except Exception:
                                pass
                            _start_stream(live_symbol, ["market_trades"])
                    else:
                        _start_stream(live_symbol, ["market_trades"])

                    def _run_live():
                        nonlocal live_status, live_last_action, live_last_time
                        try:
                            freq = strat_obj.get("freq", "1Min")
                            interval = pd.Timedelta(freq)
                            lookback = max(200, _max_datapoint_periods(strat_obj) + 10)
                            while not live_stop_event.is_set():
                                try:
                                    df = _load_latest_ohlcv("coinbase", live_symbol, lookback)
                                    df = prepare_df(df, strat_obj)
                                    if df.empty:
                                        live_last_action = "HOLD"
                                        live_last_time = datetime.datetime.utcnow().isoformat()
                                    else:
                                        frames = list(df.tail(10).itertuples())
                                        if not frames:
                                            action = "h"
                                            price = None
                                            ind_cols = []
                                        else:
                                            frame = frames[-1]
                                            price = getattr(frame, "close", None)
                                            last_frames = list(reversed(frames))
                                            action = determine_action(frame, strat_obj, last_frames=last_frames)
                                            base_cols = {
                                                "open",
                                                "high",
                                                "low",
                                                "close",
                                                "volume",
                                                "action",
                                                "in_trade",
                                                "account_value",
                                                "adj_account_value",
                                                "adj_account_value_change",
                                                "adj_account_value_change_perc",
                                                "trailing_stop_loss",
                                            }
                                            ind_cols = [c for c in df.columns if c not in base_cols][:8]
                                        if action in ["e", "ae"]:
                                            live_last_action = "ENTER"
                                        elif action in ["x", "ax", "tsl"]:
                                            live_last_action = "EXIT"
                                        else:
                                            live_last_action = "HOLD"
                                        live_last_time = datetime.datetime.utcnow().isoformat()
                                        parts = [f"{live_last_time}", f"{live_last_action}", f"close={_format_value(price)}"]
                                        for col in ind_cols:
                                            val = getattr(frame, col, None)
                                            parts.append(f"{col}={_format_value(val)}")
                                        line = " | ".join(parts)
                                        live_history.append(line)
                                        _append_log_line(live_log_path, line)
                                except Exception as exc:
                                    live_last_action = f"ERROR: {exc}"
                                    live_last_time = datetime.datetime.utcnow().isoformat()
                                    if "Parquet magic bytes not found" in str(exc):
                                        live_status = "stopped (archive read error)"
                                        if live_stop_event:
                                            live_stop_event.set()
                                # align to interval
                                now = datetime.datetime.utcnow()
                                interval_seconds = max(60, int(interval.total_seconds()))
                                next_run = now + datetime.timedelta(seconds=interval_seconds)
                                next_run = next_run - datetime.timedelta(
                                    seconds=next_run.second % interval_seconds, microseconds=next_run.microsecond
                                )
                                sleep_for = max(1.0, (next_run - now).total_seconds())
                                if live_stop_event.wait(sleep_for):
                                    break
                        finally:
                            live_status = "stopped"

                    live_thread = threading.Thread(target=_run_live, daemon=True)
                    live_thread.start()
        elif parts[:2] == ["LIVE", "STOP"]:
            if live_stop_event:
                live_stop_event.set()
                live_status = "stopping"
            else:
                console.print("[yellow]Live runner not running[/yellow]")
        elif parts[:2] == ["LIVE", "VIEW"]:
            current_page = "LIVE"
            stop_follow = threading.Event()

            def _wait_enter_live_view():
                session.prompt("Press Enter to stop live view...")
                stop_follow.set()

            threading.Thread(target=_wait_enter_live_view, daemon=True).start()
            while not stop_follow.is_set():
                console.clear()
                console.print(Panel.fit(f"FT Terminal — {run_id}", style="blue"))
                console.print(Panel.fit(f"Live: {live_status}", style="blue"))
                if not live_history:
                    console.print("[yellow]No live actions yet[/yellow]")
                else:
                    console.print("\n".join(list(live_history)[-50:]))
                time.sleep(0.5)
        elif cmd in ["STREAM", "ST"]:
            current_page = "STREAM"
        elif cmd in ["STREAM", "VIEW"] or cmd == "STREAM VIEW":
            current_page = "STREAM"
            # Live-follow view until Enter
            stop_follow = threading.Event()

            def _wait_enter():
                session.prompt("Press Enter to stop stream view...")
                stop_follow.set()

            threading.Thread(target=_wait_enter, daemon=True).start()
            while not stop_follow.is_set():
                console.clear()
                console.print(Panel.fit(f"FT Terminal — {run_id}", style="blue"))
                console.print(Panel.fit(f"Stream: {stream_status}", style="blue"))
                if not stream_buffer:
                    console.print("[yellow]No stream data yet[/yellow]")
                else:
                    console.print("\n".join(list(stream_buffer)[-50:]))
                time.sleep(0.5)
        elif parts[:2] == ["STREAM", "START"]:
            if stream_thread and stream_thread.is_alive():
                console.print("[yellow]Stream already running[/yellow]")
            else:
                symbol = "BTC-USD"
                channels = ["market_trades"]
                for token in parts[2:]:
                    if token.lower().startswith("channels="):
                        _, val = token.split("=", 1)
                        channels = [c.strip() for c in val.split(",") if c.strip()]
                    else:
                        symbol = token
                _start_stream(symbol, channels)
        elif parts[:2] == ["STREAM", "STOP"]:
            if stream_stop_event:
                stream_stop_event.set()
                stream_status = "stopping"
            else:
                console.print("[yellow]No stream running[/yellow]")
        elif parts and parts[0] in ["PORT", "PORTFOLIO"]:
            args = shlex.split(raw_cmd)
            for i in range(min(2, len(args))):
                if args[i].isalpha():
                    args[i] = args[i].lower()
            if len(args) < 2:
                console.print("[yellow]Usage: PORTFOLIO START|STATUS ...[/yellow]")
                continue
            subcmd = args[1]
            if subcmd == "start":
                strategy_path = None
                if current_strategy_path and os.path.exists(current_strategy_path):
                    strategy_path = current_strategy_path
                else:
                    override_path = summary.get("strategy_override_path")
                    if override_path and os.path.exists(override_path):
                        strategy_path = override_path
                if len(args) < 3 or args[2].startswith("-"):
                    if not strategy_path:
                        console.print("[red]No selected strategy. Use OPEN STRAT first.[/red]")
                        continue
                    args.insert(2, strategy_path)
                subprocess.run(["ft"] + args, check=False)
            elif subcmd == "status":
                subprocess.run(["ft"] + args, check=False)
            elif subcmd == "stop":
                subprocess.run(["ft"] + args, check=False)
            else:
                console.print("[yellow]Usage: PORTFOLIO START|STATUS|STOP ...[/yellow]")
        elif parts and parts[0] in ["LOG", "LOGS"]:
            tokens = parts[1:]
            log_kind = "ALL"
            follow_logs = False
            for token in tokens:
                upper = token.upper()
                if upper in ["LIVE", "STREAM", "ALL"]:
                    log_kind = upper
                elif upper in ["FOLLOW", "F"]:
                    follow_logs = True
            show_live = log_kind in ["ALL", "LIVE"]
            show_stream = log_kind in ["ALL", "STREAM"]
            if not show_live and not show_stream:
                console.print("[yellow]Usage: LOGS [LIVE|STREAM|ALL] [FOLLOW][/yellow]")
                continue

            if show_live:
                console.print(Panel.fit(f"LIVE log — {run_id}", style="blue"))
                if os.path.exists(live_log_path):
                    try:
                        with open(live_log_path, "r", encoding="utf-8", errors="ignore") as fh:
                            console.print("\n".join(fh.read().splitlines()[-200:]))
                    except Exception as exc:
                        console.print(f"[red]Unable to read live log:[/red] {exc}")
                else:
                    console.print(f"[yellow]No live log yet:[/yellow] {live_log_path}")

            if show_stream:
                console.print(Panel.fit(f"STREAM log — {run_id}", style="blue"))
                if os.path.exists(stream_log_path):
                    try:
                        with open(stream_log_path, "r", encoding="utf-8", errors="ignore") as fh:
                            console.print("\n".join(fh.read().splitlines()[-200:]))
                    except Exception as exc:
                        console.print(f"[red]Unable to read stream log:[/red] {exc}")
                else:
                    console.print(f"[yellow]No stream log yet:[/yellow] {stream_log_path}")

            if follow_logs:
                stop_follow = threading.Event()

                def _wait_enter_logs():
                    session.prompt("Press Enter to stop log follow...")
                    stop_follow.set()

                threading.Thread(target=_wait_enter_logs, daemon=True).start()
                positions = {}
                while not stop_follow.is_set():
                    any_open = False
                    if show_live and os.path.exists(live_log_path):
                        any_open = True
                        try:
                            fh = positions.get(live_log_path)
                            if fh is None or fh.closed:
                                fh = open(live_log_path, "r", encoding="utf-8", errors="ignore")
                                positions[live_log_path] = fh
                                fh.seek(0, os.SEEK_END)
                            while True:
                                line = fh.readline()
                                if not line:
                                    break
                                console.print(line.rstrip("\n"))
                        except Exception:
                            pass
                    if show_stream and os.path.exists(stream_log_path):
                        any_open = True
                        try:
                            fh = positions.get(stream_log_path)
                            if fh is None or fh.closed:
                                fh = open(stream_log_path, "r", encoding="utf-8", errors="ignore")
                                positions[stream_log_path] = fh
                                fh.seek(0, os.SEEK_END)
                            while True:
                                line = fh.readline()
                                if not line:
                                    break
                                console.print(line.rstrip("\n"))
                        except Exception:
                            pass
                    time.sleep(0.25 if any_open else 0.5)
        elif cmd in ["HELP", "H", "?"]:
            current_page = "HELP"
        elif parts[:2] == ["NEW", "STRAT"] or parts[:2] == ["NEW", "STRATEGY"]:
            _create_strategy_interactive()
        elif parts[:2] == ["SHOW", "STRAT"] or parts[:2] == ["SHOW", "STRATEGY"]:
            if current_strategy_path and os.path.exists(current_strategy_path):
                try:
                    strat_obj = open_strat_file(current_strategy_path)
                    rows = []
                    for key in ["name", "symbol", "exchange", "freq", "start", "stop"]:
                        if key in strat_obj:
                            rows.append([key, _format_value(strat_obj.get(key))])
                    if rows:
                        console.print(f"[green]Current strategy[/green] {current_strategy_path}")
                        _render_kv_table("Strategy Summary", rows)
                    else:
                        console.print(f"[green]Current strategy[/green] {current_strategy_path}")
                except Exception as exc:
                    console.print(f"[yellow]Unable to load strategy summary:[/yellow] {exc}")
            else:
                console.print("[yellow]No strategy selected[/yellow]")
        elif parts[:2] == ["EDIT", "BT"] or parts[:2] == ["EDIT", "BACKTEST"]:
            updated = _edit_backtest_interactive(summary, run_path)
            if updated is not None:
                summary = updated
        elif parts[:2] == ["EDIT", "STRAT"] or parts[:2] == ["EDIT", "STRATEGY"] or cmd in ["EDIT", "E"]:
            if current_strategy_path and os.path.exists(current_strategy_path):
                try:
                    strategy = open_strat_file(current_strategy_path)
                except Exception as exc:
                    console.print(f"[red]Unable to load selected strategy:[/red] {exc}")
                    strategy = {}
            else:
                strategy = summary.get("strategy", {})
            if not isinstance(strategy, dict) or not strategy:
                console.print("[red]No selected strategy found[/red]")
            else:
                override_path = _edit_strategy_interactive(strategy, run_path, out_path=current_strategy_path)
                if override_path:
                    summary["strategy_override_path"] = override_path
        elif cmd in ["UA", "UPDATE", "UPDATE_ARCHIVE"]:
            console.print(Panel.fit("Updating archive", style="yellow"))
            with console.status("Updating archive...", spinner="dots"):
                update_archive()
            console.print("[green]Archive update complete[/green]")
        elif parts[:2] == ["OPEN", "BT"] or parts[:2] == ["OPEN", "BACKTEST"]:
            selected = _pick_from_list(session, "Backtests", runs)
            if selected:
                try:
                    run_path, summary, trade_df, df = _load_backtest_run(
                        backtests_path, selected
                    )
                    trade_page = 0
                    current_page = "DB"
                except Exception as exc:
                    console.print(f"[red]Unable to load run: {exc}[/red]")
        elif parts[:2] == ["OPEN", "STRAT"] or parts[:2] == ["OPEN", "STRATEGY"]:
            strategies = _list_strategy_files()
            selected = _pick_from_list(session, "Strategies", strategies)
            if selected:
                current_strategy_path = selected
                try:
                    with open(last_strat_path_file, "w") as fh:
                        fh.write(selected)
                except Exception:
                    pass
                console.print(f"[green]Selected[/green] {selected}")
                try:
                    strat_obj = open_strat_file(selected)
                    rows = []
                    for key in ["name", "symbol", "exchange", "freq", "start", "stop"]:
                        if key in strat_obj:
                            rows.append([key, _format_value(strat_obj.get(key))])
                    if rows:
                        _render_kv_table("Strategy Summary", rows)
                    if Confirm.ask("View full strategy?", default=False):
                        console.print(json.dumps(strat_obj, indent=2))
                except Exception as exc:
                    console.print(f"[yellow]Unable to load strategy summary:[/yellow] {exc}")
        elif parts[:1] == ["BT"] or parts[:1] == ["BACKTEST"]:
            tokens = parts[1:]
            do_save = "SAVE" in tokens
            do_plot = "PLOT" in tokens
            mods = []
            if "MODS" in tokens:
                idx = tokens.index("MODS")
                mods = tokens[idx + 1 :]
                if len(mods) % 2 != 0:
                    console.print("[red]MODS must be key/value pairs[/red]")
                    continue
            override_path = summary.get("strategy_override_path")
            try:
                if override_path and os.path.exists(override_path):
                    console.print(f"[cyan]Running backtest with edited strategy[/cyan] {override_path}")
                    edited_strategy = open_strat_file(override_path)
                    edited_strategy = _apply_mods(edited_strategy, mods if mods else None)
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
                        data_task = progress.add_task("Loading data", total=100)
                        actions_task = progress.add_task("Processing actions", total=100)
                        simulation_task = progress.add_task("Simulating trades", total=100)

                        def progress_callback(payload):
                            phase = payload.get("phase")
                            percent = payload.get("percent", 0)
                            if phase == "data":
                                progress.update(data_task, completed=percent)
                            elif phase == "actions":
                                progress.update(actions_task, completed=percent)
                            elif phase == "simulation":
                                progress.update(simulation_task, completed=percent)

                        result = run_backtest(edited_strategy, progress_callback=progress_callback)
                elif current_strategy_path and os.path.exists(current_strategy_path):
                    console.print(f"[cyan]Running selected strategy[/cyan] {current_strategy_path}")
                    strategy_obj = open_strat_file(current_strategy_path)
                    strategy_obj = _apply_mods(strategy_obj, mods if mods else None)
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
                        data_task = progress.add_task("Loading data", total=100)
                        actions_task = progress.add_task("Processing actions", total=100)
                        simulation_task = progress.add_task("Simulating trades", total=100)

                        def progress_callback(payload):
                            phase = payload.get("phase")
                            percent = payload.get("percent", 0)
                            if phase == "data":
                                progress.update(data_task, completed=percent)
                            elif phase == "actions":
                                progress.update(actions_task, completed=percent)
                            elif phase == "simulation":
                                progress.update(simulation_task, completed=percent)

                        result = run_backtest(strategy_obj, progress_callback=progress_callback)
                else:
                    console.print("[red]No edited or selected strategy found.[/red]")
                    continue
                summary = result.get("summary", summary)
                last_result = result
                if do_plot:
                    create_plot(result.get("df"), result.get("trade_df"), show=True)
                if do_save:
                    save_path = save(result, save_all=False)["path"]
                    console.print(f"[green]Saved[/green] backtest results to [bold]{save_path}[/bold]")
                console.print("[green]Backtest complete[/green]")
                console.print("[cyan]Latest summary[/cyan]")
                _render_summary(summary, details=False, show_strategy=False)
                current_page = "SUM"
            except Exception as exc:
                console.print(f"[red]Backtest failed:[/red] {exc}")
        elif cmd in ["SAVE", "S"]:
            if not last_result:
                console.print("[red]Nothing to save yet. Run a backtest first.[/red]")
                continue
            console.print("[cyan]Saving results[/cyan]")
            with console.status("Saving results...", spinner="dots"):
                save_path = save(last_result, save_all=False)["path"]
            console.print(f"[green]Saved[/green] backtest results to [bold]{save_path}[/bold]")
        elif cmd in ["N", "NEXT"] and current_page == "TR":
            trade_page += 1
        elif cmd in ["P", "PREV", "PREVIOUS"] and current_page == "TR":
            trade_page = max(0, trade_page - 1)
        elif raw_cmd and not _terminal_handles(parts, cmd):
            try:
                args = shlex.split(raw_cmd)
                for i in range(min(2, len(args))):
                    if args[i].isalpha():
                        args[i] = args[i].lower()
                subprocess.run(["ft"] + args, check=False)
            except Exception as exc:
                console.print(f"[red]CLI command failed:[/red] {exc}")
        if cmd in ["DB", "DASH", "DASHBOARD", "TS", "TEAR", "TEARSHEET"]:
            render_page()


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
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Run ID to open"),
    index: Optional[int] = typer.Option(None, "--index", help="Nth most recent run (1 = latest)"),
    kind: str = typer.Option(
        "all",
        "--kind",
        help="Which logs to show: live, stream, or all",
        show_default=True,
    ),
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
    archive_path = os.getenv("ARCHIVE_PATH", "ft_archive")
    backtests_path = os.path.join(archive_path, "backtests")
    if not os.path.isdir(backtests_path):
        console.print("[red]No backtests directory found[/red]")
        raise typer.Exit(code=1)

    runs = sorted(os.listdir(backtests_path), reverse=True)
    runs = [r for r in runs if os.path.isdir(os.path.join(backtests_path, r))]
    if not runs:
        console.print("[red]No saved backtests found[/red]")
        raise typer.Exit(code=1)

    if index is not None:
        if index < 1 or index > len(runs):
            console.print("[red]Index out of range[/red]")
            raise typer.Exit(code=1)
        run_id = runs[index - 1]
    elif not run_id:
        run_id = runs[0]

    kind = (kind or "all").lower()
    if kind not in ["all", "live", "stream"]:
        console.print("[red]Invalid kind. Use live, stream, or all.[/red]")
        raise typer.Exit(code=1)

    def _tail_file(path: str, max_lines: int) -> List[str]:
        if max_lines <= 0 or not os.path.exists(path):
            return []
        from collections import deque

        lines = deque(maxlen=max_lines)
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                lines.append(line.rstrip("\n"))
        return list(lines)

    log_paths = []
    if kind in ["all", "live"]:
        log_paths.append(("LIVE", os.path.join(archive_path, "live_logs", f"{run_id}.log")))
    if kind in ["all", "stream"]:
        log_paths.append(("STREAM", os.path.join(archive_path, "stream_logs", f"{run_id}.log")))

    for label, path in log_paths:
        console.print(Panel.fit(f"{label} log — {run_id}", style="blue"))
        if not os.path.exists(path):
            console.print(f"[yellow]No log file yet:[/yellow] {path}")
            continue
        for line in _tail_file(path, tail):
            console.print(line)

    if not follow:
        return

    console.print("[cyan]Following logs. Press Ctrl+C to stop.[/cyan]")
    positions = {}
    while True:
        any_open = False
        for label, path in log_paths:
            if not os.path.exists(path):
                continue
            any_open = True
            try:
                fh = positions.get(path)
                if fh is None or fh.closed:
                    fh = open(path, "r", encoding="utf-8", errors="ignore")
                    positions[path] = fh
                    fh.seek(0, os.SEEK_END)
                while True:
                    line = fh.readline()
                    if not line:
                        break
                    console.print(line.rstrip("\n"))
            except Exception:
                pass
        if not any_open:
            time.sleep(0.5)
        else:
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
        action = determine_action(frame, strategy_obj, last_frames=last_frames)

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
