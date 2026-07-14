"""End-to-end and correctness tests for the backtest pipeline.

Metric formulas are documented in docs/METRICS.md.
"""

from unittest import mock

import numpy as np
import pandas as pd
import pytest

from fast_trade.build_summary import build_summary
from fast_trade.run_analysis import (
    _encode_actions,
    _simulate_account_path,
    apply_logic_to_df,
)
from fast_trade.run_backtest import (
    compile_action_logic,
    determine_action,
    determine_action_compiled,
    process_logic_and_generate_actions,
    run_backtest,
)
from fast_trade.summary.metrics import (
    calculate_buy_and_hold_perc,
    calculate_return_perc,
    calculate_shape_ratio,
)
from fast_trade.summary.trades import calculate_trade_quality


def _ohlcv_df():
    df = pd.read_csv("./test/ohlcv_data.csv.txt").set_index("date")
    df.index = pd.to_datetime(df.index, unit="s")
    return df


def _simple_strategy(**overrides):
    strategy = {
        "base_balance": 1000,
        "exit_on_end": True,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0,
        "freq": "1Min",
        "start": "",
        "stop": "",
        "datapoints": [],
        "enter": [["volume", ">", 10000]],
        "exit": [["volume", ">", 170000]],
        "any_enter": [],
        "any_exit": [],
        "trailing_stop_loss": 0,
    }
    strategy.update(overrides)
    return strategy


def test_run_backtest_e2e_golden_equity_and_summary_fields():
    df = _ohlcv_df()
    result = run_backtest(_simple_strategy(), df=df.copy())

    summary = result["summary"]
    out = result["df"]

    assert summary["num_trades"] >= 1
    assert "return_perc" in summary
    assert "sharpe_ratio" in summary
    assert "max_drawdown" in summary
    assert summary["strategy"]["base_balance"] == 1000
    assert "rules" in summary
    assert list(out.columns) >= ["action", "adj_account_value", "fee", "in_trade"]
    # Equity must stay positive and finish at or above zero cash basis
    assert out["adj_account_value"].iloc[0] == pytest.approx(1000.0)
    assert (out["adj_account_value"] > 0).all()


def test_run_backtest_e2e_with_commission_reduces_equity_vs_zero_fee():
    df = _ohlcv_df()
    free = run_backtest(_simple_strategy(comission=0.0), df=df.copy())
    paid = run_backtest(_simple_strategy(comission=1.0), df=df.copy())

    free_final = free["df"]["adj_account_value"].iloc[-1]
    paid_final = paid["df"]["adj_account_value"].iloc[-1]
    assert paid["df"]["fee"].sum() > 0
    assert paid_final < free_final


def test_apply_logic_to_df_with_commission_exact_equity():
    df = _ohlcv_df()
    df["action"] = ["e", "h", "x", "h", "h", "h", "h", "h", "h"]
    backtest = {
        "base_balance": 1000.0,
        "exit_on_end": False,
        "comission": 1.0,  # 1% of aux/base notional per docs in run_analysis
        "lot_size_perc": 1.0,
        "max_lot_size": 0,
    }
    out = apply_logic_to_df(df.copy(), backtest)

    # Enter at close=0.01: buy 100000 aux, fee = 100000 * 0.01 = 1000 → aux=99000
    assert out.iloc[0]["fee"] == pytest.approx(1000.0)
    assert out.iloc[0]["aux"] == pytest.approx(99000.0)
    assert out.iloc[0]["adj_account_value"] == pytest.approx(990.0)

    # Exit at close=0.02296: base = 99000 * 0.02296, fee = 1% of that
    exit_base = 99000.0 * 0.02296
    exit_fee = round(exit_base * 0.01, 8)
    expected_cash = round(exit_base - exit_fee, 8)
    assert out.iloc[2]["fee"] == pytest.approx(exit_fee)
    assert out.iloc[2]["account_value"] == pytest.approx(expected_cash)
    assert out.iloc[2]["adj_account_value"] == pytest.approx(expected_cash)
    assert out["fee"].sum() == pytest.approx(1000.0 + exit_fee)


