import datetime
import json
import os
import sys
from pprint import pprint
from typing import Dict, List, Optional

import pandas as pd
import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
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
from fast_trade.validate_backtest import validate_backtest

from .cli_helpers import (
    create_plot,
    open_strat_file,
    render_plot_preview_from_data,
    save,
)
from .run_backtest import run_backtest

app = typer.Typer(help="Fast Trade CLI", add_completion=False)
console = Console()

EXCHANGE_CHOICES = ["binancecom", "binanceus", "coinbase"]
ASSET_EXCHANGE_CHOICES = ["local", "binanceus", "binancecom", "coinbase"]


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


def _format_value(value) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _render_kv_table(title: str, rows: List[List[str]]) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


def _render_summary(summary: Dict, details: bool = False, show_strategy: bool = False) -> None:
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
    if headline_rows:
        _render_kv_table("Summary", headline_rows)

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
    if show_strategy:
        section_keys.append("strategy")

    if details:
        for section_key in section_keys:
            section = summary.get(section_key)
            if isinstance(section, dict) and section:
                rows = [[k, _format_value(v)] for k, v in section.items()]
                _render_kv_table(section_key.replace("_", " ").title(), rows)

        # Render any remaining scalar fields
        remaining = []
        for key, value in summary.items():
            if key in headline_keys:
                continue
            if isinstance(value, dict):
                continue
            remaining.append([key, _format_value(value)])
        if remaining:
            _render_kv_table("Other", remaining)


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
            start_date = None
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
                        start_date = latest
                except Exception:
                    start_date = None
            if not start_date:
                start_date = strat_obj.get("start_date")
                if isinstance(start_date, str):
                    try:
                        start_date = datetime.datetime.fromisoformat(start_date)
                    except ValueError:
                        start_date = None
            if isinstance(start_date, datetime.datetime) and start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=datetime.timezone.utc)
            if not isinstance(start_date, datetime.datetime):
                start_date = now - datetime.timedelta(days=30)
            strat_obj["end_date"] = now.isoformat()

            progress.update(data_task, description="Refreshing market data", total=100, completed=0)

            def update_progress(status_obj):
                perc = status_obj.get("perc_complete", 0)
                try:
                    completed = float(perc)
                except (TypeError, ValueError):
                    completed = 0
                progress.update(data_task, completed=completed)
                data_seen["value"] = True

            if start_date >= now - datetime.timedelta(minutes=1):
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
                    start_date=start_date,
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
                summary_path = os.path.join(backtests_path, run, "summary.yml")
                summary_text = ""
                if os.path.exists(summary_path):
                    try:
                        with open(summary_path, "r") as fh:
                            import yaml

                            summary = yaml.safe_load(fh)
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
        summary_path = os.path.join(run_path, "summary.yml")
        if not os.path.exists(summary_path):
            console.print("[red]summary.yml not found for run[/red]")
            raise typer.Exit(code=1)
        with open(summary_path, "r") as fh:
            import yaml

            summary = yaml.safe_load(fh)
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


def _load_backtest_run(backtests_path: str, run_id: str):
    run_path = os.path.join(backtests_path, run_id)
    summary_path = os.path.join(run_path, "summary.yml")
    if not os.path.exists(summary_path):
        raise FileNotFoundError("summary.yml not found")
    with open(summary_path, "r") as fh:
        import yaml

        summary = yaml.safe_load(fh)

    trade_path = os.path.join(run_path, "trade_log.parquet")
    df_path = os.path.join(run_path, "dataframe.parquet")
    trade_df = pd.read_parquet(trade_path) if os.path.exists(trade_path) else None
    df = pd.read_parquet(df_path) if os.path.exists(df_path) else None
    if trade_df is not None and "date" in trade_df.columns:
        trade_df = trade_df.set_index("date")
    if df is not None and "date" in df.columns:
        df = df.set_index("date")

    return run_path, summary, trade_df, df


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


def _edit_strategy_interactive(strategy: dict, run_path: str) -> str:
    session = PromptSession()

    console.print(Panel.fit("Current Strategy", style="blue"))
    console.print(json.dumps(strategy, indent=2))

    def prompt_value(label, current):
        default = "" if current is None else str(current)
        val = session.prompt(f"{label} [{default}]: ")
        return current if val.strip() == "" else val

    def prompt_float(label, current, fallback=0.0):
        val = prompt_value(label, current)
        if val is None or val == "":
            return float(current) if current is not None else fallback
        try:
            return float(val)
        except ValueError:
            return float(current) if current is not None else fallback

    updated = dict(strategy)
    updated["freq"] = prompt_value("freq", updated.get("freq"))
    updated["symbol"] = prompt_value("symbol", updated.get("symbol"))
    updated["exchange"] = prompt_value("exchange", updated.get("exchange"))
    updated["start_date"] = prompt_value("start_date", updated.get("start_date"))
    updated["end_date"] = prompt_value("end_date", updated.get("end_date"))
    updated["comission"] = prompt_float("comission", updated.get("comission", 0.0))
    updated["trailing_stop_loss"] = prompt_float(
        "trailing_stop_loss", updated.get("trailing_stop_loss", 0.0)
    )
    updated["lot_size_perc"] = prompt_float("lot_size_perc", updated.get("lot_size_perc", 1.0))
    updated["max_lot_size"] = prompt_float("max_lot_size", updated.get("max_lot_size", 0.0))

    out_path = os.path.join(run_path, "strategy.override.yml")
    try:
        import yaml
    except Exception:
        yaml = None
    with open(out_path, "w") as fh:
        if yaml is not None:
            yaml.safe_dump(updated, fh, sort_keys=False)
        else:
            json.dump(updated, fh, indent=2)
    console.print(f"[green]Saved[/green] edited strategy to [bold]{out_path}[/bold]")
    return out_path


