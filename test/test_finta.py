"""Comprehensive coverage tests for fast_trade.finta.TA."""

import runpy

import numpy as np
import pandas as pd
import pytest

from fast_trade.finta import TA, inputvalidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_ohlc():
    """Small deterministic OHLC for hand-checkable assertions."""
    return pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0, 11.0, 10.0, 10.0],
            "high": [11.0, 12.0, 13.0, 12.0, 11.0, 11.0],
            "low": [9.0, 10.0, 11.0, 10.0, 9.0, 9.5],
            "close": [10.0, 11.0, 12.0, 11.0, 10.0, 10.0],
            "volume": [100, 200, 300, 250, 150, 150],
        },
        index=pd.date_range("2024-01-01", periods=6, freq="D"),
    )


@pytest.fixture
def ohlcv():
    """Larger synthetic OHLCV with enough history for long-period indicators."""
    np.random.seed(7)
    n = 260
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    trend = np.cumsum(np.random.randn(n) * 0.4)
    close = 100.0 + trend
    high = close + np.abs(np.random.randn(n)) * 0.8 + 0.2
    low = close - np.abs(np.random.randn(n)) * 0.8 - 0.2
    open_ = close + np.random.randn(n) * 0.15
    volume = np.random.randint(1000, 50000, size=n).astype(float)
    # branches: zero volume (EVWMA), flat close (OBV no_change)
    volume[5] = 0
    volume[6] = 0
    close[20] = close[19]
    close[21] = close[19]
    # reversal pattern for SAR / PSAR
    for i in range(40, 60):
        close[i] = close[i - 1] + (1 if i % 4 < 2 else -1.5)
        high[i] = max(open_[i], close[i]) + 0.5
        low[i] = min(open_[i], close[i]) - 0.5
    # fractal-friendly spike
    high[100] = high[99] + 5
    low[120] = low[119] - 5
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture
def uppercase_ohlc(simple_ohlc):
    return simple_ohlc.rename(columns=str.upper)


def _warmup_tail(series, min_finite=1):
    """Return tail values that should be finite after indicator warmup."""
    if isinstance(series, pd.DataFrame):
        tail = series.iloc[-10:]
        for col in tail.columns:
            finite = tail[col].dropna()
            assert len(finite) >= min_finite, f"{col} all NaN after warmup"
            assert np.isfinite(finite.iloc[-1])
        return tail
    finite = series.iloc[-10:].dropna()
    assert len(finite) >= min_finite, "all NaN after warmup"
    assert np.isfinite(finite.iloc[-1])
    return finite


# ---------------------------------------------------------------------------
# inputvalidator / decorator coverage
# ---------------------------------------------------------------------------

def test_inputvalidator_missing_column_raises():
    df = pd.DataFrame({"open": [1], "high": [1], "low": [1]})
    with pytest.raises(LookupError, match="close"):
        TA.SMA(df)


def test_inputvalidator_uppercase_columns_renamed(uppercase_ohlc):
    result = TA.SMA(uppercase_ohlc, period=3)
    assert len(result) == len(uppercase_ohlc)


def test_inputvalidator_custom_column_kwarg():
    df = pd.DataFrame(
        {"open": [1, 2, 3], "high": [2, 3, 4], "low": [0.5, 1.5, 2.5], "high_price": [2, 3, 4]}
    )
    result = TA.SMA(df, period=2, column="high_price")
    assert result.iloc[-1] == pytest.approx(3.5)


def test_inputvalidator_standalone_decorator():
    @inputvalidator(input_="ohlc")
    def dummy(ohlc):
        return ohlc

    df = pd.DataFrame({"OPEN": [1], "HIGH": [1], "LOW": [1], "CLOSE": [1]})
    out = dummy(df)
    assert "close" in out.columns


def test_finta_main_block(capsys):
    runpy.run_module("fast_trade.finta", run_name="__main__")
    captured = capsys.readouterr()
    assert "SMA" in captured.out


# ---------------------------------------------------------------------------
# Hand-checkable core indicators
# ---------------------------------------------------------------------------

