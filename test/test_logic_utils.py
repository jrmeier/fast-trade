import datetime

import polars as pl

from fast_trade.logic_utils import (
    build_mask,
    can_vectorize_logic,
    max_last_frames,
    vectorized_actions,
)


def _sample_df():
    start = datetime.datetime(2024, 1, 1)
    return pl.DataFrame(
        {
            "date": [start + datetime.timedelta(hours=i) for i in range(3)],
            "open": [1.0, 2.0, 3.0],
            "high": [2.0, 3.0, 4.0],
            "low": [0.5, 1.5, 2.5],
            "close": [1.5, 2.5, 3.5],
            "volume": [100, 200, 300],
            "signal": [0, 1, 2],
        }
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


def test_build_mask_returns_polars_boolean_series():
    df = _sample_df()
    mask = build_mask(df, [["close", ">", 2.0]], combine_any=False)

    assert isinstance(mask, pl.Series)
    assert mask.dtype == pl.Boolean
    assert len(mask) == df.height


def test_build_mask_all_operators_and_branches():
    df = _sample_df()
    for op, expected in [
        (">", (df["close"] > 2.0)),
        ("<", (df["close"] < 2.0)),
        ("=", (df["close"] == 2.0)),
        ("!=", (df["close"] != 2.0)),
        (">=", (df["close"] >= 2.0)),
        ("<=", (df["close"] <= 2.0)),
    ]:
        mask = build_mask(df, [["close", op, 2.0]], combine_any=False)
        assert mask.to_list() == expected.to_list()

    col_mask = build_mask(df, [["close", ">", "signal"]], combine_any=False)
    assert col_mask.to_list() == (df["close"] > df["signal"]).to_list()

    unknown = build_mask(df, [["close", "~", 1]], combine_any=False)
    assert not unknown.any()

    missing_rhs = build_mask(df, [["close", ">", "nope"]], combine_any=False)
    assert not missing_rhs.any()

    missing_lhs = build_mask(df, [["nope", ">", 1]], combine_any=False)
    assert not missing_lhs.any()

    empty = build_mask(df, [], combine_any=False)
    assert not empty.any()

    any_mask = build_mask(df, [["close", ">", 10], ["volume", ">", 50]], combine_any=True)
    assert any_mask.to_list() == ((df["close"] > 10) | (df["volume"] > 50)).to_list()


def test_build_mask_treats_nulls_as_false():
    df = _sample_df().with_columns(pl.Series("close", [1.5, None, 3.5]))
    mask = build_mask(df, [["close", ">", 1.0]], combine_any=False)

    assert mask.to_list() == [True, False, True]


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

    assert isinstance(actions, pl.Series)
    assert actions.dtype == pl.String
    assert actions.to_list() == ["h", "ae", "ae"]


def test_vectorized_actions_trailing_stop_loss_wins():
    df = _sample_df().with_columns(pl.Series("trailing_stop_loss", [2.0, 2.0, 2.0]))
    backtest = {
        "trailing_stop_loss": 0.1,
        "exit": [],
        "any_exit": [],
        "enter": [["close", ">", 0]],
        "any_enter": [],
    }
    actions = vectorized_actions(df, backtest)

    assert actions.to_list() == ["tsl", "e", "e"]
