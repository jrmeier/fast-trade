import itertools
from typing import List

import pandas as pd


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


def can_vectorize_logic(df: pd.DataFrame, backtest: dict) -> bool:
    for logic_group in [
        backtest.get("enter", []),
        backtest.get("exit", []),
        backtest.get("any_enter", []),
        backtest.get("any_exit", []),
    ]:
        for logic in logic_group:
            if not (
                isinstance(logic[0], str)
                and logic[0] in df.columns
                and (
                    isinstance(logic[2], (int, float))
                    or (isinstance(logic[2], str) and logic[2] in df.columns)
                )
            ):
                return False
    return True


def build_mask(df: pd.DataFrame, logic_list: List, combine_any: bool) -> pd.Series:
    if not logic_list:
        return pd.Series(False, index=df.index)
    mask = pd.Series(True, index=df.index) if not combine_any else pd.Series(False, index=df.index)
    for logic in logic_list:
        if isinstance(logic[2], (int, float)):
            if logic[1] == ">":
                condition = df[logic[0]] > logic[2]
            elif logic[1] == "<":
                condition = df[logic[0]] < logic[2]
            elif logic[1] == "=":
                condition = df[logic[0]] == logic[2]
            elif logic[1] == "!=":
                condition = df[logic[0]] != logic[2]
            elif logic[1] == ">=":
                condition = df[logic[0]] >= logic[2]
            elif logic[1] == "<=":
                condition = df[logic[0]] <= logic[2]
            else:
                condition = pd.Series(False, index=df.index)
        elif logic[2] in df.columns:
            if logic[1] == ">":
                condition = df[logic[0]] > df[logic[2]]
            elif logic[1] == "<":
                condition = df[logic[0]] < df[logic[2]]
            elif logic[1] == "=":
                condition = df[logic[0]] == df[logic[2]]
            elif logic[1] == "!=":
                condition = df[logic[0]] != df[logic[2]]
            elif logic[1] == ">=":
                condition = df[logic[0]] >= df[logic[2]]
            elif logic[1] == "<=":
                condition = df[logic[0]] <= df[logic[2]]
            else:
                condition = pd.Series(False, index=df.index)
        else:
            condition = pd.Series(False, index=df.index)

        mask = mask | condition if combine_any else mask & condition
    return mask


def vectorized_actions(df: pd.DataFrame, backtest: dict) -> pd.Series:
    df_actions = pd.Series("h", index=df.index)
    exit_mask = build_mask(df, backtest.get("exit", []), combine_any=False)
    any_exit_mask = build_mask(df, backtest.get("any_exit", []), combine_any=True)
    enter_mask = build_mask(df, backtest.get("enter", []), combine_any=False)
    any_enter_mask = build_mask(df, backtest.get("any_enter", []), combine_any=True)

    tsl_mask = pd.Series(False, index=df.index)
    if backtest.get("trailing_stop_loss"):
        tsl_mask = df["close"] <= df["trailing_stop_loss"]

    df_actions.loc[tsl_mask] = "tsl"
    df_actions.loc[~tsl_mask & exit_mask] = "x"
    df_actions.loc[~tsl_mask & ~exit_mask & any_exit_mask] = "ax"
    df_actions.loc[~tsl_mask & ~exit_mask & ~any_exit_mask & enter_mask] = "e"
    df_actions.loc[
        ~tsl_mask & ~exit_mask & ~any_exit_mask & ~enter_mask & any_enter_mask
    ] = "ae"

    return df_actions