def test_sma_hand_check(simple_ohlc):
    sma = TA.SMA(simple_ohlc, period=3)
    assert sma.iloc[2] == pytest.approx(11.0)  # (10+11+12)/3
    assert sma.iloc[4] == pytest.approx(11.0)  # (12+11+10)/3


def test_ema_finite_and_responsive(simple_ohlc):
    ema = TA.EMA(simple_ohlc, period=3)
    assert np.isfinite(ema.iloc[-1])
    assert ema.iloc[-1] != ema.iloc[0]


def test_rsi_bounded(simple_ohlc):
    rsi = TA.RSI(simple_ohlc, period=3)
    tail = rsi.dropna()
    assert tail.min() >= 0
    assert tail.max() <= 100
    assert len(tail) > 0


def test_macd_columns_and_values(simple_ohlc):
    macd = TA.MACD(simple_ohlc, period_fast=3, period_slow=5, signal=2)
    assert list(macd.columns) == ["MACD", "SIGNAL"]
    _warmup_tail(macd)


def test_bbands_ordering(simple_ohlc):
    bb = TA.BBANDS(simple_ohlc, period=3)
    row = bb.dropna().iloc[-1]
    assert row["BB_UPPER"] >= row["BB_MIDDLE"] >= row["BB_LOWER"]


def test_bbands_custom_ma(simple_ohlc):
    ma = TA.EMA(simple_ohlc, period=3)
    bb = TA.BBANDS(simple_ohlc, period=3, MA=ma)
    assert "BB_UPPER" in bb.columns
    _warmup_tail(bb)


# ---------------------------------------------------------------------------
# NotImplemented indicators
# ---------------------------------------------------------------------------

NOT_IMPLEMENTED = ["LWMA", "VIDYA", "ALMA", "MAMA", "SWI", "TMF"]


@pytest.mark.parametrize("method_name", NOT_IMPLEMENTED)
def test_not_implemented_raises(method_name, ohlcv):
    method = getattr(TA, method_name)
    with pytest.raises(NotImplementedError):
        if method_name == "LWMA":
            method(ohlcv, 9)
        else:
            method(ohlcv)


# ---------------------------------------------------------------------------
# Error / edge branches
# ---------------------------------------------------------------------------

def test_frama_requires_even_period(ohlcv):
    with pytest.raises(AssertionError):
        TA.FRAMA(ohlcv, period=15)


def test_rolling_max_missing_column(ohlcv):
    with pytest.raises(LookupError, match="missing"):
        TA.ROLLING_MAX(ohlcv.copy(), column="missing")


def test_rolling_min_missing_column(ohlcv):
    with pytest.raises(LookupError, match="missing"):
        TA.ROLLING_MIN(ohlcv.copy(), column="missing")


def test_sma_empty_dataframe():
    empty = pd.DataFrame(columns=["open", "high", "low", "close"])
    result = TA.SMA(empty, period=3)
    assert len(result) == 0


def test_linear_regression_short_window(simple_ohlc):
    lr = TA.LINEAR_REGRESSION(simple_ohlc, period=1)
    assert len(lr) == len(simple_ohlc)
    assert lr.iloc[0] == pytest.approx(simple_ohlc["close"].iloc[0])


def test_linear_regression_short_and_normal(simple_ohlc):
    lr = TA.LINEAR_REGRESSION(simple_ohlc, period=3)
    assert len(lr) == len(simple_ohlc)
    assert np.isfinite(lr.iloc[-1])


# ---------------------------------------------------------------------------
# All implemented indicators – shape / finite-after-warmup
# ---------------------------------------------------------------------------

