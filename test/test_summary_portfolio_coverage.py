"""Additional portfolio, summary, metrics, and trades coverage."""

import datetime
import json
from unittest import mock

import polars as pl
import pytest

from fast_trade.build_summary import build_summary
from fast_trade.portfolio import append_log, append_trades, apply_action, save_state
from fast_trade.summary.metrics import (
    calculate_buy_and_hold_perc,
    calculate_drawdown_metrics,
    calculate_market_exposure,
    calculate_perc_missing_safe,
    calculate_position_metrics,
    calculate_return_perc,
    calculate_risk_metrics,
    calculate_shape_ratio,
    calculate_trade_streaks,
    calculate_time_analysis,
)
from fast_trade.summary.trades import (
    calculate_effective_trades,
    calculate_trade_quality,
    summarize_trade_perc,
    summarize_trades,
)


def test_append_log_string_dict_and_error(tmp_path):
    log_path = tmp_path / "nested" / "log.jsonl"
    append_log(str(log_path), "hello")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0])["message"] == "hello"

    append_log(str(log_path), {"event": "buy", "qty": 1})
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert "event" in json.loads(lines[1])

    append_log(str(log_path), 99)
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[2])["message"] == "99"

    with mock.patch("builtins.open", side_effect=OSError("nope")):
        append_log(str(log_path), "silent fail")  # swallowed


def test_save_state_error_swallowed(tmp_path):
    path = tmp_path / "state.json"
    with mock.patch("builtins.open", side_effect=OSError("nope")):
        save_state(str(path), {"cash": 1})  # swallowed


def test_append_trades_corrupt_existing(tmp_path):
    path = tmp_path / "trades.parquet"
    path.write_text("not parquet", encoding="utf-8")
    with mock.patch("fast_trade.portfolio._safe_read_parquet", return_value=None):
        append_trades(str(path), [{"side": "BUY", "qty": 1.0}])
    df = pl.read_parquet(path)
    assert len(df) == 1


def test_apply_action_zero_qty_becomes_hold():
    state = {"cash": 0.0, "position_qty": 0.0, "avg_price": 0.0, "equity": 0.0}
    updated, executed, action = apply_action(state, "e", 100.0, 1.0, 0.0)
    assert action == "h"
    assert executed is None


def test_build_summary_non_timedelta_time_held_branch():
    mock_df = pl.read_csv("./test/ohlcv_data.csv.txt").with_columns(
        pl.from_epoch("date", time_unit="s"),
        pl.Series("in_trade", [True, False, False, False, True, True, False, False, False]),
        pl.Series("fee", [0.0] * 9),
        pl.Series("close", [10, 11, 11, 9, 9, 10, 11, 90, 11]),
        pl.Series("action", ["e", "h", "h", "h", "x", "e", "h", "h", "x"]),
        pl.Series("account_value", [90, 110, 110, 90, 90, 100, 110, 90, 100]),
        pl.Series("adj_account_value", [90, 110, 110, 90, 90, 100, 110, 90, 100]),
        pl.Series("aux", [1] * 9),
    ).with_columns(
        pl.col("adj_account_value").diff().fill_null(0).alias("adj_account_value_change"),
        pl.col("account_value").pct_change().fill_null(0).alias("adj_account_value_change_perc"),
    )

    with mock.patch(
        "fast_trade.build_summary.summarize_time_held",
        return_value=(0, 0, 0, 0),
    ):
        summary, _ = build_summary(mock_df, datetime.datetime.utcnow())
    assert summary["median_trade_len"] == 0
    assert summary["mean_trade_len"] == 0


def test_metrics_exception_fallbacks():
    bad = pl.DataFrame(
        {
            "in_trade": [False],
            "aux": [0.0],
            "fee": [0.0],
            "adj_account_value": [0.0],
        }
    )
    assert calculate_position_metrics(bad)["avg_position_size"] == 0.0
    assert calculate_market_exposure(bad)["time_in_market_pct"] == 0.0
    assert calculate_drawdown_metrics(pl.DataFrame())["max_drawdown_pct"] == 0.0
    assert calculate_risk_metrics(pl.DataFrame())["sortino_ratio"] == 0.0
    assert calculate_time_analysis(pl.DataFrame())["best_day"] == 0.0
    assert calculate_trade_streaks(None)["current_streak"] == 0
    assert calculate_trade_streaks(pl.DataFrame())["current_streak"] == 0


def test_metrics_edge_return_and_sharpe_and_buy_hold():
    empty = pl.DataFrame()
    assert calculate_return_perc(empty) == 0.0

    tl = pl.DataFrame({"adj_account_value": [0.0, 10.0]})
    assert calculate_return_perc(tl) == 0.0

    tl = pl.DataFrame({"adj_account_value": [100.0, 0.0]})
    assert calculate_return_perc(tl) == 0.0

    df = pl.DataFrame({"close": [1.0, 0.0]})
    assert calculate_buy_and_hold_perc(df) == 0.0

    sharpe_df = pl.DataFrame({"adj_account_value_change_perc": [0.0, 0.0, 0.0]})
    assert calculate_shape_ratio(sharpe_df) == 0.0

    assert calculate_perc_missing_safe(
        pl.DataFrame({"date": [datetime.datetime(2024, 1, 1)], "close": [1]})
    ) == [0.0, 0]


def test_trade_streaks_and_quality_exceptions():
    tl = pl.DataFrame({"adj_account_value_change_perc": [1.0]})
    streaks = calculate_trade_streaks(tl)
    assert streaks["current_streak"] == 1

    empty_quality = calculate_trade_quality(
        pl.DataFrame(schema={"adj_account_value_change_perc": pl.Float64})
    )
    assert empty_quality["profit_factor"] == 0.0

    only_losses = pl.DataFrame({"adj_account_value_change_perc": [-1.0, -2.0]})
    q = calculate_trade_quality(only_losses)
    assert q["profit_factor"] == 0.0
    assert q["avg_win_loss_ratio"] == 0.0

    assert q["largest_winning_trade"] == -1.0


def test_effective_trades_empty_and_missing_pnl():
    empty = calculate_effective_trades(pl.DataFrame(), pl.DataFrame())
    assert empty["num_profitable_after_commission"] == 0

    dates = [datetime.datetime(2024, 1, 1), datetime.datetime(2024, 1, 2)]
    trade_log = pl.DataFrame(
        {"date": dates, "adj_account_value_change_perc": [0.1, -0.1]}
    )
    df = pl.DataFrame(
        {"date": dates, "fee": [0.0, 0.0], "adj_account_value": [100, 100]}
    )
    res = calculate_effective_trades(df, trade_log)
    assert res["commission_drag_pct"] == 0.0


def test_summarize_trade_perc_and_trades_errors():
    tl = pl.DataFrame({"adj_account_value_change_perc": [0.1, 0.2]})
    mx, mn, mean, med = summarize_trade_perc(tl)
    assert mx == pytest.approx(0.2)

    total, avg, pct = summarize_trades(tl, 10)
    assert total == 2
    assert avg == 15.0
    assert pct == 20.0
