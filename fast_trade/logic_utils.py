import itertools
from typing import Any, List

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


def frame_is_empty(frame: Any) -> bool:
    """True when a frame holds no rows.

    Accepts Polars frames and, while the rest of the library is still being
    ported, frames handed over by callers that have not been migrated yet.
    """
    if frame is None:
        return True
    if isinstance(frame, pl.DataFrame):
        return frame.height == 0

    is_empty = getattr(frame, "is_empty", None)
    if callable(is_empty):
        return bool(is_empty())

    empty = getattr(frame, "empty", None)
    if empty is not None:
        return bool(empty)

    return len(frame) == 0


def _index_is_datetime(index: Any) -> bool:
    dtype = getattr(index, "dtype", None)
    return getattr(dtype, "kind", "") == "M"


def to_polars_frame(frame: Any) -> pl.DataFrame:
    """Normalize a frame to Polars, keeping the date as an explicit column.

    Polars frames pass through untouched. Frames coming from modules that are
    still pandas based get their datetime index materialized as a `date` column.
    """
    if frame is None:
        return pl.DataFrame()
    if isinstance(frame, pl.DataFrame):
        return frame
    if isinstance(frame, pl.Series):
        return frame.to_frame()

    index = getattr(frame, "index", None)
    columns = getattr(frame, "columns", None)
    if index is None or columns is None:
        raise TypeError(f"Expected a Polars DataFrame, got {type(frame)!r}")

    if len(columns) == 0:
        return pl.DataFrame()
    if "date" in columns:
        return pl.from_pandas(frame.reset_index(drop=True))
    if _index_is_datetime(index):
        return pl.from_pandas(frame.rename_axis("date").reset_index())
    return pl.from_pandas(frame.reset_index(drop=True))


def max_last_frames(backtest: dict) -> int:
    logics = [
        backtest.get("enter", []),
        backtest.get("exit", []),
        backtest.get("any_exit", []),
        backtest.get("any_enter", []),
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
        backtest.get("enter", []),
        backtest.get("exit", []),
        backtest.get("any_enter", []),
        backtest.get("any_exit", []),
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

    exit_mask = _mask_array(df, backtest.get("exit", []), combine_any=False)
    any_exit_mask = _mask_array(df, backtest.get("any_exit", []), combine_any=True)
    enter_mask = _mask_array(df, backtest.get("enter", []), combine_any=False)
    any_enter_mask = _mask_array(df, backtest.get("any_enter", []), combine_any=True)

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
