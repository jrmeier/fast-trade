import json

import pandas as pd

from fast_trade.portfolio import (
    append_trades,
    apply_action,
    load_state,
    portfolio_paths,
    save_state,
)


def test_portfolio_paths_respects_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    paths = portfolio_paths("demo")
    assert paths["base"].endswith("portfolio/demo")
    assert (tmp_path / "portfolio" / "demo").exists()
    assert paths["state"].endswith("state.json")
    assert paths["trades"].endswith("trades.parquet")
    assert paths["log"].endswith("portfolio.jsonl")
    assert paths["pid"].endswith("runner.pid")


def test_load_save_state_roundtrip(tmp_path):
    state_path = tmp_path / "state.json"
    default = {"cash": 100}
    loaded = load_state(str(state_path), default)
    assert loaded == default

    payload = {"cash": 123.45, "position_qty": 0.25}
    save_state(str(state_path), payload)
    reloaded = load_state(str(state_path), default)
    assert reloaded == payload
    # Ensure file is valid json
    with open(state_path, "r", encoding="utf-8") as fh:
        json.load(fh)


def test_append_trades_creates_and_appends(tmp_path):
    trades_path = tmp_path / "trades.parquet"
    rows1 = [{"ts": "t1", "side": "BUY", "price": 10.0, "qty": 1.0}]
    rows2 = [{"ts": "t2", "side": "SELL", "price": 11.0, "qty": 1.0}]

    append_trades(str(trades_path), rows1)
    df1 = pd.read_parquet(trades_path)
    assert len(df1) == 1

    append_trades(str(trades_path), rows2)
    df2 = pd.read_parquet(trades_path)
    assert len(df2) == 2
    assert list(df2["side"]) == ["BUY", "SELL"]


def test_append_trades_no_rows_no_file(tmp_path):
    trades_path = tmp_path / "trades.parquet"
    append_trades(str(trades_path), [])
    assert not trades_path.exists()


def test_apply_action_enter_and_exit():
    state = {"cash": 1000.0, "position_qty": 0.0, "avg_price": 0.0, "equity": 1000.0}
    updated, executed, action = apply_action(state, "e", 100.0, lot_size_perc=1.0, max_lot_size=0.0)
    assert action == "e"
    assert executed["side"] == "BUY"
    assert updated["position_qty"] == 10.0
    assert updated["cash"] == 0.0
    assert updated["equity"] == 1000.0

    updated2, executed2, action2 = apply_action(updated, "x", 110.0, lot_size_perc=1.0, max_lot_size=0.0)
    assert action2 == "x"
    assert executed2["side"] == "SELL"
    assert updated2["position_qty"] == 0.0
    assert updated2["cash"] == 1100.0
    assert updated2["equity"] == 1100.0


def test_apply_action_respects_max_lot_size():
    state = {"cash": 1000.0, "position_qty": 0.0, "avg_price": 0.0, "equity": 1000.0}
    updated, executed, action = apply_action(state, "e", 50.0, lot_size_perc=1.0, max_lot_size=100.0)
    assert action == "e"
    assert executed["notional"] == 100.0
    assert updated["position_qty"] == 2.0
    assert updated["cash"] == 900.0


def test_apply_action_hold_no_price():
    state = {"cash": 1000.0, "position_qty": 0.0, "avg_price": 0.0, "equity": 1000.0}
    updated, executed, action = apply_action(state, "e", 0.0, lot_size_perc=1.0, max_lot_size=0.0)
    assert action == "h"
    assert executed is None
    assert updated["cash"] == 1000.0
    assert updated["position_qty"] == 0.0


def test_load_state_invalid_json_returns_default(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text("{bad json", encoding="utf-8")
    default = {"cash": 1}
    loaded = load_state(str(state_path), default)
    assert loaded == default
