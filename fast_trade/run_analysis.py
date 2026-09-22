"""Account-path simulation for vectorized backtests.

Hot path is ``_simulate_account_path``: a pure NumPy/Numba loop over action
codes. Intermediate ``round(..., 8)`` calls are intentionally avoided; cash /
aux / fee state uses float64 and output arrays are rounded once at the end so
callers still see 8-decimal columns without paying per-fill Python ``round``.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np
import polars as pl

try:
    from numba import njit

    _HAS_NUMBA = True
except ImportError:  # pragma: no cover - optional accel
    _HAS_NUMBA = False

    def njit(*args, **kwargs):  # type: ignore[misc]
        def wrap(fn):
            return fn

        if args and callable(args[0]):
            return args[0]
        return wrap


ACTION_HOLD = 0
ACTION_ENTER = 1
ACTION_EXIT = 2


def _encode_actions(actions: np.ndarray) -> np.ndarray:
    codes = np.zeros(len(actions), dtype=np.int8)
    enter_mask = (actions == "e") | (actions == "ae")
    exit_mask = (actions == "x") | (actions == "ax") | (actions == "tsl")
    codes[enter_mask] = ACTION_ENTER
    codes[exit_mask] = ACTION_EXIT
    return codes


@njit(cache=True)
def _simulate_account_path_kernel(  # pragma: no cover - executed via Numba
    action_codes: np.ndarray,
    close_prices: np.ndarray,
    base_balance: float,
    fee_rate: float,
    lot_size: float,
    max_lot_size: float,
):
    """Numba-friendly account path. No per-fill rounding."""
    n = len(action_codes)
    in_trade_array = np.zeros(n, dtype=np.bool_)
    account_value_array = np.zeros(n, dtype=np.float64)
    aux_array = np.zeros(n, dtype=np.float64)
    fee_array = np.zeros(n, dtype=np.float64)

    in_trade = False
    cash_value = base_balance
    aux_value = 0.0

    for i in range(n):
        close = close_prices[i]
        fee = 0.0
        action_code = action_codes[i]

        if action_code == ACTION_ENTER and not in_trade:
            base_transaction_amount = cash_value * lot_size
            if max_lot_size > 0.0 and base_transaction_amount > max_lot_size:
                base_transaction_amount = max_lot_size

            if base_transaction_amount and close != 0.0:
                aux_value = base_transaction_amount / close
            else:
                aux_value = 0.0
            if fee_rate and aux_value:
                fee = aux_value * fee_rate
                aux_value = aux_value - fee
            cash_value = cash_value - base_transaction_amount
            in_trade = True

        elif action_code == ACTION_EXIT and in_trade:
            if aux_value:
                base_value = aux_value * close
            else:
                base_value = 0.0
            if fee_rate and base_value:
                fee = base_value * fee_rate
            cash_value = cash_value + base_value - fee
            aux_value = 0.0
            in_trade = False

        account_value_array[i] = cash_value
        aux_array[i] = aux_value
        in_trade_array[i] = in_trade
        fee_array[i] = fee

    adj_account_value_array = account_value_array + aux_array * close_prices
    return (
        in_trade_array,
        account_value_array,
        aux_array,
        fee_array,
        adj_account_value_array,
    )


def _simulate_account_path_python(
    action_codes: np.ndarray,
    close_prices: np.ndarray,
    base_balance: float,
    fee_rate: float,
    lot_size: float,
    max_lot_size: float,
    progress_callback: Optional[Callable[[dict], Any]] = None,
):
    """Python fallback with optional progress reporting. No per-fill rounding."""
    n = len(action_codes)
    in_trade_array = np.zeros(n, dtype=bool)
    account_value_array = np.zeros(n, dtype=float)
    aux_array = np.zeros(n, dtype=float)
    fee_array = np.zeros(n, dtype=float)

    in_trade = False
    cash_value = float(base_balance)
    aux_value = 0.0
    update_every = max(1, n // 200) if n else 1
    max_lot = float(max_lot_size or 0.0)

    for i in range(n):
        close = float(close_prices[i])
        fee = 0.0
        action_code = int(action_codes[i])

        if action_code == ACTION_ENTER and not in_trade:
            base_transaction_amount = cash_value * lot_size
            if max_lot and base_transaction_amount > max_lot:
                base_transaction_amount = max_lot

            aux_value = (
                base_transaction_amount / close
                if base_transaction_amount and close
                else 0.0
            )
            if fee_rate and aux_value:
                fee = aux_value * fee_rate
                aux_value = aux_value - fee
            cash_value = cash_value - base_transaction_amount
            in_trade = True

        elif action_code == ACTION_EXIT and in_trade:
            base_value = aux_value * close if aux_value else 0.0
            if fee_rate and base_value:
                fee = base_value * fee_rate
            cash_value = cash_value + base_value - fee
            aux_value = 0.0
            in_trade = False

        account_value_array[i] = cash_value
        aux_array[i] = aux_value
        in_trade_array[i] = in_trade
        fee_array[i] = fee
        if progress_callback and (i % update_every == 0 or i == n - 1):
            progress_callback({"percent": int((i + 1) / n * 100)})

    adj_account_value_array = account_value_array + aux_array * close_prices
    return (
        in_trade_array,
        account_value_array,
        aux_array,
        fee_array,
        adj_account_value_array,
    )


def _simulate_account_path(
    action_codes: np.ndarray,
    close_prices: np.ndarray,
    base_balance: float,
    comission: float,
    lot_size: float,
    max_lot_size: float,
    progress_callback=None,
):
    fee_rate = comission / 100.0 if comission else 0.0
    max_lot = float(max_lot_size or 0.0)
    codes = np.ascontiguousarray(action_codes, dtype=np.int8)
    closes = np.ascontiguousarray(close_prices, dtype=np.float64)

    if _HAS_NUMBA and progress_callback is None:
        (
            in_trade_array,
            account_value_array,
            aux_array,
            fee_array,
            adj_account_value_array,
        ) = _simulate_account_path_kernel(
            codes,
            closes,
            float(base_balance),
            float(fee_rate),
            float(lot_size),
            max_lot,
        )
    else:
        (
            in_trade_array,
            account_value_array,
            aux_array,
            fee_array,
            adj_account_value_array,
        ) = _simulate_account_path_python(
            codes,
            closes,
            float(base_balance),
            float(fee_rate),
            float(lot_size),
            max_lot,
            progress_callback=progress_callback,
        )

    # Round once on outputs so public columns stay 8-decimal friendly without
    # paying Python ``round`` on every fill inside the loop.
    return {
        "in_trade": np.asarray(in_trade_array, dtype=bool),
        "account_value": np.round(account_value_array, 8),
        "aux": np.round(aux_array, 8),
        "fee": np.round(fee_array, 8),
        "adj_account_value": np.round(adj_account_value_array, 8),
    }


def append_exit_on_end_row(df: pl.DataFrame) -> pl.DataFrame:
    """Duplicate the last bar one second later so the closing trade has a row."""
    last_row = df.tail(1)

    if "date" in df.columns:
        if df.schema["date"].is_temporal():
            last_row = last_row.with_columns(pl.col("date") + pl.duration(seconds=1))
        else:
            last_row = last_row.with_columns(pl.col("date") + 1)

    return pl.concat([df, last_row], how="vertical")


def apply_logic_to_df(df: pl.DataFrame, backtest: dict, progress_callback=None):
    """Run the market simulation over a frame that already has actions.

    Datapoints and enter/exit actions are computed beforehand; this step only
    tracks cash, inventory, and fees along the action path.
    """
    try:
        base_balance = float(backtest.get("base_balance"))
        comission = float(backtest.get("comission") or 0.0)
        lot_size = float(backtest.get("lot_size_perc") or 1.0)
        max_lot_size = float(backtest.get("max_lot_size") or 0.0)

        actions = df["action"].to_numpy()
        close_prices = df["close"].to_numpy().astype(float)
        action_codes = _encode_actions(actions)
        sim = _simulate_account_path(
            action_codes=action_codes,
            close_prices=close_prices,
            base_balance=base_balance,
            comission=comission,
            lot_size=lot_size,
            max_lot_size=max_lot_size,
            progress_callback=progress_callback,
        )
        fee_rate = comission / 100.0 if comission else 0.0
        in_trade_array = sim["in_trade"]
        account_value_array = sim["account_value"]
        aux_array = sim["aux"]
        fee_array = sim["fee"]
        adj_account_value_array = sim["adj_account_value"]

        # Keep the input frame untouched until every column lines up, otherwise
        # a failure here would hand the fallback path an already-extended frame
        # and it would append the exit row a second time.
        sim_df = df
        if backtest.get("exit_on_end") and len(in_trade_array) and in_trade_array[-1]:
            close = close_prices[-1]
            new_base = aux_array[-1] * close if aux_array[-1] else 0.0
            fee = new_base * fee_rate if fee_rate and new_base else 0.0
            new_account_value = account_value_array[-1] + new_base - fee

            sim_df = append_exit_on_end_row(df)

            in_trade_array = np.append(in_trade_array, False)
            aux_array = np.append(aux_array, 0.0)
            account_value_array = np.append(
                account_value_array, round(new_account_value, 8)
            )
            fee_array = np.append(fee_array, round(fee, 8))
            adj_account_value = round(
                new_account_value + convert_aux_to_base(0.0, close), 8
            )
            adj_account_value_array = np.append(
                adj_account_value_array, adj_account_value
            )

        df = sim_df.with_columns(
            pl.Series("aux", aux_array),
            pl.Series("account_value", account_value_array),
            pl.Series("adj_account_value", adj_account_value_array),
            pl.Series("in_trade", in_trade_array),
            pl.Series("fee", fee_array),
        )

    except Exception:
        # Fall back to row-by-row processing if the simulation kernel fails
        in_trade = False
        account_value = float(backtest.get("base_balance"))
        comission = float(backtest.get("comission") or 0.0)
        lot_size = float(backtest.get("lot_size_perc") or 1.0)
        max_lot_size = float(backtest.get("max_lot_size") or 0.0)

        new_account_value = account_value

        aux = 0.0
        close = 0.0
        aux_list = []
        account_value_list = []
        in_trade_list = []
        fee_list = []
        adj_account_value_list = []

        total_rows = df.height
        update_every = max(1, total_rows // 200)
        for idx, row in enumerate(df.iter_rows(named=True)):
            close = row["close"]
            curr_action = row["action"]
            fee = 0.0

            if curr_action in ["e", "ae"] and not in_trade:
                [in_trade, aux, new_account_value, fee] = enter_position(
                    account_value_list,
                    lot_size,
                    account_value,
                    max_lot_size,
                    close,
                    comission,
                )

            if curr_action in ["x", "ax", "tsl"] and in_trade:
                [in_trade, aux, new_account_value, fee] = exit_position(
                    account_value_list, close, aux, comission
                )

            adj_account_value = new_account_value + convert_aux_to_base(aux, close)

            aux_list.append(aux)
            account_value_list.append(new_account_value)
            in_trade_list.append(in_trade)
            fee_list.append(fee)
            adj_account_value_list.append(adj_account_value)
            if progress_callback and (
                idx % update_every == 0 or idx == total_rows - 1
            ):
                progress_callback({"percent": int((idx + 1) / total_rows * 100)})

        if backtest.get("exit_on_end") and in_trade:
            [in_trade, aux, new_account_value, fee] = exit_position(
                account_value_list, close, aux, comission
            )

            df = append_exit_on_end_row(df)

            aux_list.append(aux)
            account_value_list.append(new_account_value)
            in_trade_list.append(in_trade)
            fee_list.append(fee)
            adj_account_value_list.append(
                new_account_value + convert_aux_to_base(aux, close)
            )

        df = df.with_columns(
            pl.Series("aux", aux_list, dtype=pl.Float64),
            pl.Series("account_value", account_value_list, dtype=pl.Float64),
            pl.Series("adj_account_value", adj_account_value_list, dtype=pl.Float64),
            pl.Series("in_trade", in_trade_list, dtype=pl.Boolean),
            pl.Series("fee", fee_list, dtype=pl.Float64),
        )

    return df


def enter_position(
    account_value_list, lot_size, account_value, max_lot_size, close, comission
):
    if len(account_value_list):
        base_transaction_amount = account_value_list[-1] * lot_size
    else:
        base_transaction_amount = account_value * lot_size

    if max_lot_size and base_transaction_amount > max_lot_size:
        base_transaction_amount = max_lot_size

    new_aux = convert_base_to_aux(base_transaction_amount, close)
    fee = calculate_fee(new_aux, comission)

    new_aux = new_aux - fee

    new_account_value = calculate_new_account_value_on_enter(
        base_transaction_amount, account_value_list, account_value
    )

    in_trade = True

    return [in_trade, new_aux, new_account_value, fee]


def exit_position(account_value_list, close, new_aux, comission):
    new_base = convert_aux_to_base(new_aux, close)
    fee = calculate_fee(new_base, comission)
    new_base = new_base - fee

    new_account_value = account_value_list[-1] + new_base

    new_aux = 0

    in_trade = False

    return [in_trade, new_aux, new_account_value, fee]


def convert_base_to_aux(new_base: float, close: float):
    if new_base:
        return round(new_base / close, 8)
    return 0.0


def convert_aux_to_base(new_aux: float, close: float):
    if new_aux:
        return round(new_aux * close, 8)
    return 0.0


def calculate_fee(order_size: float, comission: float):
    if comission:
        return round((order_size / 100) * comission, 8)

    return 0.0


def calculate_new_account_value_on_enter(
    base_transaction_amount, account_value_list, account_value
):
    if len(account_value_list):
        new_account_value = account_value_list[-1] - base_transaction_amount
    else:
        new_account_value = account_value - base_transaction_amount
    return round(new_account_value, 8)