INDICATOR_CALLS = [
    ("SMM", lambda df: TA.SMM(df, period=3)),
    ("SSMA", lambda df: TA.SSMA(df, period=3)),
    ("DEMA", lambda df: TA.DEMA(df, period=3)),
    ("TEMA", lambda df: TA.TEMA(df, period=3)),
    ("TRIMA", lambda df: TA.TRIMA(df, period=5)),
    ("TRIX", lambda df: TA.TRIX(df, period=5)),
    ("VAMA", lambda df: TA.VAMA(df, period=5)),
    ("ER", lambda df: TA.ER(df, period=5)),
    ("KAMA", lambda df: TA.KAMA(df, er=5, period=5, ema_fast=2, ema_slow=10)),
    ("ZLEMA", lambda df: TA.ZLEMA(df, period=5)),
    ("WMA", lambda df: TA.WMA(df, period=3)),
    ("HMA", lambda df: TA.HMA(df, period=9)),
    ("EVWMA", lambda df: TA.EVWMA(df, period=5)),
    ("VWAP", lambda df: TA.VWAP(df)),
    ("SMMA", lambda df: TA.SMMA(df, period=3)),
    ("FRAMA", lambda df: TA.FRAMA(df, period=16, batch=5)),
    ("PPO", lambda df: TA.PPO(df, period_fast=5, period_slow=10, signal=3)),
    ("VW_MACD", lambda df: TA.VW_MACD(df, period_fast=5, period_slow=10, signal=3)),
    ("EV_MACD", lambda df: TA.EV_MACD(df, period_fast=5, period_slow=10, signal=3)),
    ("MOM", lambda df: TA.MOM(df, period=3)),
    ("ROC", lambda df: TA.ROC(df, period=3)),
    ("VBM", lambda df: TA.VBM(df, roc_period=3, atr_period=5)),
    ("IFT_RSI", lambda df: TA.IFT_RSI(df, rsi_period=3, wma_period=3)),
    ("DYMI", lambda df: TA.DYMI(df)),
    ("TR", lambda df: TA.TR(df)),
    ("ATR", lambda df: TA.ATR(df, period=5)),
    ("SAR", lambda df: TA.SAR(df)),
    ("PSAR", lambda df: TA.PSAR(df)),
    ("MOBO", lambda df: TA.MOBO(df)),
    ("BBWIDTH", lambda df: TA.BBWIDTH(df, period=5)),
    ("PERCENT_B", lambda df: TA.PERCENT_B(df, period=5)),
    ("KC", lambda df: TA.KC(df, period=5, atr_period=5)),
    ("KC_custom_ma", lambda df: TA.KC(df, period=5, atr_period=5, MA=TA.EMA(df, 5))),
    ("DO", lambda df: TA.DO(df, upper_period=5, lower_period=3)),
    ("DMI", lambda df: TA.DMI(df, period=5)),
    ("ADX", lambda df: TA.ADX(df, period=5)),
    ("PIVOT", lambda df: TA.PIVOT(df)),
    ("PIVOT_FIB", lambda df: TA.PIVOT_FIB(df)),
    ("STOCH", lambda df: TA.STOCH(df, period=5)),
    ("STOCHD", lambda df: TA.STOCHD(df, period=3, stoch_period=5)),
    ("STOCHRSI", lambda df: TA.STOCHRSI(df, rsi_period=5, stoch_period=5)),
    ("WILLIAMS", lambda df: TA.WILLIAMS(df, period=5)),
    ("UO", lambda df: TA.UO(df)),
    ("AO", lambda df: TA.AO(df, slow_period=10, fast_period=3)),
    ("MI", lambda df: TA.MI(df, period=5)),
    ("BOP", lambda df: TA.BOP(df)),
    ("VORTEX", lambda df: TA.VORTEX(df, period=5)),
    ("KST", lambda df: TA.KST(df, r1=5, r2=8, r3=10, r4=12)),
    ("TSI", lambda df: TA.TSI(df, long=10, short=5, signal=3)),
    ("TP", lambda df: TA.TP(df)),
    ("ADL", lambda df: TA.ADL(df)),
    ("CHAIKIN", lambda df: TA.CHAIKIN(df)),
    ("MFI", lambda df: TA.MFI(df, period=5)),
    ("OBV", lambda df: TA.OBV(df)),
    ("WOBV", lambda df: TA.WOBV(df)),
    ("VZO", lambda df: TA.VZO(df, period=5)),
    ("PZO", lambda df: TA.PZO(df, period=5)),
    ("EFI", lambda df: TA.EFI(df, period=5)),
    ("CFI", lambda df: TA.CFI(df)),
    ("EBBP", lambda df: TA.EBBP(df)),
    ("EMV", lambda df: TA.EMV(df, period=5)),
    ("CCI", lambda df: TA.CCI(df, period=5)),
    ("COPP", lambda df: TA.COPP(df)),
    ("BASP", lambda df: TA.BASP(df, period=10)),
    ("BASPN", lambda df: TA.BASPN(df, period=10)),
    ("CMO", lambda df: TA.CMO(df, period=5)),
    ("CHANDELIER", lambda df: TA.CHANDELIER(df, short_period=5, long_period=5)),
    ("QSTICK", lambda df: TA.QSTICK(df, period=3)),
    ("WTO", lambda df: TA.WTO(df, channel_length=5, average_length=8)),
    ("FISH", lambda df: TA.FISH(df, period=5)),
    ("ICHIMOKU", lambda df: TA.ICHIMOKU(df, tenkan_period=5, kijun_period=10, senkou_period=15, chikou_period=5)),
    ("APZ", lambda df: TA.APZ(df, period=5)),
    ("APZ_custom_ma", lambda df: TA.APZ(df, period=5, MA=TA.EMA(df, 5))),
    ("SQZMI", lambda df: TA.SQZMI(df, period=5)),
    ("SQZMI_custom_ma", lambda df: TA.SQZMI(df, period=5, MA=TA.SMA(df, 5))),
    ("VPT", lambda df: TA.VPT(df)),
    ("FVE", lambda df: TA.FVE(df, period=5, factor=0.01)),
    ("VFI", lambda df: TA.VFI(df, period=20, smoothing_factor=3)),
    ("MSD", lambda df: TA.MSD(df, period=5)),
    ("STC", lambda df: TA.STC(df, period_fast=10, period_slow=20, k_period=5, d_period=3)),
    ("EVSTC", lambda df: TA.EVSTC(df, period_fast=5, period_slow=10, k_period=5, d_period=3)),
    ("WILLIAMS_FRACTAL", lambda df: TA.WILLIAMS_FRACTAL(df, period=2)),
    ("VC", lambda df: TA.VC(df, period=5)),
    ("WAVEPM", lambda df: TA.WAVEPM(df, period=5, lookback_period=20)),
    ("ROLLING_MAX", lambda df: TA.ROLLING_MAX(df, periods=5)),
    ("ROLLING_MIN", lambda df: TA.ROLLING_MIN(df, periods=5)),
    ("LINEAR_REGRESSION", lambda df: TA.LINEAR_REGRESSION(df, period=5)),
]


