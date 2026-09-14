"""Optional Numba accelerators for stateful loops.

Falls back to plain Python when Numba is unavailable so installs stay light.
"""

from __future__ import annotations

import numpy as np

try:
    from numba import njit
except ImportError:  # pragma: no cover

    def njit(*args, **kwargs):  # type: ignore[misc]
        def wrap(fn):
            return fn

        if args and callable(args[0]):
            return args[0]
        return wrap


@njit(cache=True)
def sar_kernel(high: np.ndarray, low: np.ndarray, af: float, amax: float) -> np.ndarray:
    n = len(high)
    sig0 = True
    xpt0 = high[0]
    af0 = af
    hl_std = 0.0
    if n > 1:
        diffs = high - low
        mean = 0.0
        for i in range(n):
            mean += diffs[i]
        mean /= n
        var = 0.0
        for i in range(n):
            d = diffs[i] - mean
            var += d * d
        # pandas Series.std uses ddof=1
        hl_std = (var / (n - 1)) ** 0.5 if n > 1 else 0.0

    sar = np.empty(n, dtype=np.float64)
    sar[0] = low[0] - hl_std
    sar_prev = sar[0]

    for i in range(1, n):
        sig1 = sig0
        xpt1 = xpt0
        af1 = af0

        lmin = low[i - 1] if low[i - 1] < low[i] else low[i]
        lmax = high[i - 1] if high[i - 1] > high[i] else high[i]

        if sig1:
            sig0 = low[i] > sar_prev
            xpt0 = lmax if lmax > xpt1 else xpt1
        else:
            sig0 = high[i] >= sar_prev
            xpt0 = lmin if lmin < xpt1 else xpt1

        if sig0 == sig1:
            sari = sar_prev + (xpt1 - sar_prev) * af1
            af0 = amax if (af1 + af) > amax else (af1 + af)

            if sig0:
                af0 = af0 if xpt0 > xpt1 else af1
                sari = sari if sari < lmin else lmin
            else:
                af0 = af0 if xpt0 < xpt1 else af1
                sari = sari if sari > lmax else lmax
        else:
            af0 = af
            sari = xpt0

        sar[i] = sari
        sar_prev = sari

    return sar


@njit(cache=True)
def psar_kernel(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, iaf: float, maxaf: float
):
    length = len(close)
    psar = close.copy()
    psarbull = np.full(length, np.nan)
    psarbear = np.full(length, np.nan)
    bull = True
    af = iaf
    hp = high[0]
    lp = low[0]

    for i in range(2, length):
        if bull:
            psar[i] = psar[i - 1] + af * (hp - psar[i - 1])
        else:
            psar[i] = psar[i - 1] + af * (lp - psar[i - 1])

        reverse = False

        if bull:
            if low[i] < psar[i]:
                bull = False
                reverse = True
                psar[i] = hp
                lp = low[i]
                af = iaf
        else:
            if high[i] > psar[i]:
                bull = True
                reverse = True
                psar[i] = lp
                hp = high[i]
                af = iaf

        if not reverse:
            if bull:
                if high[i] > hp:
                    hp = high[i]
                    af = af + iaf if (af + iaf) < maxaf else maxaf
                if low[i - 1] < psar[i]:
                    psar[i] = low[i - 1]
                if low[i - 2] < psar[i]:
                    psar[i] = low[i - 2]
            else:
                if low[i] < lp:
                    lp = low[i]
                    af = af + iaf if (af + iaf) < maxaf else maxaf
                if high[i - 1] > psar[i]:
                    psar[i] = high[i - 1]
                if high[i - 2] > psar[i]:
                    psar[i] = high[i - 2]

        if bull:
            psarbull[i] = psar[i]
        else:
            psarbear[i] = psar[i]

    return psar, psarbull, psarbear


@njit(cache=True)
def frama_filter_kernel(close: np.ndarray, alp: np.ndarray, window: int) -> np.ndarray:
    filt = close.copy()
    n = len(close)
    for i in range(n):
        x = alp[i]
        if i < window:
            continue
        if x != x:  # NaN
            continue
        filt[i] = close[i] * x + (1.0 - x) * filt[i - 1]
    return filt


@njit(cache=True)
def kama_kernel(
    price: np.ndarray, sc: np.ndarray, sma_shift: np.ndarray
) -> np.ndarray:
    n = len(price)
    out = np.full(n, np.nan)
    started = False
    prev = 0.0
    for i in range(n):
        s_val = sc[i]
        ma_val = sma_shift[i]
        price_val = price[i]
        if started:
            prev = prev + s_val * (price_val - prev)
            out[i] = prev
        elif ma_val == ma_val:  # finite SMA seed
            prev = ma_val + s_val * (price_val - ma_val)
            out[i] = prev
            started = True
        else:
            out[i] = np.nan
    return out
