import datetime
import json
import os
import threading
import time
from typing import Dict, List, Optional

import pandas as pd
import requests
from rich import box
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fast_trade.cli_render import format_value as _format_value
from fast_trade.cli_render import render_kv_table as _render_kv_table
from fast_trade.cli_render import render_summary as _render_summary

from .cli_helpers import render_plot_preview_from_data

_WIDGET_CACHE: Dict[str, Dict[str, object]] = {}


def render_trades_table(console, trade_df: pd.DataFrame, page: int, page_size: int) -> None:
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


def render_summary_page(console, summary: dict) -> None:
    _render_summary(summary, details=False, show_strategy=False)


def render_tearsheet(console, summary: dict) -> None:
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

    settings_keys = [
        "symbol",
        "exchange",
        "freq",
        "start",
        "stop",
        "base_balance",
        "lot_size_perc",
        "max_lot_size",
        "comission",
        "commission",
        "trailing_stop_loss",
        "slippage",
    ]
    settings_source = strategy if isinstance(strategy, dict) else summary
    settings_rows = []
    if isinstance(settings_source, dict):
        for key in settings_keys:
            if key in settings_source:
                settings_rows.append((key, settings_source.get(key)))
    if settings_rows:
        lines = ["Backtest Settings"]
        for k, v in settings_rows:
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

    group_texts = [Text(g) for g in groups]
    cols = Columns(group_texts, expand=False, equal=False, column_first=True, padding=(0, 2))
    console.print(Panel.fit(cols, padding=(0, 1)))


def format_stream_line(payload: dict) -> List[str]:
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


def parse_trade_time(value: str) -> Optional[datetime.datetime]:
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


def minute_floor(dt: datetime.datetime) -> datetime.datetime:
    return dt.replace(second=0, microsecond=0)


def update_candle(candle: dict, price: float, size: float) -> None:
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


def render_position_page(console, summary: dict) -> None:
    section = summary.get("position_metrics", {})
    if not isinstance(section, dict) or not section:
        console.print("[yellow]No position metrics available[/yellow]")
        return
    rows = [[k, str(v)] for k, v in section.items()]
    _render_kv_table("Position Metrics", rows)


def render_graph_page(console, run_path: str, df: pd.DataFrame, trade_df: pd.DataFrame) -> None:
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
        _WIDGET_CACHE[cache_key] = {
            "ts": cached.get("ts", 0) if cached else 0,
            "panel": cached.get("panel") if cached else _dashboard_text(title, ["Loading..."]),
            "fetching": True,
        }
        threading.Thread(target=fetch, daemon=True).start()

    return _WIDGET_CACHE[cache_key]["panel"]  # type: ignore[return-value]


def build_dashboard_layout(
    console,
    run_id: str,
    run_path: str,
    summary: dict,
    trade_df: pd.DataFrame,
    df: pd.DataFrame,
    runs: List[str],
    archive_path: str,
    stream_info: Optional[dict] = None,
) -> Panel:
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


def render_dashboard(
    console,
    run_id: str,
    run_path: str,
    summary: dict,
    trade_df: pd.DataFrame,
    df: pd.DataFrame,
    runs: List[str],
    archive_path: str,
    stream_info: Optional[dict] = None,
) -> None:
    layout = build_dashboard_layout(
        console, run_id, run_path, summary, trade_df, df, runs, archive_path, stream_info=stream_info
    )
    console.print(layout)


def build_stream_panel(stream_info: dict) -> Panel:
    stream_rows = [
        ["Status", stream_info.get("status", "n/a")],
        ["Product", stream_info.get("product", "n/a")],
        ["Channels", ", ".join(stream_info.get("channels", [])) or "n/a"],
        ["Msg/sec", f"{stream_info.get('mps', 0):.2f}"],
    ]
    return _dashboard_table("Stream", stream_rows)


def stringify_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2)
    return str(value)


def render_dict_table(console, title: str, data: dict) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=True)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in data.items():
        table.add_row(str(key), stringify_value(value))
    console.print(table)