# Indicators whose output length differs from input length
LENGTH_OVERRIDES = {
    "DYMI": lambda n: n - 14,
    "QSTICK": lambda n, period=3: period,
}


@pytest.mark.parametrize("name,fn", INDICATOR_CALLS)
def test_indicator_runs(name, fn, ohlcv):
    data = ohlcv.copy()
    result = fn(data)
    assert result is not None
    if name in LENGTH_OVERRIDES:
        expected = LENGTH_OVERRIDES[name](len(ohlcv))
        assert len(result) == expected
    else:
        assert len(result) == len(ohlcv)
    _warmup_tail(result)


# ---------------------------------------------------------------------------
# Targeted branch coverage helpers
# ---------------------------------------------------------------------------

def test_dmi_directional_branches():
    """Craft rows that hit both DMI helper branches."""
    df = pd.DataFrame(
        {
            "open": [10, 10, 10, 10, 10, 10, 10],
            "high": [11, 12, 11, 10, 9, 8, 9],
            "low": [9, 9, 8, 9, 10, 11, 10],
            "close": [10, 11, 10, 9, 10, 9, 10],
            "volume": [100] * 7,
        },
        index=pd.date_range("2024-01-01", periods=7, freq="D"),
    )
    out = TA.DMI(df, period=3)
    assert "DI_PLUS" in out.columns
    assert "DI_MINUS" in out.columns


