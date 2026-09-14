"""Coverage for Numba fallbacks and vectorized FinTA edge cases."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import polars as pl

from fast_trade import finta as finta_mod
from fast_trade.finta import TA
from fast_trade.run_analysis import (
    ACTION_ENTER,
    ACTION_EXIT,
    ACTION_HOLD,
    _encode_actions,
    _simulate_account_path,
    _simulate_account_path_python,
)


def _ohlcv(n: int = 40) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "open": np.linspace(100, 120, n),
            "high": np.linspace(101, 121, n),
            "low": np.linspace(99, 119, n),
            "close": np.linspace(100.5, 120.5, n),
            "volume": np.linspace(1000, 2000, n),
        }
    )


def test_window_np_accepts_ndarray_and_series():
    arr = np.array([1.0, 2.0, 3.0])
    out = finta_mod._window_np(arr)
    assert out.dtype == float
    assert list(out) == [1.0, 2.0, 3.0]
    # Series branch (line used by leftover rolling_map callers)
    series_out = finta_mod._window_np(pl.Series("x", [4.0, 5.0]))
    assert list(series_out) == [4.0, 5.0]


def test_simulate_python_fallback_and_progress():
    codes = np.array([ACTION_ENTER, ACTION_HOLD, ACTION_EXIT], dtype=np.int8)
    closes = np.array([10.0, 11.0, 12.0])
    seen = []

    def progress(payload):
        seen.append(payload["percent"])

    with patch("fast_trade.run_analysis._HAS_NUMBA", False):
        sim = _simulate_account_path(
            codes,
            closes,
            base_balance=1000.0,
            comission=0.1,
            lot_size=1.0,
            max_lot_size=0.0,
            progress_callback=progress,
        )
    assert sim["in_trade"][0]
    assert not sim["in_trade"][-1]
    assert seen  # progress fired

    # Direct python path with max lot + zero close enter
    codes2 = np.array([ACTION_ENTER, ACTION_EXIT], dtype=np.int8)
    closes2 = np.array([0.0, 10.0])
    sim2 = _simulate_account_path_python(
        codes2,
        closes2,
        base_balance=1000.0,
        fee_rate=0.0,
        lot_size=1.0,
        max_lot_size=50.0,
    )
    assert sim2[2][0] == 0.0  # aux stays 0 when close is 0


def test_linear_regression_short_and_empty_windows():
    df = _ohlcv(5)
    out = TA.LINEAR_REGRESSION(df, period=3)
    assert out.len() == 5

    # Early-window all-NaN hits empty-finite branch inside _lr_end
    nan_early = pl.DataFrame(
        {
            "open": [np.nan, np.nan, 1.0, 2.0, 3.0],
            "high": [np.nan, np.nan, 1.0, 2.0, 3.0],
            "low": [np.nan, np.nan, 1.0, 2.0, 3.0],
            "close": [np.nan, np.nan, 1.0, 2.0, 3.0],
            "volume": [np.nan, np.nan, 1.0, 2.0, 3.0],
        }
    )
    out2 = TA.LINEAR_REGRESSION(nan_early, period=3)
    assert out2.len() == 5
    # Polars stores np.nan from early all-null windows as null
    assert out2[0] is None or (isinstance(out2[0], float) and np.isnan(out2[0]))


def test_encode_actions_aliases():
    actions = np.array(["e", "ae", "h", "x", "ax", "tsl"])
    codes = _encode_actions(actions)
    assert codes.tolist() == [
        ACTION_ENTER,
        ACTION_ENTER,
        ACTION_HOLD,
        ACTION_EXIT,
        ACTION_EXIT,
        ACTION_EXIT,
    ]


def test_sar_psar_frama_kama_smoke():
    df = _ohlcv(60)
    assert TA.SAR(df).len() == 60
    assert "psar" in TA.PSAR(df).columns
    assert TA.FRAMA(df, period=16, batch=10).len() == 60
    assert TA.KAMA(df).len() == 60
    assert TA.CCI(df).len() == 60
    assert TA.WILLIAMS_FRACTAL(df).height == 60