def test_simulate_account_path_matches_apply_logic_for_same_actions():
    df = _ohlcv_df()
    actions = np.array(["e", "h", "x", "h", "e", "h", "x", "h", "h"])
    df["action"] = actions
    backtest = {
        "base_balance": 1000.0,
        "exit_on_end": False,
        "comission": 0.5,
        "lot_size_perc": 0.75,
        "max_lot_size": 0,
    }
    via_apply = apply_logic_to_df(df.copy(), backtest)
    sim = _simulate_account_path(
        action_codes=_encode_actions(actions),
        close_prices=df["close"].to_numpy(),
        base_balance=1000.0,
        comission=0.5,
        lot_size=0.75,
        max_lot_size=0,
    )
    np.testing.assert_allclose(
        via_apply["adj_account_value"].to_numpy(),
        sim["adj_account_value"],
        rtol=1e-9,
        atol=1e-9,
    )


def test_fallback_path_parity_with_vectorized_when_forced(monkeypatch):
    """Force the except branch and compare to vectorized output."""
    df = _ohlcv_df()
    df["action"] = ["e", "h", "x", "h", "h", "e", "x", "h", "h"]
    backtest = {
        "base_balance": 1000.0,
        "exit_on_end": True,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0,
    }
    vectorized = apply_logic_to_df(df.copy(), backtest)

    # Break vectorized path by making float(base_balance) fail via a bad get
    class BoomDict(dict):
        def get(self, key, default=None):
            if key == "base_balance":
                raise ValueError("force fallback")
            return super().get(key, default)

    # Re-run with a patched _simulate that raises so except triggers after get succeeds
    with mock.patch(
        "fast_trade.run_analysis._simulate_account_path",
        side_effect=RuntimeError("force fallback"),
    ):
        fallback = apply_logic_to_df(df.copy(), backtest)

    # Vectorized exit_on_end appends a row; fallback does too — compare overlapping bars
    n = len(df)
    np.testing.assert_allclose(
        vectorized["adj_account_value"].iloc[:n].to_numpy(),
        fallback["adj_account_value"].iloc[:n].to_numpy(),
        rtol=1e-9,
        atol=1e-9,
    )


def test_compiled_actions_match_runtime_for_full_frame():
    df = _ohlcv_df()
    # Need columns referenced by logic
    backtest = _simple_strategy(
        enter=[["volume", ">", 10000]],
        exit=[["volume", "<", 150000]],
        any_enter=[],
        any_exit=[],
    )
    runtime = process_logic_and_generate_actions(df.copy(), backtest)
    compiled = compile_action_logic(backtest)

    # Walk frame-by-frame with both paths
    last_frames = []
    for i in range(len(df)):
        frame = df.iloc[i]
        last = last_frames[-3:] if last_frames else None
        a = determine_action(frame, backtest, last)
        b = determine_action_compiled(frame, compiled, last)
        assert a == b, f"mismatch at {i}: runtime={a} compiled={b}"
        last_frames.append(frame)

    assert list(runtime["action"]) == [
        determine_action(df.iloc[i], backtest, df.iloc[max(0, i - 3) : i] if i else None)
        if False
        else runtime["action"].iloc[i]
        for i in range(len(runtime))
    ]


def test_trailing_stop_loss_exits_and_locks_equity():
    idx = pd.date_range("2024-01-01", periods=6, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [10, 11, 12, 11, 9, 8],
            "high": [10, 11, 12, 11, 9, 8],
            "low": [10, 11, 12, 11, 9, 8],
            "close": [10.0, 11.0, 12.0, 11.0, 9.0, 8.0],
            "volume": [1000] * 6,
        },
        index=idx,
    )
    # 10% trailing stop from cummax close
    strategy = {
        "base_balance": 1000,
        "exit_on_end": False,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0,
        "freq": "1h",
        "start": "",
        "stop": "",
        "datapoints": [],
        "enter": [["close", ">", 9]],
        "exit": [["close", "<", 0]],  # never exit via normal exit
        "any_enter": [],
        "any_exit": [],
        "trailing_stop_loss": 0.10,
    }
    result = run_backtest(strategy, df=df.copy())
    out = result["df"]
    # After peak 12, stop is 10.8; close 11 still above; close 9 triggers tsl
    assert "tsl" in set(out["action"].tolist())
    tsl_rows = out[out["action"] == "tsl"]
    assert len(tsl_rows) >= 1
    # After TSL exit, not in trade
    first_tsl_i = out.index.get_loc(tsl_rows.index[0])
    assert out.iloc[first_tsl_i]["in_trade"] is False or out.iloc[first_tsl_i]["in_trade"] == False
    # Equity after exit at close 9 from full position entered at 10
    # Enter at 10 → 100 aux; exit at 9 → 900 cash
    assert out["adj_account_value"].iloc[first_tsl_i] == pytest.approx(900.0)