def test_mfi_pos_neg_branches(simple_ohlc):
    out = TA.MFI(simple_ohlc, period=3)
    assert out.dropna().between(0, 100).all()


def test_obv_all_change_types(ohlcv):
    out = TA.OBV(ohlcv.copy())
    assert out.iloc[-1] != 0


def test_fve_volume_shift_branches():
    df = pd.DataFrame(
        {
            "open": [100, 100, 100, 100, 100, 100],
            "high": [101, 102, 103, 104, 105, 106],
            "low": [99, 98, 97, 96, 95, 94],
            "close": [100.5, 101.5, 99.0, 100.0, 102.0, 97.0],
            "volume": [1000, 2000, 3000, 4000, 5000, 6000],
        },
        index=pd.date_range("2024-01-01", periods=6, freq="D"),
    )
    out = TA.FVE(df, period=3, factor=0.01)
    assert len(out) == 6


def test_vfi_multiplier_branches(ohlcv):
    out = TA.VFI(ohlcv, period=15, smoothing_factor=2, factor=0.001, vfactor=1.5)
    _warmup_tail(out)


def test_sqzmi_squeeze_states(simple_ohlc):
    on = TA.SQZMI(simple_ohlc, period=3)
    assert on.dtype == bool or on.dropna().isin([True, False]).all()


def test_kama_early_none_branch():
    df = pd.DataFrame(
        {
            "open": [1, 2],
            "high": [2, 3],
            "low": [0.5, 1.5],
            "close": [1.5, 2.5],
            "volume": [10, 20],
        },
        index=pd.date_range("2024-01-01", periods=2, freq="D"),
    )
    out = TA.KAMA(df, er=2, period=5, ema_fast=2, ema_slow=5)
    assert len(out) == 2


def test_sar_reversal_paths(ohlcv):
    out = TA.SAR(ohlcv)
    assert len(out) == len(ohlcv)
    assert out.notna().all()


def test_psar_bull_bear_paths(ohlcv):
    out = TA.PSAR(ohlcv)
    assert list(out.columns) == ["psar", "psarbull", "psarbear"]


def test_williams_fractal_detection(ohlcv):
    out = TA.WILLIAMS_FRACTAL(ohlcv, period=2)
    assert out["BearishFractal"].isin([0.0, 1.0, True, False]).any()
    assert out["BullishFractal"].isin([0.0, 1.0, True, False]).any()


def test_wavepm_tanh_branches(ohlcv):
    out = TA.WAVEPM(ohlcv, period=5, lookback_period=15)
    _warmup_tail(out)


def test_dymi_early_index_branch(ohlcv):
    out = TA.DYMI(ohlcv)
    assert len(out) == len(ohlcv) - 14


def test_vpt_and_chandelier(simple_ohlc):
    assert len(TA.VPT(simple_ohlc)) == len(simple_ohlc)
    ch = TA.CHANDELIER(simple_ohlc, short_period=3, long_period=3, k=2)
    assert "Long." in ch.columns


def test_adjust_false_variants(simple_ohlc):
    assert len(TA.EMA(simple_ohlc, period=3, adjust=False)) == len(simple_ohlc)
    assert len(TA.RSI(simple_ohlc, period=3, adjust=False)) == len(simple_ohlc)
    assert len(TA.DMI(simple_ohlc, period=3, adjust=False).columns) == 2


def test_indicator_count_matches_public_api():
    """Sanity: every callable public TA method is exercised."""
    public = {
        name
        for name in dir(TA)
        if not name.startswith("_") and callable(getattr(TA, name))
    }
    alias_map = {
        "KC_custom_ma": "KC",
        "SQZMI_custom_ma": "SQZMI",
        "APZ_custom_ma": "APZ",
    }
    covered = {alias_map.get(name, name) for name, _ in INDICATOR_CALLS}
    covered.update({"SMA", "EMA", "RSI", "MACD", "BBANDS"})
    covered.update(NOT_IMPLEMENTED)
    assert public == covered
