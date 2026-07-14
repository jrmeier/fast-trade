"""Tests for fast_trade.cli_render."""

from io import StringIO

from rich.console import Console

from fast_trade.cli_render import format_value, render_kv_table, render_summary


def test_format_value_float_and_other():
    assert format_value(1.234567) == "1.2346"
    assert format_value("x") == "x"
    assert format_value(42) == "42"


def test_render_kv_table_default_console(capsys):
    render_kv_table("T", [["a", "1"]])
    assert capsys.readouterr().out


def test_render_summary_headline_only():
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=True)
    render_summary({"return_perc": 1.5, "num_trades": 2}, console=console)
    assert "return_perc" in buf.getvalue() or "Summary" in buf.getvalue()


def test_render_summary_details_and_remaining():
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=True)
    summary = {
        "return_perc": 1.0,
        "position_metrics": {"avg": 2.5},
        "trade_quality": {},
        "extra_scalar": 99,
        "strategy": {"name": "S"},
    }
    render_summary(summary, details=True, show_strategy=True, console=console)
    text = buf.getvalue()
    assert "Position" in text or "position" in text.lower()
    render_summary(summary, details=True, show_strategy=False, console=console)
