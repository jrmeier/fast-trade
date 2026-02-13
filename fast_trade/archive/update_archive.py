import datetime
import os
import time
from typing import Callable, List, Tuple

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

import pandas as pd

from .update_kline import update_kline
from .db_helpers import _safe_read_parquet

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive"))
console = Console()


def update_single_archive(
    symbol: str,
    exchange: str,
    progress_callback: Callable[[dict], None] = None,
):
    # check the oldest date in the existing archive
    if not symbol.endswith(".parquet"):
        symbol = symbol + ".parquet"
    path = os.path.join(ARCHIVE_PATH, exchange, symbol)

    now = datetime.datetime.now(datetime.timezone.utc)
    now = now.replace(second=0, microsecond=0)

    if os.path.exists(path):
        try:
            df = _safe_read_parquet(path)
            if df is None:
                raise RuntimeError("archive parquet corrupted")
            if "date" in df.columns:
                df = df.set_index("date")
            df.index = pd.to_datetime(df.index)
            start_date = df.index.max()
        except Exception:
            start_date = None
    else:
        start_date = None

    if start_date is None:
        start_date = now - datetime.timedelta(days=7)

    actual_symbol = symbol.replace(".parquet", "")
    update_kline(
        symbol=actual_symbol,
        exchange=exchange,
        start_date=start_date,
        end_date=now,
        progress_callback=progress_callback,
    )


def update_archive():
    """Read the archive and update the klines"""
    count = 0
    start_time = time.time()

    work_items: List[Tuple[str, str]] = []
    for exchange in os.listdir(ARCHIVE_PATH):
        if not os.path.isdir(os.path.join(ARCHIVE_PATH, exchange)):
            continue
        for symbol in os.listdir(os.path.join(ARCHIVE_PATH, exchange)):
            if symbol.startswith("_") or not symbol.endswith(".parquet"):
                continue
            work_items.append((exchange, symbol))

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
        overall_task = progress.add_task("Updating symbols", total=len(work_items))

        for exchange, symbol in work_items:
            actual_symbol = symbol.replace(".parquet", "")
            symbol_task = progress.add_task(f"{exchange}:{actual_symbol}", total=100)

            def progress_callback(status_obj):
                perc = status_obj.get("perc_complete", 0)
                try:
                    completed = float(perc)
                except (TypeError, ValueError):
                    completed = 0
                progress.update(symbol_task, completed=completed)

            try:
                update_single_archive(symbol, exchange, progress_callback=progress_callback)
                progress.update(symbol_task, completed=100)
                progress.update(overall_task, advance=1)
                count += 1
            except Exception as e:
                progress.update(symbol_task, completed=100)
                progress.update(overall_task, advance=1)
                raise e

    updated_time = round(time.time() - start_time, 2)
    console.print(f"[green]Updated {count} symbols in {updated_time} seconds[/green]")


if __name__ == "__main__":
    update_archive()
