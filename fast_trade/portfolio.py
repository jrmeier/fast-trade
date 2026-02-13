import json
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

from fast_trade.archive.db_helpers import _atomic_write_parquet, _safe_read_parquet


def portfolio_paths(name: str, archive_path: Optional[str] = None) -> Dict[str, str]:
    base_root = archive_path or os.getenv("ARCHIVE_PATH", "ft_archive")
    base = os.path.join(base_root, "portfolio", name)
    os.makedirs(base, exist_ok=True)
    return {
        "base": base,
        "state": os.path.join(base, "state.json"),
        "trades": os.path.join(base, "trades.parquet"),
        "log": os.path.join(base, "portfolio.log"),
        "pid": os.path.join(base, "runner.pid"),
    }


def load_state(path: str, default_state: dict) -> dict:
    if not os.path.exists(path):
        return default_state
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default_state


def save_state(path: str, state: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except Exception:
        pass


def append_log(path: str, line: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")
    except Exception:
        pass


def append_trades(trades_path: str, rows: List[dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    if os.path.exists(trades_path):
        existing = _safe_read_parquet(trades_path)
        if existing is None:
            merged = df
        else:
            merged = pd.concat([existing, df]).reset_index(drop=True)
        _atomic_write_parquet(merged, trades_path, index=False)
    else:
        _atomic_write_parquet(df, trades_path, index=False)


def apply_action(
    state: dict,
    action: str,
    price: float,
    lot_size_perc: float,
    max_lot_size: float,
) -> Tuple[dict, Optional[dict], str]:
    cash_bal = float(state.get("cash", 0.0))
    position_qty = float(state.get("position_qty", 0.0))
    avg_price = float(state.get("avg_price", 0.0))

    executed = None
    action_out = action

    if action in ["e", "ae"] and position_qty <= 0.0 and price > 0:
        notional = cash_bal * lot_size_perc
        if max_lot_size > 0:
            notional = min(notional, max_lot_size)
        qty = notional / price if price else 0.0
        if qty > 0:
            cash_bal -= qty * price
            position_qty = qty
            avg_price = price
            executed = {"side": "BUY", "qty": qty, "price": price, "notional": qty * price}
        else:
            action_out = "h"
    elif action in ["x", "ax", "tsl"] and position_qty > 0.0 and price > 0:
        cash_bal += position_qty * price
        executed = {"side": "SELL", "qty": position_qty, "price": price, "notional": position_qty * price}
        position_qty = 0.0
        avg_price = 0.0
    else:
        action_out = "h"

    equity = cash_bal + position_qty * price
    state = {**state}
    state["cash"] = round(cash_bal, 8)
    state["position_qty"] = round(position_qty, 8)
    state["avg_price"] = round(avg_price, 8)
    state["equity"] = round(equity, 8)

    return state, executed, action_out
