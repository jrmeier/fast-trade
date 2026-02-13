from typing import Dict, List, Optional

from rich import box
from rich.console import Console
from rich.table import Table


def format_value(value) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_kv_table(title: str, rows: List[List[str]], console: Optional[Console] = None) -> None:
    if console is None:
        console = Console()
    table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


def render_summary(
    summary: Dict,
    details: bool = False,
    show_strategy: bool = False,
    console: Optional[Console] = None,
) -> None:
    if console is None:
        console = Console()
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
            headline_rows.append([key, format_value(summary.get(key))])
    if headline_rows:
        render_kv_table("Summary", headline_rows, console=console)

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
                rows = [[k, format_value(v)] for k, v in section.items()]
                render_kv_table(section_key.replace("_", " ").title(), rows, console=console)

        # Render any remaining scalar fields
        remaining = []
        for key, value in summary.items():
            if key in headline_keys:
                continue
            if isinstance(value, dict):
                continue
            remaining.append([key, format_value(value)])
        if remaining:
            render_kv_table("Other", remaining, console=console)