def _list_strategy_files() -> List[str]:
    files = []
    cwd = os.getcwd()
    for name in os.listdir(cwd):
        if not name.endswith((".yml", ".yaml")):
            continue
        if name.startswith("."):
            continue
        files.append(os.path.join(cwd, name))
    return sorted(files)


def _pick_from_list(session: PromptSession, title: str, items: List[str]) -> Optional[str]:
    if not items:
        return None
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Item", style="white")
    for idx, item in enumerate(items, start=1):
        table.add_row(str(idx), item)
    console.print(table)
    choice = IntPrompt.ask("Select number", default=1)
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

    session = PromptSession()
    completer = WordCompleter(
        ["TR", "SUM", "GP", "POS", "EDIT", "RUN", "SAVE", "OPEN", "N", "P", "HELP", "Q"], ignore_case=True
    )
    current_page = "TR"
    trade_page = 0
    current_strategy_path = None
    last_result = None

    def render_page():
        console.clear()
        console.print(Panel.fit(f"FT Terminal — {run_id}", style="blue"))
        if current_page == "TR":
            _render_trades_table(trade_df, trade_page, page_size)
        elif current_page == "SUM":
            _render_summary_page(summary)
        elif current_page == "GP":
            _render_graph_page(run_path, df, trade_df)
        elif current_page == "POS":
            _render_position_page(summary)
        elif current_page == "HELP":
            console.print(
                "[cyan]Shortcuts:[/cyan] TR (trades), SUM (summary), GP (graph), POS (positions), N/P (page), Q (quit)"
            )

    render_page()
    while True:
        raw_cmd = session.prompt("FT> ", completer=completer).strip()
        cmd = raw_cmd.upper()
        parts = cmd.split()
        if cmd in ["Q", "QUIT", "EXIT"]:
            break
        if cmd in ["TR", "TRADE", "TRADES"]:
            current_page = "TR"
        elif cmd in ["SUM", "SUMMARY"]:
            current_page = "SUM"
        elif cmd in ["GP", "GRAPH"]:
            current_page = "GP"
        elif cmd in ["POS", "POSITIONS"]:
            current_page = "POS"
        elif cmd in ["HELP", "H", "?"]:
            current_page = "HELP"
        elif cmd in ["EDIT", "E"]:
            strategy = summary.get("strategy", {})
            if not isinstance(strategy, dict) or not strategy:
                console.print("[red]No strategy found in summary[/red]")
            else:
                override_path = _edit_strategy_interactive(strategy, run_path)
                summary["strategy_override_path"] = override_path
        elif parts[:2] == ["OPEN", "BT"] or parts[:2] == ["OPEN", "BACKTEST"]:
            selected = _pick_from_list(session, "Backtests", runs)
            if selected:
                try:
                    run_path, summary, trade_df, df = _load_backtest_run(
                        backtests_path, selected
                    )
                    trade_page = 0
                    current_page = "TR"
                except Exception as exc:
                    console.print(f"[red]Unable to load run: {exc}[/red]")
        elif parts[:2] == ["OPEN", "STRAT"] or parts[:2] == ["OPEN", "STRATEGY"]:
            strategies = _list_strategy_files()
            selected = _pick_from_list(session, "Strategies", strategies)
            if selected:
                current_strategy_path = selected
                console.print(f"[green]Selected[/green] {selected}")
        elif cmd in ["RUN", "R"]:
            override_path = summary.get("strategy_override_path")
            try:
                if override_path and os.path.exists(override_path):
                    console.print("[cyan]Re-running backtest with edited strategy[/cyan]")
                    edited_strategy = open_strat_file(override_path)
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
                    console.print("[cyan]Running selected strategy[/cyan]")
                    strategy_obj = open_strat_file(current_strategy_path)
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
                console.print("[green]Re-run complete[/green]")
                console.print("[cyan]Latest summary[/cyan]")
                _render_summary(summary, details=False, show_strategy=False)
                current_page = "SUM"
            except Exception as exc:
                console.print(f"[red]Re-run failed:[/red] {exc}")
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


@app.command("update_archive")
def update_archive_cmd():
    console.print(Panel.fit("Updating archive", style="yellow"))
    update_archive()
    console.print("[green]Archive update complete[/green]")


@app.command("evolve")
def evolve_cmd(
    config: str = typer.Argument(..., help="Path to evolver config JSON"),
):
    if config.endswith((".yml", ".yaml")):
        console.print("[yellow]YAML is supported but JSON is the default format[/yellow]")
    try:
        with open(config, "r") as fh:
            if config.endswith((".yml", ".yaml")):
                import yaml

                config_payload = yaml.safe_load(fh)
            else:
                config_payload = json.load(fh)
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
