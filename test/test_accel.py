"""Edge cases for the Numba-accelerated kernels in fast_trade._accel."""

import numpy as np
import polars as pl
import pytest

from fast_trade._accel import frama_filter_kernel, psar_kernel, sar_kernel
from fast_trade.finta import TA


def _clean_ohlc(n=40):
    idx = np.arange(n, dtype=np.float64)
    close = 100.0 + np.sin(idx / 3.0) * 5.0
    spread = 1.0 + np.abs(np.cos(idx / 5.0))
    return close + spread, close - spread, close


def test_sar_seed_std_ignores_nan_samples():
    """One NaN bar must not poison the whole series through the seed std."""
    high, low, _ = _clean_ohlc()
    high = high.copy()
    high[10] = np.nan

    sar = sar_kernel(high, low, 0.02, 0.2)

    assert np.isfinite(sar[0])
    assert np.all(np.isfinite(sar[:10]))


def test_sar_seed_std_skips_nan_like_pandas():
    high, low, _ = _clean_ohlc()
    high = high.copy()
    high[10] = np.nan

    sar = sar_kernel(high, low, 0.02, 0.2)
    # pandas Series.std() drops NaN and uses ddof=1 over what is left
    expected_std = np.nanstd(high - low, ddof=1)

    assert expected_std > 0
    assert sar[0] == pytest.approx(float(low[0]) - expected_std, rel=1e-9)


def test_sar_and_psar_kernels_handle_empty_input():
    empty = np.empty(0, dtype=np.float64)

    assert sar_kernel(empty, empty, 0.02, 0.2).shape == (0,)

    psar, psarbull, psarbear = psar_kernel(empty, empty, empty, 0.02, 0.2)
    assert psar.shape == psarbull.shape == psarbear.shape == (0,)


def test_frama_filter_propagates_nan_alpha():
    """A NaN alpha carries forward, matching the reference implementation."""
    close = np.arange(1.0, 11.0)
    alp = np.full(10, 0.5)
    alp[5] = np.nan

    filt = frama_filter_kernel(close, alp, window=2)

    assert np.isfinite(filt[4])
    assert np.all(np.isnan(filt[5:]))


def test_sar_on_frame_with_nan_bar_keeps_early_values():
    high, low, close = _clean_ohlc()
    high = high.copy()
    high[15] = np.nan
    df = pl.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": close}
    )

    sar = TA.SAR(df)

    assert np.isfinite(sar.to_numpy()[:15]).all()