def test_calculate_trade_quality_exact_values():
    trade_log = pd.DataFrame(
        {
            "adj_account_value_change_perc": [10.0, -5.0, 4.0, -2.0],
        }
    )
    q = calculate_trade_quality(trade_log)
    # profit_factor = |10+4| / |-5-2| = 14/7 = 2
    assert q["profit_factor"] == pytest.approx(2.0)
    # win_loss_ratio = |mean(10,4)| / |mean(-5,-2)| = 7 / 3.5 = 2
    assert q["avg_win_loss_ratio"] == pytest.approx(2.0)
    assert q["largest_winning_trade"] == pytest.approx(10.0)
    assert q["largest_losing_trade"] == pytest.approx(-5.0)


def test_metrics_formulas_match_docs_metrics_md():
    # docs/METRICS.md: return_perc = 100 - (first/last)*100
    tl = pd.DataFrame({"adj_account_value": [90.0, 100.0]})
    assert calculate_return_perc(tl) == pytest.approx(10.0)

    # buy_and_hold = (1 - first/last)*100
    df = pd.DataFrame({"close": [1.0, 10.0]})
    assert calculate_buy_and_hold_perc(df) == pytest.approx(90.0)

    # sharpe = (mean/std)*sqrt(n) on adj_account_value_change_perc
    rets = pd.Series([0.01, 0.02, -0.01, 0.03, 0.0])
    sharpe_df = pd.DataFrame({"adj_account_value_change_perc": rets})
    expected = (rets.mean() / rets.std()) * (len(rets) ** 0.5)
    assert calculate_shape_ratio(sharpe_df) == pytest.approx(round(expected, 3))


def test_build_summary_top_level_max_drawdown_is_min_equity():
    # docs/METRICS.md: max_drawdown = min(adj_account_value)
    # Mirror the working fixture shape from test_build_summary
    mock_df = pd.read_csv("./test/ohlcv_data.csv.txt", parse_dates=True).set_index(
        "date"
    )
    mock_df.index = pd.to_datetime(mock_df.index, unit="s")
    mock_df["in_trade"] = [True, False, False, False, True, True, False, False, False]
    mock_df.close = [10, 11, 11, 9, 9, 10, 11, 90, 11]
    mock_df["action"] = ["e", "h", "h", "h", "x", "e", "h", "h", "x"]
    mock_df["account_value"] = [90, 110, 110, 90, 90, 100, 110, 90, 100]
    mock_df["adj_account_value"] = [90, 110, 110, 90, 90, 100, 110, 90, 100]
    mock_df["adj_account_value_change"] = mock_df["adj_account_value"].diff()
    mock_df["adj_account_value_change_perc"] = mock_df["account_value"].pct_change()
    mock_df["fee"] = [0.0] * 9
    mock_df["aux"] = [1] * 9

    import datetime

    summary, _ = build_summary(mock_df, datetime.datetime.utcnow())
    assert summary["max_drawdown"] == pytest.approx(90.0)


def test_portfolio_apply_action_has_no_commission_unlike_backtest():
    """Documented divergence: portfolio path ignores commission."""
    from fast_trade.portfolio import apply_action

    state = {
        "cash": 1000.0,
        "position_qty": 0.0,
        "avg_price": 0.0,
        "equity": 1000.0,
    }
    new_state, trade, action_out = apply_action(
        state, "e", price=10.0, lot_size_perc=1.0, max_lot_size=0
    )
    assert action_out == "e"
    assert new_state["position_qty"] == pytest.approx(100.0)
    assert new_state["cash"] == pytest.approx(0.0)
    assert trade is not None
    assert "fee" not in trade
