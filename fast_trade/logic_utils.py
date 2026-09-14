import itertools
from typing import List

import numpy as np
import polars as pl

_COMPARISONS = {
    ">": np.greater,
    "<": np.less,
    "=": np.equal,
    "!=": np.not_equal,
    ">=": np.greater_equal,
    "<=": np.less_equal,
}


def max_last_frames(backtest: dict) -> int:
    logics = [
        backtest.get("enter") or [],
        backtest.get("exit") or [],
        backtest.get("any_exit") or [],
        backtest.get("any_enter") or [],
    ]
    flat = list(itertools.chain(*logics))
    max_frames = 0
    for logic in flat:
        if len(logic) > 3 and logic[3] > max_frames:
            max_frames = logic[3]
    return max_frames


def can_vectorize_logic(df: pl.DataFrame, backtest: dict) -> bool:
    columns = df.columns
    for logic_group in [
        backtest.get("enter") or [],
        backtest.get("exit") or [],
        backtest.get("any_enter") or [],
        backtest.get("any_exit") or [],
    ]:
        for logic in logic_group:
            if not (
                isinstance(logic[0], str)
                and logic[0] in columns
                and (
                    isinstance(logic[2], (int, float))
                    or (isinstance(logic[2], str) and logic[2] in columns)
                )
            ):
                return False
    return True


def _column_values(df: pl.DataFrame, column: str) -> np.ndarray:
    """Column as a numpy array, with nulls surfacing as NaN like pandas."""
    return df[column].to_numpy()


def _mask_array(df: pl.DataFrame, logic_list: List, combine_any: bool) -> np.ndarray:
    height = df.height
    if not logic_list:
        return np.zeros(height, dtype=bool)

    columns = df.columns
    mask = np.zeros(height, dtype=bool) if combine_any else np.ones(height, dtype=bool)
    for logic in logic_list:
        left, operator_key, right = logic[0], logic[1], logic[2]
        compare = _COMPARISONS.get(operator_key)

        if compare is None or left not in columns:
            condition = np.zeros(height, dtype=bool)
        elif isinstance(right, (int, float)):
            condition = compare(_column_values(df, left), right)
        elif isinstance(right, str) and right in columns:
            condition = compare(_column_values(df, left), _column_values(df, right))
        else:
            condition = np.zeros(height, dtype=bool)

        condition = np.asarray(condition, dtype=bool)
        mask = mask | condition if combine_any else mask & condition

    return mask


def build_mask(df: pl.DataFrame, logic_list: List, combine_any: bool) -> pl.Series:
    return pl.Series("mask", _mask_array(df, logic_list, combine_any))


def vectorized_actions(df: pl.DataFrame, backtest: dict) -> pl.Series:
    height = df.height
    actions = np.full(height, "h", dtype="<U3")

    exit_mask = _mask_array(df, backtest.get("exit") or [], combine_any=False)
    any_exit_mask = _mask_array(df, backtest.get("any_exit") or [], combine_any=True)
    enter_mask = _mask_array(df, backtest.get("enter") or [], combine_any=False)
    any_enter_mask = _mask_array(df, backtest.get("any_enter") or [], combine_any=True)

    if backtest.get("trailing_stop_loss"):
        tsl_mask = _column_values(df, "close") <= _column_values(df, "trailing_stop_loss")
        tsl_mask = np.asarray(tsl_mask, dtype=bool)
    else:
        tsl_mask = np.zeros(height, dtype=bool)

    remaining = ~tsl_mask
    actions[tsl_mask] = "tsl"
    actions[remaining & exit_mask] = "x"
    remaining = remaining & ~exit_mask
    actions[remaining & any_exit_mask] = "ax"
    remaining = remaining & ~any_exit_mask
    actions[remaining & enter_mask] = "e"
    remaining = remaining & ~enter_mask
    actions[remaining & any_enter_mask] = "ae"

    return pl.Series("action", actions.tolist(), dtype=pl.String)
