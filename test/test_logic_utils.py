import pandas as pd

from fast_trade.logic_utils import (
    build_mask,
    can_vectorize_logic,
    max_last_frames,
    vectorized_actions,
)


def _sample_df():
    return pd.DataFrame(
        {
            "open": [1, 2, 3],
            "high": [2, 3, 4],
            "low": [0.5, 1.5, 2.5],
            "close": [1.5, 2.5, 3.5],
            "volume": [100, 200, 300],
            "signal": [0, 1, 2],
        },
        index=pd.date_range("2024-01-01", periods=3, freq="h"),
    )


def test_max_last_frames_returns_highest_lookback():
    backtest = {
        "enter": [["close", ">", 1, 2]],
        "exit": [["close", "<", 2, 5]],
        "any_enter": [],
        "any_exit": [["volume", ">", 0, 1]],
    }
    assert max_last_frames(backtest) == 5


def test_can_vectorize_logic_false_for_missing_column():
    df = _sample_df()
    backtest = {"enter": [["missing_col", ">", 1]], "exit": [], "any_enter": [], "any_exit": []}
    assert can_vectorize_logic(df, backtest) is False


def test_can_vectorize_logic_true_for_column_and_literal():
    df = _sample_df()
    backtest = {
        "enter": [["close", ">", "signal"]],
        "exit": [["close", "<", 10]],
        "any_enter": [],
        "any_exit": [],
    }
    assert can_vectorize_logic(df, backtest) is True


def test_build_mask_all_operators_and_branches():
    df = _sample_df()
    for op, fn in [
        (">", lambda a, b: a > b),
        ("<", lambda a, b: a < b),
        ("=", lambda a, b: a == b),
        ("!=", lambda a, b: a != b),
        (">=", lambda a, b: a >= b),
        ("<=", lambda a, b: a <= b),
    ]:
        mask = build_mask(df, [["close", op, 2.0]], combine_any=False)
        expected = fn(df["close"], 2.0)
        assert mask.equals(expected)

    col_mask = build_mask(df, [["close", ">", "signal"]], combine_any=False)
    assert col_mask.equals(df["close"] > df["signal"])

    unknown = build_mask(df, [["close", "~", 1]], combine_any=False)
    assert not unknown.any()

    missing_rhs = build_mask(df, [["close", ">", "nope"]], combine_any=False)
    assert not missing_rhs.any()

    empty = build_mask(df, [], combine_any=False)
    assert not empty.any()

    any_mask = build_mask(df, [["close", ">", 10], ["volume", ">", 50]], combine_any=True)
    assert any_mask.equals((df["close"] > 10) | (df["volume"] > 50))


def test_vectorized_actions_priority_and_any_enter():
    df = _sample_df()
    backtest = {
        "trailing_stop_loss": 0,
        "exit": [["close", "<", 0]],
        "any_exit": [["volume", ">", 5000]],
        "enter": [["close", ">", 100]],
        "any_enter": [["signal", ">", 0]],
    }
    actions = vectorized_actions(df, backtest)
    assert list(actions) == ["h", "ae", "ae"]
