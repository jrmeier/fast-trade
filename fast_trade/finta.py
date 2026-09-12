from functools import wraps
from typing import Any, Optional

import numpy as np
import polars as pl


def _is_dataframe(obj: Any) -> bool:
    return isinstance(obj, pl.DataFrame)


def _is_series_like(obj: Any) -> bool:
    return isinstance(obj, pl.Series)


def _as_pl_series(values: Any, name: str = "") -> pl.Series:
    """Normalize values to a Polars Series, converting float NaN to null for ewm parity."""
    if isinstance(values, pl.Expr):
        raise TypeError("Expected Series/array, got polars Expr")
    if isinstance(values, pl.Series):
        s = values
    else:
        s = pl.Series(name, values)
    # Pandas ewm treats leading NaN like missing; Polars needs null (not NaN)
    if s.dtype in (pl.Float32, pl.Float64):
        s = s.fill_nan(None)
    return s


def _series_out(values: Any, name: Optional[str]) -> pl.Series:
    """Convert computed values to a Polars Series."""
    if isinstance(values, pl.Expr):
        raise TypeError("Expected Series/array, got polars Expr")
    if isinstance(values, pl.Series):
        s = values
    else:
        s = pl.Series("" if name is None else name, values)
    if name is not None:
        s = s.alias(name)
    if s.dtype in (pl.Float32, pl.Float64):
        s = s.fill_nan(None)
    return s


def _frame_out(data: Any) -> pl.DataFrame:
    """Convert computed columns to a Polars DataFrame."""
    if isinstance(data, pl.DataFrame):
        return data
    return pl.DataFrame(data)


def _col(df: pl.DataFrame, name: str) -> pl.Series:
    return df.get_column(name)


def _to_np(series: Any) -> np.ndarray:
    if isinstance(series, pl.Series):
        return series.to_numpy()
    return np.asarray(series, dtype=float)


def _window_np(x: Any) -> np.ndarray:
    """Convert rolling_map window (polars Series) to float ndarray."""
    if isinstance(x, pl.Series):
        return x.to_numpy()
    return np.asarray(x, dtype=float)


def _ewm_mean(
    series: Any,
    *,
    span: Optional[float] = None,
    alpha: Optional[float] = None,
    com: Optional[float] = None,
    adjust: bool = True,
    min_periods: int = 1,
) -> pl.Series:
    """EMA matching pandas ewm(...).mean() with ignore_nulls=False."""
    s = _as_pl_series(series)
    kwargs = {
        "adjust": adjust,
        "ignore_nulls": False,
        "min_samples": min_periods,
    }
    if alpha is not None:
        return s.ewm_mean(alpha=alpha, **kwargs)
    if com is not None:
        return s.ewm_mean(com=com, **kwargs)
    if span is not None:
        return s.ewm_mean(span=span, **kwargs)
    raise ValueError("span, alpha, or com required")


def _rolling_mean(series: Any, period: int, min_periods: Optional[int] = None) -> pl.Series:
    s = _as_pl_series(series)
    mp = period if min_periods is None else min_periods
    return s.rolling_mean(window_size=period, min_samples=mp)


def _rolling_min(series: Any, period: int, min_periods: Optional[int] = None) -> pl.Series:
    s = _as_pl_series(series)
    mp = period if min_periods is None else min_periods
    return s.rolling_min(window_size=period, min_samples=mp)


def _rolling_max(series: Any, period: int, min_periods: Optional[int] = None) -> pl.Series:
    s = _as_pl_series(series)
    mp = period if min_periods is None else min_periods
    return s.rolling_max(window_size=period, min_samples=mp)


def _rolling_std(
    series: Any, period: int, min_periods: Optional[int] = None, ddof: int = 1
) -> pl.Series:
    s = _as_pl_series(series)
    mp = period if min_periods is None else min_periods
    return s.rolling_std(window_size=period, min_samples=mp, ddof=ddof)


def _rolling_sum(series: Any, period: int, min_periods: Optional[int] = None) -> pl.Series:
    s = _as_pl_series(series)
    mp = period if min_periods is None else min_periods
    return s.rolling_sum(window_size=period, min_samples=mp)


def _rolling_median(series: Any, period: int, min_periods: Optional[int] = None) -> pl.Series:
    s = _as_pl_series(series)
    mp = period if min_periods is None else min_periods
    return s.rolling_median(window_size=period, min_samples=mp)


def _shift(series: Any, n: int = 1) -> pl.Series:
    s = _as_pl_series(series)
    return s.shift(n)


def _diff(series: Any, n: int = 1) -> pl.Series:
    s = _as_pl_series(series)
    return s.diff(n)


def _wma(series: Any, period: int) -> pl.Series:
    """Weighted moving average matching pandas rolling.apply with linear weights."""
    s = _as_pl_series(series)
    weights = np.arange(1, period + 1, dtype=float)
    d = (period * (period + 1)) / 2.0

    def _compute(x) -> float:
        arr = _window_np(x)
        return float((weights * arr).sum() / d)

    return s.rolling_map(_compute, window_size=period, min_samples=period)


def _ensure_ma(MA: Any, length: int) -> Optional[np.ndarray]:
    """Normalize optional MA override to numpy values, or None to use default."""
    if MA is None:
        return None
    if isinstance(MA, pl.Series):
        return MA.to_numpy()
    return None


def inputvalidator(input_="ohlc"):
    def dfcheck(func):
        @wraps(func)
        def wrap(*args, **kwargs):

            args = list(args)
            i = 0 if _is_dataframe(args[0]) else 1

            df = args[i]
            if not isinstance(df, pl.DataFrame):
                raise TypeError("Expected polars DataFrame")
            args[i] = df.rename({c: c.lower() for c in df.columns})

            inputs = {
                "o": "open",
                "h": "high",
                "l": "low",
                "c": kwargs.get("column", "close").lower(),
                "v": "volume",
            }

            if inputs["c"] != "close":
                kwargs["column"] = inputs["c"]

            cols = set(args[i].columns)
            for l in input_:
                if inputs[l] not in cols:
                    raise LookupError(
                        'Must have a dataframe column named "{0}"'.format(inputs[l])
                    )

            return func(*args, **kwargs)

        return wrap

    return dfcheck


def apply(decorator):
    def decorate(cls):
        for attr in cls.__dict__:
            if callable(getattr(cls, attr)):
                setattr(cls, attr, decorator(getattr(cls, attr)))

        return cls

    return decorate


@apply(inputvalidator(input_="ohlc"))
class TA:

    __version__ = "1.3"

    @classmethod
    def SMA(cls, ohlc: pl.DataFrame, period: int = 41, column: str = "close") -> pl.Series:
        """
        Simple moving average - rolling mean in pandas lingo. Also known as 'MA'.
        The simple moving average (SMA) is the most basic of the moving averages used for trading.
        """
        pl_df = ohlc
        result = _rolling_mean(_col(pl_df, column), period)
        return _series_out(result, "{0} period SMA".format(period))

    @classmethod
    def SMM(cls, ohlc: pl.DataFrame, period: int = 9, column: str = "close") -> pl.Series:
        """
        Simple moving median, an alternative to moving average. SMA, when used to estimate the underlying trend in a time series,
        is susceptible to rare events such as rapid shocks or other anomalies. A more robust estimate of the trend is the simple moving median over n time periods.
        """
        pl_df = ohlc
        result = _rolling_median(_col(pl_df, column), period)
        return _series_out(result, "{0} period SMM".format(period))

    @classmethod
    def SSMA(
        cls,
        ohlc: pl.DataFrame,
        period: int = 9,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """
        Smoothed simple moving average.

        :param ohlc: data
        :param period: range
        :param column: open/close/high/low column of the DataFrame
        :return: result Series
        """
        pl_df = ohlc
        result = _ewm_mean(
            _col(pl_df, column), alpha=1.0 / period, min_periods=0, adjust=adjust
        )
        return _series_out(result, "{0} period SSMA".format(period))

    @classmethod
    def EMA(
        cls,
        ohlc: pl.DataFrame,
        period: int = 9,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """
        Exponential Weighted Moving Average - Like all moving average indicators, they are much better suited for trending markets.
        When the market is in a strong and sustained uptrend, the EMA indicator line will also show an uptrend and vice-versa for a down trend.
        EMAs are commonly used in conjunction with other indicators to confirm significant market moves and to gauge their validity.
        """
        pl_df = ohlc
        result = _ewm_mean(_col(pl_df, column), span=period, adjust=adjust)
        return _series_out(result, "{0} period EMA".format(period))

    @classmethod
    def DEMA(
        cls,
        ohlc: pl.DataFrame,
        period: int = 9,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """
        Double Exponential Moving Average - attempts to remove the inherent lag associated to Moving Averages
         by placing more weight on recent values. The name suggests this is achieved by applying a double exponential
        smoothing which is not the case. The name double comes from the fact that the value of an EMA (Exponential Moving Average) is doubled.
        To keep it in line with the actual data and to remove the lag the value 'EMA of EMA' is subtracted from the previously doubled EMA.
        Because EMA(EMA) is used in the calculation, DEMA needs 2 * period -1 samples to start producing values in contrast to the period
        samples needed by a regular EMA
        """
        pl_df = ohlc
        # Match pandas ref: EMA uses default column "close" (column arg unused)
        ema = cls.EMA(pl_df, period, adjust=adjust)
        dema = 2 * ema - _ewm_mean(ema, span=period, adjust=adjust)
        return _series_out(dema, "{0} period DEMA".format(period))

    @classmethod
    def TEMA(cls, ohlc: pl.DataFrame, period: int = 9, adjust: bool = True) -> pl.Series:
        """
        Triple exponential moving average - attempts to remove the inherent lag associated to Moving Averages by placing more weight on recent values.
        The name suggests this is achieved by applying a triple exponential smoothing which is not the case. The name triple comes from the fact that the
        value of an EMA (Exponential Moving Average) is triple.
        To keep it in line with the actual data and to remove the lag the value 'EMA of EMA' is subtracted 3 times from the previously tripled EMA.
        Finally 'EMA of EMA of EMA' is added.
        Because EMA(EMA(EMA)) is used in the calculation, TEMA needs 3 * period - 2 samples to start producing values in contrast to the period samples
        needed by a regular EMA.
        """
        pl_df = ohlc
        ema = cls.EMA(pl_df, period, adjust=adjust)
        ema2 = _ewm_mean(ema, span=period, adjust=adjust)
        ema3 = _ewm_mean(ema2, span=period, adjust=adjust)
        tema = 3 * ema - 3 * ema2 + ema3
        return _series_out(tema, "{0} period TEMA".format(period))

    @classmethod
    def TRIMA(cls, ohlc: pl.DataFrame, period: int = 18) -> pl.Series:
        """
        The Triangular Moving Average (TRIMA) [also known as TMA] represents an average of prices,
        but places weight on the middle prices of the time period.
        The calculations double-smooth the data using a window width that is one-half the length of the series.
        source: https://www.thebalance.com/triangular-moving-average-tma-description-and-uses-1031203
        """
        pl_df = ohlc
        sma = cls.SMA(pl_df, period)
        result = _rolling_sum(sma, period) / period
        return _series_out(result, "{0} period TRIMA".format(period))

    @classmethod
    def TRIX(
        cls,
        ohlc: pl.DataFrame,
        period: int = 20,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """
        The TRIX indicator calculates the rate of change of a triple exponential moving average.
        The values oscillate around zero. Buy/sell signals are generated when the TRIX crosses above/below zero.
        A (typically) 9 period exponential moving average of the TRIX can be used as a signal line.
        A buy/sell signals are generated when the TRIX crosses above/below the signal line and is also above/below zero.

        The TRIX was developed by Jack K. Hutson, publisher of Technical Analysis of Stocks & Commodities magazine,
        and was introduced in Volume 1, Number 5 of that magazine.
        """
        pl_df = ohlc
        data = _col(pl_df, column)

        def _ema(data, period, adjust):
            return _ewm_mean(data, span=period, adjust=adjust)

        m = _ema(_ema(_ema(data, period, adjust), period, adjust), period, adjust)
        result = 100 * (_diff(m) / m)
        return _series_out(result, "{0} period TRIX".format(period))

    @classmethod
    def LWMA(cls, ohlc: pl.DataFrame, period: int, column: str = "close") -> pl.Series:
        """
        Linear Weighted Moving Average
        """
        raise NotImplementedError

    @classmethod
    @inputvalidator(input_="ohlcv")
    def VAMA(cls, ohlcv: pl.DataFrame, period: int = 8, column: str = "close") -> pl.Series:
        """
        Volume Adjusted Moving Average
        """
        pl_df = ohlcv
        vp = _col(pl_df, "volume") * _col(pl_df, column)
        volsum = _rolling_mean(_col(pl_df, "volume"), period)
        vol_ratio = vp / volsum
        cum_sum = _rolling_sum(vol_ratio * _col(pl_df, column), period)
        cum_div = _rolling_sum(vol_ratio, period)
        return _series_out(
            cum_sum / cum_div, "{0} period VAMA".format(period)
        )

    @classmethod
    @inputvalidator(input_="ohlcv")
    def VIDYA(
        cls,
        ohlcv: pl.DataFrame,
        period: int = 9,
        smoothing_period: int = 12,
        column: str = "close",
    ) -> pl.Series:
        """Vidya (variable index dynamic average) indicator is a modification of the traditional Exponential Moving Average (EMA) indicator.
        The main difference between EMA and Vidya is in the way the smoothing factor F is calculated.
        In EMA the smoothing factor is a constant value F=2/(period+1);
        in Vidya the smoothing factor is variable and depends on bar-to-bar price movements.
        """
        raise NotImplementedError

    @classmethod
    def ER(cls, ohlc: pl.DataFrame, period: int = 10, column: str = "close") -> pl.Series:
        """The Kaufman Efficiency indicator is an oscillator indicator that oscillates between +100 and -100, where zero is the center point.
        +100 is upward forex trending market and -100 is downwards trending markets."""
        pl_df = ohlc
        change = _diff(_col(pl_df, column), period).abs()
        volatility = _rolling_sum(_diff(_col(pl_df, column)).abs(), period)
        return _series_out(
            change / volatility, "{0} period ER".format(period)
        )

    @classmethod
    def KAMA(
        cls,
        ohlc: pl.DataFrame,
        er: int = 10,
        ema_fast: int = 2,
        ema_slow: int = 30,
        period: int = 20,
        column: str = "close",
    ) -> pl.Series:
        """Developed by Perry Kaufman, Kaufman's Adaptive Moving Average (KAMA) is a moving average designed to account for market noise or volatility.
        Its main advantage is that it takes into consideration not just the direction, but the market volatility as well.
        """
        pl_df = ohlc
        er_s = cls.ER(pl_df, er, column=column)
        fast_alpha = 2 / (ema_fast + 1)
        slow_alpha = 2 / (ema_slow + 1)
        sc = (er_s * (fast_alpha - slow_alpha) + slow_alpha) ** 2
        sma = _rolling_mean(_col(pl_df, column), period)
        price = _col(pl_df, column)

        sc_arr = _to_np(sc)
        sma_arr = _to_np(sma)
        price_arr = _to_np(price)
        sma_shift = np.roll(sma_arr, 1)
        sma_shift[0] = np.nan

        kama = []
        for i in range(len(price_arr)):
            s_val = sc_arr[i]
            ma_val = sma_shift[i]
            price_val = price_arr[i]
            try:
                kama.append(kama[-1] + s_val * (price_val - kama[-1]))
            except (IndexError, TypeError):
                if ma_val == ma_val:  # not NaN
                    kama.append(ma_val + s_val * (price_val - ma_val))
                else:
                    kama.append(None)

        return _series_out(
            kama, "{0} period KAMA.".format(period)
        )

    @classmethod
    def ZLEMA(
        cls,
        ohlc: pl.DataFrame,
        period: int = 26,
        adjust: bool = True,
        column: str = "close",
    ) -> pl.Series:
        """ZLEMA is an abbreviation of Zero Lag Exponential Moving Average. It was developed by John Ehlers and Rick Way.
        ZLEMA is a kind of Exponential moving average but its main idea is to eliminate the lag arising from the very nature of the moving averages
        and other trend following indicators. As it follows price closer, it also provides better price averaging and responds better to price swings.
        """
        pl_df = ohlc
        lag = (period - 1) / 2
        # Polars Series.diff(lag) truncates lag to int
        lag_n = int(lag)
        ema = _col(pl_df, column) + _diff(_col(pl_df, column), lag_n)
        zlema = _ewm_mean(ema, span=period, adjust=adjust)
        return _series_out(zlema, "{0} period ZLEMA".format(period))

    @classmethod
    def WMA(cls, ohlc: pl.DataFrame, period: int = 9, column: str = "close") -> pl.Series:
        """
        WMA stands for weighted moving average. It helps to smooth the price curve for better trend identification.
        It places even greater importance on recent data than the EMA does.

        :period: Specifies the number of Periods used for WMA calculation
        """
        pl_df = ohlc
        wma = _wma(_col(pl_df, column), period)
        return _series_out(wma, "{0} period WMA.".format(period))

    @classmethod
    def HMA(cls, ohlc: pl.DataFrame, period: int = 16) -> pl.Series:
        """
        HMA indicator is a common abbreviation of Hull Moving Average.
        The average was developed by Allan Hull and is used mainly to identify the current market trend.
        Unlike SMA (simple moving average) the curve of Hull moving average is considerably smoother.
        Moreover, because its aim is to minimize the lag between HMA and price it does follow the price activity much closer.
        It is used especially for middle-term and long-term trading.
        :period: Specifies the number of Periods used for WMA calculation
        """
        import math

        pl_df = ohlc
        half_length = int(period / 2)
        sqrt_length = int(math.sqrt(period))

        wmaf = cls.WMA(pl_df, period=half_length)
        wmas = cls.WMA(pl_df, period=period)
        deltawma = 2 * wmaf - wmas
        # Build temp frame with deltawma column for WMA
        tmp = pl_df.with_columns(deltawma.alias("deltawma"))
        hma = cls.WMA(tmp, column="deltawma", period=sqrt_length)
        return _series_out(hma, "{0} period HMA.".format(period))

    @classmethod
    @inputvalidator(input_="ohlcv")
    def EVWMA(cls, ohlcv: pl.DataFrame, period: int = 20) -> pl.Series:
        """
        The eVWMA can be looked at as an approximation to the
        average price paid per share in the last n periods.

        :period: Specifies the number of Periods used for eVWMA calculation
        """
        pl_df = ohlcv
        vol_sum = _rolling_sum(_col(pl_df, "volume"), period)
        x = (vol_sum - _col(pl_df, "volume")) / vol_sum
        y = (_col(pl_df, "volume") * _col(pl_df, "close")) / vol_sum

        x_arr = _to_np(x.fill_null(0))
        y_arr = _to_np(y)
        # Match pandas: fillna(0) on x only
        x_arr = np.nan_to_num(x_arr, nan=0.0)

        evwma = [0]
        for xv, yv in zip(x_arr, y_arr):
            if xv == 0 or yv == 0 or (isinstance(yv, float) and yv != yv):
                evwma.append(0)
            else:
                evwma.append(evwma[-1] * xv + yv)

        return _series_out(
            evwma[1:], "{0} period EVWMA.".format(period)
        )

    @classmethod
    @inputvalidator(input_="ohlcv")
    def VWAP(cls, ohlcv: pl.DataFrame) -> pl.Series:
        """
        The volume weighted average price (VWAP) is a trading benchmark used especially in pension plans.
        VWAP is calculated by adding up the dollars traded for every transaction (price multiplied by number of shares traded) and then dividing
        by the total shares traded for the day.
        """
        pl_df = ohlcv
        tp = cls.TP(pl_df)
        vol = _col(pl_df, "volume")
        result = (vol * tp).cum_sum() / vol.cum_sum()
        return _series_out(result, "VWAP.")

    @classmethod
    def SMMA(
        cls,
        ohlc: pl.DataFrame,
        period: int = 42,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """The SMMA (Smoothed Moving Average) gives recent prices an equal weighting to historic prices."""
        pl_df = ohlc
        result = _ewm_mean(_col(pl_df, column), alpha=1 / period, adjust=adjust)
        return _series_out(result, "SMMA")

    @classmethod
    def ALMA(
        cls, ohlc: pl.DataFrame, period: int = 9, sigma: int = 6, offset: int = 0.85
    ) -> pl.Series:
        """Arnaud Legoux Moving Average."""
        raise NotImplementedError

    @classmethod
    def MAMA(cls, ohlc: pl.DataFrame, period: int = 16) -> pl.Series:
        """MESA Adaptive Moving Average"""
        raise NotImplementedError

    @classmethod
    def FRAMA(cls, ohlc: pl.DataFrame, period: int = 16, batch: int = 10) -> pl.Series:
        """Fractal Adaptive Moving Average
        Source: http://www.stockspotter.com/Files/frama.pdf
        Adopted from: https://www.quantopian.com/posts/frama-fractal-adaptive-moving-average-in-python

        :period: Specifies the number of periods used for FRANA calculation
        :batch: Specifies the size of batches used for FRAMA calculation
        """
        assert period % 2 == 0, print("FRAMA period must be even")

        pl_df = ohlc
        c = _col(pl_df, "close")
        window = batch * 2

        hh = _rolling_max(c, batch)
        ll = _rolling_min(c, batch)
        n1 = (hh - ll) / batch
        n2 = _shift(n1, batch)

        hh2 = _rolling_max(c, window)
        ll2 = _rolling_min(c, window)
        n3 = (hh2 - ll2) / window

        n1_a = _to_np(n1)
        n2_a = _to_np(n2)
        n3_a = _to_np(n3)
        with np.errstate(divide="ignore", invalid="ignore"):
            D = (np.log(n1_a + n2_a) - np.log(n3_a)) / np.log(2)
            alp = np.clip(np.exp(-4.6 * (D - 1)), 0.01, 1)

        filt = _to_np(c).copy()
        for i, x in enumerate(alp):
            cl = filt[i]
            if i < window:
                continue
            if x != x:  # NaN alpha
                continue
            filt[i] = cl * x + (1 - x) * filt[i - 1]

        return _series_out(
            filt, "{0} period FRAMA.".format(period)
        )

    @classmethod
    def MACD(
        cls,
        ohlc: pl.DataFrame,
        period_fast: int = 12,
        period_slow: int = 26,
        signal: int = 9,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.DataFrame:
        """
        MACD, MACD Signal and MACD difference.
        The MACD Line oscillates above and below the zero line, which is also known as the centerline.
        These crossovers signal that the 12-day EMA has crossed the 26-day EMA. The direction, of course, depends on the direction of the moving average cross.
        Positive MACD indicates that the 12-day EMA is above the 26-day EMA. Positive values increase as the shorter EMA diverges further from the longer EMA.
        This means upside momentum is increasing. Negative MACD values indicates that the 12-day EMA is below the 26-day EMA.
        Negative values increase as the shorter EMA diverges further below the longer EMA. This means downside momentum is increasing.

        Signal line crossovers are the most common MACD signals. The signal line is a 9-day EMA of the MACD Line.
        As a moving average of the indicator, it trails the MACD and makes it easier to spot MACD turns.
        A bullish crossover occurs when the MACD turns up and crosses above the signal line.
        A bearish crossover occurs when the MACD turns down and crosses below the signal line.
        """
        pl_df = ohlc
        ema_fast = _ewm_mean(_col(pl_df, column), span=period_fast, adjust=adjust)
        ema_slow = _ewm_mean(_col(pl_df, column), span=period_slow, adjust=adjust)
        macd = ema_fast - ema_slow
        macd_signal = _ewm_mean(macd, span=signal, adjust=adjust)
        return _frame_out(
            {"MACD": macd, "SIGNAL": macd_signal}
        )

    @classmethod
    def PPO(
        cls,
        ohlc: pl.DataFrame,
        period_fast: int = 12,
        period_slow: int = 26,
        signal: int = 9,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.DataFrame:
        """
        Percentage Price Oscillator
        PPO, PPO Signal and PPO difference.
        As with MACD, the PPO reflects the convergence and divergence of two moving averages.
        While MACD measures the absolute difference between two moving averages, PPO makes this a relative value by dividing the difference by the slower moving average
        """
        pl_df = ohlc
        ema_fast = _ewm_mean(_col(pl_df, column), span=period_fast, adjust=adjust)
        ema_slow = _ewm_mean(_col(pl_df, column), span=period_slow, adjust=adjust)
        ppo = ((ema_fast - ema_slow) / ema_slow) * 100
        ppo_signal = _ewm_mean(ppo, span=signal, adjust=adjust)
        ppo_histo = ppo - ppo_signal
        return _frame_out(
            {"PPO": ppo, "SIGNAL": ppo_signal, "HISTO": ppo_histo}
        )

    @classmethod
    @inputvalidator(input_="ohlcv")
    def VW_MACD(
        cls,
        ohlcv: pl.DataFrame,
        period_fast: int = 12,
        period_slow: int = 26,
        signal: int = 9,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.DataFrame:
        """ "Volume-Weighted MACD" is an indicator that shows how a volume-weighted moving average can be used to calculate moving average convergence/divergence (MACD).
        This technique was first used by Buff Dormeier, CMT, and has been written about since at least 2002.
        """
        pl_df = ohlcv
        vp = _col(pl_df, "volume") * _col(pl_df, column)
        _fast = _ewm_mean(vp, span=period_fast, adjust=adjust) / _ewm_mean(
            _col(pl_df, "volume"), span=period_fast, adjust=adjust
        )
        _slow = _ewm_mean(vp, span=period_slow, adjust=adjust) / _ewm_mean(
            _col(pl_df, "volume"), span=period_slow, adjust=adjust
        )
        macd = _fast - _slow
        macd_signal = _ewm_mean(macd, span=signal, adjust=adjust)
        return _frame_out({"MACD": macd, "SIGNAL": macd_signal})

    @classmethod
    @inputvalidator(input_="ohlcv")
    def EV_MACD(
        cls,
        ohlcv: pl.DataFrame,
        period_fast: int = 20,
        period_slow: int = 40,
        signal: int = 9,
        adjust: bool = True,
    ) -> pl.DataFrame:
        """
        Elastic Volume Weighted MACD is a variation of standard MACD,
        calculated using two EVWMA's.

        :period_slow: Specifies the number of Periods used for the slow EVWMA calculation
        :period_fast: Specifies the number of Periods used for the fast EVWMA calculation
        :signal: Specifies the number of Periods used for the signal calculation
        """
        pl_df = ohlcv
        evwma_slow = cls.EVWMA(pl_df, period_slow)
        evwma_fast = cls.EVWMA(pl_df, period_fast)
        macd = evwma_fast - evwma_slow
        macd_signal = _ewm_mean(macd, span=signal, adjust=adjust)
        return _frame_out({"MACD": macd, "SIGNAL": macd_signal})

    @classmethod
    def MOM(cls, ohlc: pl.DataFrame, period: int = 10, column: str = "close") -> pl.Series:
        """Market momentum is measured by continually taking price differences for a fixed time interval.
        To construct a 10-day momentum line, simply subtract the closing price 10 days ago from the last closing price.
        This positive or negative value is then plotted around a zero line."""
        pl_df = ohlc
        return _series_out(
            _diff(_col(pl_df, column), period), "MOM".format(period)
        )

    @classmethod
    def ROC(cls, ohlc: pl.DataFrame, period: int = 12, column: str = "close") -> pl.Series:
        """The Rate-of-Change (ROC) indicator, which is also referred to as simply Momentum,
        is a pure momentum oscillator that measures the percent change in price from one period to the next.
        The ROC calculation compares the current price with the price "n" periods ago.
        """
        pl_df = ohlc
        col = _col(pl_df, column)
        result = (_diff(col, period) / _shift(col, period)) * 100
        return _series_out(result, "ROC")

    @classmethod
    def VBM(
        cls,
        ohlc: pl.DataFrame,
        roc_period: int = 12,
        atr_period: int = 26,
        column: str = "close",
    ) -> pl.Series:
        """The Volatility-Based-Momentum (VBM) indicator, The calculation for a volatility based momentum (VBM)
        indicator is very similar to ROC, but divides by the security's historical volatility instead.
        The average true range indicator (ATR) is used to compute historical volatility.
        VBM(n,v) = (Close — Close n periods ago) / ATR(v periods)
        """
        pl_df = ohlc
        col = _col(pl_df, column)
        # Preserve pandas-ref quirk: diff - shift (not just diff)
        result = (_diff(col, roc_period) - _shift(col, roc_period)) / cls.ATR(
            pl_df, atr_period
        )
        return _series_out(result, "VBM")

    @classmethod
    def RSI(
        cls,
        ohlc: pl.DataFrame,
        period: int = 14,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """Relative Strength Index (RSI) is a momentum oscillator that measures the speed and change of price movements.
        RSI oscillates between zero and 100. Traditionally, and according to Wilder, RSI is considered overbought when above 70 and oversold when below 30.
        Signals can also be generated by looking for divergences, failure swings and centerline crossovers.
        RSI can also be used to identify the general trend."""
        pl_df = ohlc
        delta = _diff(_col(pl_df, column))
        d = _to_np(delta)
        up = np.where(np.isnan(d), np.nan, np.where(d < 0, 0.0, d))
        down = np.where(np.isnan(d), np.nan, np.where(d > 0, 0.0, d))
        _gain = _ewm_mean(up, alpha=1.0 / period, adjust=adjust)
        _loss = _ewm_mean(np.abs(down), alpha=1.0 / period, adjust=adjust)
        rs = _gain / _loss
        result = 100 - (100 / (1 + rs))
        return _series_out(result, "{0} period RSI".format(period))

    @classmethod
    def IFT_RSI(
        cls,
        ohlc: pl.DataFrame,
        column: str = "close",
        rsi_period: int = 5,
        wma_period: int = 9,
    ) -> pl.Series:
        """Modified Inverse Fisher Transform applied on RSI.
        Suggested method to use any IFT indicator is to buy when the indicator crosses over –0.5 or crosses over +0.5
        if it has not previously crossed over –0.5 and to sell short when the indicators crosses under +0.5 or crosses under –0.5
        if it has not previously crossed under +0.5."""
        pl_df = ohlc
        v1 = 0.1 * (cls.RSI(pl_df, rsi_period, column=column) - 50)
        v2 = _wma(v1, wma_period)
        ift = (v2**2 - 1) / (v2**2 + 1)
        return _series_out(ift, "IFT_RSI")

    @classmethod
    def SWI(cls, ohlc: pl.DataFrame, period: int = 16) -> pl.Series:
        """Sine Wave indicator"""
        raise NotImplementedError

    @classmethod
    def DYMI(
        cls, ohlc: pl.DataFrame, column: str = "close", adjust: bool = True
    ) -> pl.Series:
        """
        The Dynamic Momentum Index is a variable term RSI. The RSI term varies from 3 to 30. The variable
        time period makes the RSI more responsive to short-term moves. The more volatile the price is,
        the shorter the time period is. It is interpreted in the same way as the RSI, but provides signals earlier.
        Readings below 30 are considered oversold, and levels over 70 are considered overbought. The indicator
        oscillates between 0 and 100.
        https://www.investopedia.com/terms/d/dynamicmomentumindex.asp
        """
        pl_df = ohlc
        close = _col(pl_df, column)
        sd = _rolling_std(close, 5)
        asd = _rolling_mean(sd, 10)
        v = sd / asd
        t_arr = _to_np(v)
        t_vals = np.zeros(len(t_arr), dtype=int)
        for i, val in enumerate(t_arr):
            if val != val:  # NaN
                t_vals[i] = 0
            else:
                rounded = int(round(14 / val)) if val != 0 else 0
                t_vals[i] = int(min(max(rounded, 5), 30))

        # Match pandas: periods from 14..len-1, RSI on subset
        results = []
        n = len(pl_df)
        for idx in range(14, n):
            time = t_vals[idx]
            if (idx - time) < 0:
                subset = pl_df.slice(0, idx)
            else:
                subset = pl_df.slice(idx - time, time)
            rsi = cls.RSI(subset, period=time, column=column, adjust=adjust)
            results.append(_to_np(rsi)[-1])

        return pl.Series(results)

    @classmethod
    def TR(cls, ohlc: pl.DataFrame) -> pl.Series:
        """True Range is the maximum of three price ranges.
        Most recent period's high minus the most recent period's low.
        Absolute value of the most recent period's high minus the previous close.
        Absolute value of the most recent period's low minus the previous close."""
        pl_df = ohlc
        high = _col(pl_df, "high")
        low = _col(pl_df, "low")
        close = _col(pl_df, "close")
        tr1 = _to_np((high - low).abs())
        tr2 = _to_np((high - _shift(close)).abs())
        tr3 = _to_np((_shift(close) - low).abs())
        # numpy nanmax skips NaN (same as pandas DataFrame.max(axis=1, skipna=True))
        stacked = np.vstack([tr1, tr2, tr3])
        with np.errstate(all="ignore"):
            tr = np.nanmax(stacked, axis=0)
        return _series_out(tr, "TR")

    @classmethod
    def ATR(cls, ohlc: pl.DataFrame, period: int = 14) -> pl.Series:
        """Average True Range is moving average of True Range."""
        pl_df = ohlc
        tr = cls.TR(pl_df)
        result = _rolling_mean(tr, period)
        return _series_out(result, "{0} period ATR".format(period))

    @classmethod
    def SAR(cls, ohlc: pl.DataFrame, af: int = 0.02, amax: int = 0.2) -> pl.Series:
        """SAR stands for "stop and reverse," which is the actual indicator used in the system.
        SAR trails price as the trend extends over time. The indicator is below prices when prices are rising and above prices when prices are falling.
        In this regard, the indicator stops and reverses when the price trend reverses and breaks above or below the indicator.
        """
        pl_df = ohlc
        high = _to_np(_col(pl_df, "high"))
        low = _to_np(_col(pl_df, "low"))

        sig0, xpt0, af0 = True, high[0], af
        hl_std = float(np.nanstd(high - low, ddof=1)) if len(high) > 1 else 0.0
        # pandas (ohlc.high - ohlc.low).std() uses ddof=1
        _sar = [low[0] - hl_std]

        for i in range(1, len(pl_df)):
            sig1, xpt1, af1 = sig0, xpt0, af0

            lmin = min(low[i - 1], low[i])
            lmax = max(high[i - 1], high[i])

            if sig1:
                sig0 = low[i] > _sar[-1]
                xpt0 = max(lmax, xpt1)
            else:
                sig0 = high[i] >= _sar[-1]
                xpt0 = min(lmin, xpt1)

            if sig0 == sig1:
                sari = _sar[-1] + (xpt1 - _sar[-1]) * af1
                af0 = min(amax, af1 + af)

                if sig0:
                    af0 = af0 if xpt0 > xpt1 else af1
                    sari = min(sari, lmin)
                else:
                    af0 = af0 if xpt0 < xpt1 else af1
                    sari = max(sari, lmax)
            else:
                af0 = af
                sari = xpt0

            _sar.append(sari)

        return _series_out(_sar, None)

    @classmethod
    def PSAR(cls, ohlc: pl.DataFrame, iaf: int = 0.02, maxaf: int = 0.2) -> pl.DataFrame:
        """
        The parabolic SAR indicator, developed by J. Wells Wilder, is used by traders to determine trend direction and potential reversals in price.
        The indicator uses a trailing stop and reverse method called "SAR," or stop and reverse, to identify suitable exit and entry points.
        Traders also refer to the indicator as the parabolic stop and reverse, parabolic SAR, or PSAR.
        https://www.investopedia.com/terms/p/parabolicindicator.asp
        https://virtualizedfrog.wordpress.com/2014/12/09/parabolic-sar-implementation-in-python/
        """
        pl_df = ohlc
        length = len(pl_df)
        high = _to_np(_col(pl_df, "high"))
        low = _to_np(_col(pl_df, "low"))
        close = _to_np(_col(pl_df, "close"))
        psar = close.copy()
        psarbull = [None] * length
        psarbear = [None] * length
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
                        af = min(af + iaf, maxaf)
                    if low[i - 1] < psar[i]:
                        psar[i] = low[i - 1]
                    if low[i - 2] < psar[i]:
                        psar[i] = low[i - 2]
                else:
                    if low[i] < lp:
                        lp = low[i]
                        af = min(af + iaf, maxaf)
                    if high[i - 1] > psar[i]:
                        psar[i] = high[i - 1]
                    if high[i - 2] > psar[i]:
                        psar[i] = high[i - 2]

            if bull:
                psarbull[i] = psar[i]
            else:
                psarbear[i] = psar[i]

        # Preserve pandas-ref swap quirk: both columns get bull list values
        bear_col = psarbull
        bull_col = psarbull
        return _frame_out(
            {"psar": psar, "psarbull": bull_col, "psarbear": bear_col}
        )

    @classmethod
    def BBANDS(
        cls,
        ohlc: pl.DataFrame,
        period: int = 20,
        MA: pl.Series = None,
        column: str = "close",
        std_multiplier: float = 2,
    ) -> pl.DataFrame:
        """
        Developed by John Bollinger, Bollinger Bands® are volatility bands placed above and below a moving average.
        Volatility is based on the standard deviation, which changes as volatility increases and decreases.
        The bands automatically widen when volatility increases and narrow when volatility decreases.

        This method allows input of some other form of moving average like EMA or KAMA around which BBAND will be formed.
        Pass desired moving average as <MA> argument. For example BBANDS(MA=TA.KAMA(20)).
        """
        pl_df = ohlc
        std = _rolling_std(_col(pl_df, column), period)
        ma_vals = _ensure_ma(MA, len(pl_df))
        if ma_vals is None:
            middle = cls.SMA(pl_df, period, column=column)
        else:
            middle = pl.Series(ma_vals)
        upper = middle + (std_multiplier * std)
        lower = middle - (std_multiplier * std)
        return _frame_out(
            {"BB_UPPER": upper, "BB_MIDDLE": middle, "BB_LOWER": lower}
        )

    @classmethod
    def MOBO(
        cls,
        ohlc: pl.DataFrame,
        period: int = 10,
        std_multiplier: float = 0.8,
        column: str = "close",
    ) -> pl.DataFrame:
        """
        "MOBO bands are based on a zone of 0.80 standard deviation with a 10 period look-back"
        If the price breaks out of the MOBO band it can signify a trend move or price spike
        Contains 42% of price movements(noise) within bands.
        """
        # Preserve pandas-ref: hardcoded period=10, std_multiplier=0.8 via TA.BBANDS
        return TA.BBANDS(ohlc, period=10, std_multiplier=0.8, column=column)

    @classmethod
    def BBWIDTH(
        cls, ohlc: pl.DataFrame, period: int = 20, MA: pl.Series = None, column: str = "close"
    ) -> pl.Series:
        """Bandwidth tells how wide the Bollinger Bands are on a normalized basis."""
        pl_df = ohlc
        bb = TA.BBANDS(pl_df, period, MA, column)
        result = (bb.get_column("BB_UPPER") - bb.get_column("BB_LOWER")) / bb.get_column(
            "BB_MIDDLE"
        )
        return _series_out(result, "{0} period BBWITH".format(period))

    @classmethod
    def PERCENT_B(
        cls, ohlc: pl.DataFrame, period: int = 20, MA: pl.Series = None, column: str = "close"
    ) -> pl.Series:
        """
        %b (pronounced 'percent b') is derived from the formula for Stochastics and shows where price is in relation to the bands.
        %b equals 1 at the upper band and 0 at the lower band.
        """
        pl_df = ohlc
        bb = TA.BBANDS(pl_df, period, MA, column)
        close = _col(pl_df, "close")
        lower = bb.get_column("BB_LOWER")
        upper = bb.get_column("BB_UPPER")
        percent_b = (close - lower) / (upper - lower)
        return _series_out(percent_b, "%b")

    @classmethod
    def KC(
        cls,
        ohlc: pl.DataFrame,
        period: int = 20,
        atr_period: int = 10,
        MA: pl.Series = None,
        kc_mult: float = 2,
    ) -> pl.DataFrame:
        """Keltner Channels [KC] are volatility-based envelopes set above and below an exponential moving average.
        This indicator is similar to Bollinger Bands, which use the standard deviation to set the bands.
        Instead of using the standard deviation, Keltner Channels use the Average True Range (ATR) to set channel distance.
        The channels are typically set two Average True Range values above and below the 20-day EMA.
        The exponential moving average dictates direction and the Average True Range sets channel width.
        Keltner Channels are a trend following indicator used to identify reversals with channel breakouts and channel direction.
        Channels can also be used to identify overbought and oversold levels when the trend is flat.
        """
        pl_df = ohlc
        ma_vals = _ensure_ma(MA, len(pl_df))
        if ma_vals is None:
            middle = cls.EMA(pl_df, period)
        else:
            middle = pl.Series(ma_vals)
        atr = cls.ATR(pl_df, atr_period)
        up = middle + (kc_mult * atr)
        down = middle - (kc_mult * atr)
        return _frame_out({"KC_UPPER": up, "KC_LOWER": down})

    @classmethod
    def DO(
        cls, ohlc: pl.DataFrame, upper_period: int = 20, lower_period: int = 5
    ) -> pl.DataFrame:
        """Donchian Channel, a moving average indicator developed by Richard Donchian.
        It plots the highest high and lowest low over the last period time intervals."""
        pl_df = ohlc
        upper = _rolling_max(_col(pl_df, "high"), upper_period)
        lower = _rolling_min(_col(pl_df, "low"), lower_period)
        middle = (upper + lower) / 2
        return _frame_out(
            {"LOWER": lower, "MIDDLE": middle, "UPPER": upper}
        )

    @classmethod
    def DMI(cls, ohlc: pl.DataFrame, period: int = 14, adjust: bool = True) -> pl.DataFrame:
        """The directional movement indicator (also known as the directional movement index - DMI) is a valuable tool
         for assessing price direction and strength. This indicator was created in 1978 by J. Welles Wilder, who also created the popular
         relative strength index. DMI tells you when to be long or short.
         It is especially useful for trend trading strategies because it differentiates between strong and weak trends,
         allowing the trader to enter only the strongest trends.
        source: https://www.tradingview.com/wiki/Directional_Movement_(DMI)#CALCULATION

        :period: Specifies the number of Periods used for DMI calculation
        """
        pl_df = ohlc
        up_move = _diff(_col(pl_df, "high"))
        down_move = -_diff(_col(pl_df, "low"))
        up_a = _to_np(up_move)
        down_a = _to_np(down_move)
        plus = np.where((up_a > down_a) & (up_a > 0), up_a, 0.0)
        minus = np.where((down_a > up_a) & (down_a > 0), down_a, 0.0)
        atr = cls.ATR(pl_df, period)
        diplus = 100 * _ewm_mean(
            pl.Series(plus) / atr, alpha=1 / period, adjust=adjust
        )
        diminus = 100 * _ewm_mean(
            pl.Series(minus) / atr, alpha=1 / period, adjust=adjust
        )
        return _frame_out(
            {"DI_PLUS": diplus, "DI_MINUS": diminus}
        )

    @classmethod
    def ADX(cls, ohlc: pl.DataFrame, period: int = 14, adjust: bool = True) -> pl.Series:
        """The A.D.X. is 100 * smoothed moving average of absolute value (DMI +/-) divided by (DMI+ + DMI-). ADX does not indicate trend direction or momentum,
        only trend strength. Generally, A.D.X. readings below 20 indicate trend weakness,
        and readings above 40 indicate trend strength. An extremely strong trend is indicated by readings above 50
        """
        pl_df = ohlc
        dmi = cls.DMI(pl_df, period, adjust=adjust)
        di_plus = dmi.get_column("DI_PLUS")
        di_minus = dmi.get_column("DI_MINUS")
        result = 100 * _ewm_mean(
            (di_plus - di_minus).abs() / (di_plus + di_minus),
            alpha=1 / period,
            adjust=adjust,
        )
        return _series_out(
            result, "{0} period ADX.".format(period)
        )

    @classmethod
    def PIVOT(cls, ohlc: pl.DataFrame) -> pl.DataFrame:
        """
        Pivot Points are significant support and resistance levels that can be used to determine potential trades.
        The pivot points come as a technical analysis indicator calculated using a financial instrument's high, low, and close value.
        The pivot point's parameters are usually taken from the previous day's trading range.
        This means you'll have to use the previous day's range for today's pivot points.
        Or, last week's range if you want to calculate weekly pivot points or, last month's range for monthly pivot points and so on.
        """
        pl_df = ohlc
        df = pl_df.select([_shift(_col(pl_df, c)).alias(c) for c in pl_df.columns])
        pivot = cls.TP(df)
        high = _col(df, "high")
        low = _col(df, "low")
        s1 = (pivot * 2) - high
        s2 = pivot - (high - low)
        s3 = low - (2 * (high - pivot))
        s4 = low - (3 * (high - pivot))
        r1 = (pivot * 2) - low
        r2 = pivot + (high - low)
        r3 = high + (2 * (pivot - low))
        r4 = high + (3 * (pivot - low))
        return _frame_out(
            {
                "pivot": pivot,
                "s1": s1,
                "s2": s2,
                "s3": s3,
                "s4": s4,
                "r1": r1,
                "r2": r2,
                "r3": r3,
                "r4": r4,
            }
        )

    @classmethod
    def PIVOT_FIB(cls, ohlc: pl.DataFrame) -> pl.DataFrame:
        """
        Fibonacci pivot point levels are determined by first calculating the classic pivot point,
        then multiply the previous day's range with its corresponding Fibonacci level.
        Most traders use the 38.2%, 61.8% and 100% retracements in their calculations.
        """
        pl_df = ohlc
        df = pl_df.select([_shift(_col(pl_df, c)).alias(c) for c in pl_df.columns])
        pp = cls.TP(df)
        high = _col(df, "high")
        low = _col(df, "low")
        rng = high - low
        r4 = pp + (rng * 1.382)
        r3 = pp + (rng * 1)
        r2 = pp + (rng * 0.618)
        r1 = pp + (rng * 0.382)
        s1 = pp - (rng * 0.382)
        s2 = pp - (rng * 0.618)
        s3 = pp - (rng * 1)
        s4 = pp - (rng * 1.382)
        return _frame_out(
            {
                "pivot": pp,
                "s1": s1,
                "s2": s2,
                "s3": s3,
                "s4": s4,
                "r1": r1,
                "r2": r2,
                "r3": r3,
                "r4": r4,
            }
        )

    @classmethod
    def STOCH(cls, ohlc: pl.DataFrame, period: int = 14) -> pl.Series:
        """Stochastic oscillator %K
        The stochastic oscillator is a momentum indicator comparing the closing price of a security
        to the range of its prices over a certain period of time.
        The sensitivity of the oscillator to market movements is reducible by adjusting that time
        period or by taking a moving average of the result.
        """
        pl_df = ohlc
        highest_high = _rolling_max(_col(pl_df, "high"), period)
        lowest_low = _rolling_min(_col(pl_df, "low"), period)
        stoch = (_col(pl_df, "close") - lowest_low) / (highest_high - lowest_low) * 100
        return _series_out(
            stoch, "{0} period STOCH %K".format(period)
        )

    @classmethod
    def STOCHD(cls, ohlc: pl.DataFrame, period: int = 3, stoch_period: int = 14) -> pl.Series:
        """Stochastic oscillator %D
        STOCH%D is a 3 period simple moving average of %K.
        """
        pl_df = ohlc
        result = _rolling_mean(cls.STOCH(pl_df, stoch_period), period)
        return _series_out(
            result, "{0} period STOCH %D.".format(period)
        )

    @classmethod
    def STOCHRSI(
        cls, ohlc: pl.DataFrame, rsi_period: int = 14, stoch_period: int = 14
    ) -> pl.Series:
        """StochRSI is an oscillator that measures the level of RSI relative to its high-low range over a set time period.
        StochRSI applies the Stochastics formula to RSI values, instead of price values. This makes it an indicator of an indicator.
        The result is an oscillator that fluctuates between 0 and 1."""
        pl_df = ohlc
        rsi = cls.RSI(pl_df, rsi_period)
        # Preserve quirk: global min/max of entire RSI series
        rsi_min = float(rsi.min())
        rsi_max = float(rsi.max())
        scaled = (rsi - rsi_min) / (rsi_max - rsi_min)
        result = _rolling_mean(scaled, stoch_period)
        return _series_out(
            result,
            "{0} period stochastic RSI.".format(rsi_period)
        )

    @classmethod
    def WILLIAMS(cls, ohlc: pl.DataFrame, period: int = 14) -> pl.Series:
        """Williams %R, or just %R, is a technical analysis oscillator showing the current closing price in relation to the high and low
        of the past N days (for a given N). It was developed by a publisher and promoter of trading materials, Larry Williams.
        Its purpose is to tell whether a stock or commodity market is trading near the high or the low, or somewhere in between,
        of its recent trading range.
        The oscillator is on a negative scale, from −100 (lowest) up to 0 (highest).
        """
        pl_df = ohlc
        highest_high = _rolling_max(_col(pl_df, "high"), period)
        lowest_low = _rolling_min(_col(pl_df, "low"), period)
        wr = (highest_high - _col(pl_df, "close")) / (highest_high - lowest_low)
        return _series_out(wr * -100, "{0} Williams %R".format(period))

    @classmethod
    def UO(cls, ohlc: pl.DataFrame, column: str = "close") -> pl.Series:
        """Ultimate Oscillator is a momentum oscillator designed to capture momentum across three different time frames.
        The multiple time frame objective seeks to avoid the pitfalls of other oscillators.
        Many momentum oscillators surge at the beginning of a strong advance and then form bearish divergence as the advance continues.
        This is because they are stuck with one time frame. The Ultimate Oscillator attempts to correct this fault by incorporating longer
        time frames into the basic formula."""
        pl_df = ohlc
        low = _to_np(_col(pl_df, "low"))
        prev_close = _to_np(_shift(_col(pl_df, "close")))
        k = np.minimum(low, prev_close)
        bp = _col(pl_df, column) - pl.Series(k)
        tr = cls.TR(pl_df)
        average7 = _rolling_sum(bp, 7) / _rolling_sum(tr, 7)
        average14 = _rolling_sum(bp, 14) / _rolling_sum(tr, 14)
        average28 = _rolling_sum(bp, 28) / _rolling_sum(tr, 28)
        result = (100 * ((4 * average7) + (2 * average14) + average28)) / (4 + 2 + 1)
        return _series_out(result, None)

    @classmethod
    def AO(cls, ohlc: pl.DataFrame, slow_period: int = 34, fast_period: int = 5) -> pl.Series:
        """'EMA',
        Awesome Oscillator is an indicator used to measure market momentum. AO calculates the difference of a 34 Period and 5 Period Simple Moving Averages.
        The Simple Moving Averages that are used are not calculated using closing price but rather each bar's midpoints.
        AO is generally used to affirm trends or to anticipate possible reversals."""
        pl_df = ohlc
        mid = (_col(pl_df, "high") + _col(pl_df, "low")) / 2
        slow = _rolling_mean(mid, slow_period)
        fast = _rolling_mean(mid, fast_period)
        return _series_out(fast - slow, "AO")

    @classmethod
    def MI(cls, ohlc: pl.DataFrame, period: int = 9, adjust: bool = True) -> pl.Series:
        """Developed by Donald Dorsey, the Mass Index uses the high-low range to identify trend reversals based on range expansions.
        In this sense, the Mass Index is a volatility indicator that does not have a directional bias.
        Instead, the Mass Index identifies range bulges that can foreshadow a reversal of the current trend.
        """
        pl_df = ohlc
        _range = _col(pl_df, "high") - _col(pl_df, "low")
        ema9 = _ewm_mean(_range, span=period, adjust=adjust)
        dema9 = _ewm_mean(ema9, span=period, adjust=adjust)
        mass = ema9 / dema9
        return _series_out(_rolling_sum(mass, 25), "Mass Index")

    @classmethod
    def BOP(cls, ohlc: pl.DataFrame) -> pl.Series:
        """Balance Of Power indicator"""
        pl_df = ohlc
        result = (_col(pl_df, "close") - _col(pl_df, "open")) / (
            _col(pl_df, "high") - _col(pl_df, "low")
        )
        return _series_out(result, "Balance Of Power")

    @classmethod
    def VORTEX(cls, ohlc: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """The Vortex indicator plots two oscillating lines, one to identify positive trend movement and the other
        to identify negative price movement.
        Indicator construction revolves around the highs and lows of the last two days or periods.
        The distance from the current high to the prior low designates positive trend movement while the
        distance between the current low and the prior high designates negative trend movement.
        Strongly positive or negative trend movements will show a longer length between the two numbers while
        weaker positive or negative trend movement will show a shorter length."""
        pl_df = ohlc
        vmp = (_col(pl_df, "high") - _shift(_col(pl_df, "low"))).abs()
        vmm = (_col(pl_df, "low") - _shift(_col(pl_df, "high"))).abs()
        vmpx = _rolling_sum(vmp, period)
        vmmx = _rolling_sum(vmm, period)
        tr = _rolling_sum(cls.TR(pl_df), period)
        vip = (vmpx / tr).interpolate()
        vim = (vmmx / tr).interpolate()
        return _frame_out({"VIm": vim, "VIp": vip})

    @classmethod
    def KST(
        cls, ohlc: pl.DataFrame, r1: int = 10, r2: int = 15, r3: int = 20, r4: int = 30
    ) -> pl.DataFrame:
        """Know Sure Thing (KST) is a momentum oscillator based on the smoothed rate-of-change for four different time frames.
        KST measures price momentum for four different price cycles. It can be used just like any momentum oscillator.
        Chartists can look for divergences, overbought/oversold readings, signal line crossovers and centerline crossovers.
        """
        pl_df = ohlc
        r1s = _rolling_mean(cls.ROC(pl_df, r1), 10)
        r2s = _rolling_mean(cls.ROC(pl_df, r2), 10)
        r3s = _rolling_mean(cls.ROC(pl_df, r3), 10)
        r4s = _rolling_mean(cls.ROC(pl_df, r4), 15)
        k = (r1s * 1) + (r2s * 2) + (r3s * 3) + (r4s * 4)
        signal = _rolling_mean(k, 10)
        return _frame_out({"KST": k, "signal": signal})

    @classmethod
    def TSI(
        cls,
        ohlc: pl.DataFrame,
        long: int = 25,
        short: int = 13,
        signal: int = 13,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.DataFrame:
        """True Strength Index (TSI) is a momentum oscillator based on a double smoothing of price changes."""
        pl_df = ohlc
        momentum = _diff(_col(pl_df, column))
        _ema25 = _ewm_mean(momentum, span=long, min_periods=long - 1, adjust=adjust)
        _dema13 = _ewm_mean(_ema25, span=short, min_periods=short - 1, adjust=adjust)
        absmomentum = _diff(_col(pl_df, column)).abs()
        _aema25 = _ewm_mean(absmomentum, span=long, min_periods=long - 1, adjust=adjust)
        _adema13 = _ewm_mean(_aema25, span=short, min_periods=short - 1, adjust=adjust)
        tsi = (_dema13 / _adema13) * 100
        sig = _ewm_mean(tsi, span=signal, min_periods=signal - 1, adjust=adjust)
        return _frame_out({"TSI": tsi, "signal": sig})

    @classmethod
    def TP(cls, ohlc: pl.DataFrame) -> pl.Series:
        """Typical Price refers to the arithmetic average of the high, low, and closing prices for a given period."""
        pl_df = ohlc
        result = (_col(pl_df, "high") + _col(pl_df, "low") + _col(pl_df, "close")) / 3
        return _series_out(result, "TP")

    @classmethod
    @inputvalidator(input_="ohlcv")
    def ADL(cls, ohlcv: pl.DataFrame) -> pl.Series:
        """The accumulation/distribution line was created by Marc Chaikin to determine the flow of money into or out of a security.
        It should not be confused with the advance/decline line. While their initials might be the same, these are entirely different indicators,
        and their uses are different as well. Whereas the advance/decline line can provide insight into market movements,
        the accumulation/distribution line is of use to traders looking to measure buy/sell pressure on a security or confirm the strength of a trend.
        """
        pl_df = ohlcv
        mfm = (
            (_col(pl_df, "close") - _col(pl_df, "low"))
            - (_col(pl_df, "high") - _col(pl_df, "close"))
        ) / (_col(pl_df, "high") - _col(pl_df, "low"))
        mfv = mfm * _col(pl_df, "volume")
        return _series_out(mfv.cum_sum(), None)

    @classmethod
    @inputvalidator(input_="ohlcv")
    def CHAIKIN(cls, ohlcv: pl.DataFrame, adjust: bool = True) -> pl.Series:
        """Chaikin Oscillator, named after its creator, Marc Chaikin, the Chaikin oscillator is an oscillator that measures the accumulation/distribution
        line of the moving average convergence divergence (MACD). The Chaikin oscillator is calculated by subtracting a 10-day exponential moving average (EMA)
        of the accumulation/distribution line from a three-day EMA of the accumulation/distribution line, and highlights the momentum implied by the
        accumulation/distribution line."""
        pl_df = ohlcv
        adl = cls.ADL(pl_df)
        result = _ewm_mean(adl, span=3, min_periods=2, adjust=adjust) - _ewm_mean(
            adl, span=10, min_periods=9, adjust=adjust
        )
        return _series_out(result, None)

    @classmethod
    @inputvalidator(input_="ohlcv")
    def MFI(cls, ohlc: pl.DataFrame, period: int = 14) -> pl.Series:
        """The money flow index (MFI) is a momentum indicator that measures
        the inflow and outflow of money into a security over a specific period of time.
        MFI can be understood as RSI adjusted for volume.
        The money flow indicator is one of the more reliable indicators of overbought and oversold conditions, perhaps partly because
        it uses the higher readings of 80 and 20 as compared to the RSI's overbought/oversold readings of 70 and 30
        """
        pl_df = ohlc
        tp = cls.TP(pl_df)
        rmf = tp * _col(pl_df, "volume")
        delta = _diff(tp)
        d = _to_np(delta)
        r = _to_np(rmf)
        pos = np.where(d > 0, r, 0.0)
        neg = np.where(d < 0, r, 0.0)
        mfratio = _rolling_sum(pl.Series(pos), period) / _rolling_sum(
            pl.Series(neg), period
        )
        result = 100 - (100 / (1 + mfratio))
        return _series_out(result, "{0} period MFI".format(period))

    @classmethod
    @inputvalidator(input_="ohlcv")
    def OBV(cls, ohlcv: pl.DataFrame, column: str = "close") -> pl.Series:
        """
        On Balance Volume (OBV) measures buying and selling pressure as a cumulative indicator that adds volume on up days and subtracts volume on down days.
        OBV was developed by Joe Granville and introduced in his 1963 book, Granville's New Key to Stock Market Profits.
        It was one of the first indicators to measure positive and negative volume flow.
        Chartists can look for divergences between OBV and price to predict price movements or use OBV to confirm price trends.

        source: https://en.wikipedia.org/wiki/On-balance_volume#The_formula

        :param pl.DataFrame ohlc: 'open, high, low, close' Polars DataFrame
        :return pl.Series: result is polars.Series
        """
        pl_df = ohlcv
        close = _to_np(_col(pl_df, column))
        volume = _to_np(_col(pl_df, "volume"))
        prev = np.roll(close, 1)
        prev[0] = np.nan
        obv = np.full(len(close), np.nan)
        pos_change = close >= prev
        neg_change = close < prev
        no_change = close == prev
        obv[pos_change] = volume[pos_change]
        obv[neg_change] = -volume[neg_change]
        # no_change overwrites with previous OBV (still nan before cumsum for equals that were also pos)
        for i in range(len(obv)):
            if no_change[i]:
                obv[i] = obv[i - 1] if i > 0 else np.nan
        return _series_out(np.cumsum(obv), "OBV")

    @classmethod
    @inputvalidator(input_="ohlcv")
    def WOBV(cls, ohlcv: pl.DataFrame, column: str = "close") -> pl.Series:
        """
        Weighted OBV
        Can also be seen as an OBV indicator that takes the price differences into account.
        In a regular OBV, a high volume bar can make a huge difference,
        even if the price went up only 0.01, and it it goes down 0.01
        instead, that huge volume makes the OBV go down, even though
        hardly anything really happened.
        """
        pl_df = ohlcv
        wobv = _col(pl_df, "volume") * _diff(_col(pl_df, column))
        return _series_out(wobv.cum_sum(), "WOBV")

    @classmethod
    @inputvalidator(input_="ohlcv")
    def VZO(
        cls,
        ohlc: pl.DataFrame,
        period: int = 14,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """VZO uses price, previous price and moving averages to compute its oscillating value.
        It is a leading indicator that calculates buy and sell signals based on oversold / overbought conditions.
        Oscillations between the 5% and 40% levels mark a bullish trend zone, while oscillations between -40% and 5% mark a bearish trend zone.
        Meanwhile, readings above 40% signal an overbought condition, while readings above 60% signal an extremely overbought condition.
        Alternatively, readings below -40% indicate an oversold condition, which becomes extremely oversold below -60%.
        """
        pl_df = ohlc
        d = _to_np(_diff(_col(pl_df, column)))
        sign = np.sign(d)
        # pandas apply sign: (a > 0) - (a < 0); NaN stays weird — np.sign(nan)=nan
        sign = np.where(d != d, np.nan, (d > 0).astype(float) - (d < 0).astype(float))
        r = pl.Series(sign) * _col(pl_df, "volume")
        dvma = _ewm_mean(r, span=period, adjust=adjust)
        vma = _ewm_mean(_col(pl_df, "volume"), span=period, adjust=adjust)
        return _series_out(100 * (dvma / vma), "VZO")

    @classmethod
    def PZO(
        cls,
        ohlc: pl.DataFrame,
        period: int = 14,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """
        The formula for PZO depends on only one condition: if today's closing price is higher than yesterday's closing price,
        then the closing price will have a positive value (bullish); otherwise it will have a negative value (bearish).
        source: http://traders.com/Documentation/FEEDbk_docs/2011/06/Khalil.html

        :period: Specifies the number of Periods used for PZO calculation
        """
        pl_df = ohlc
        d = _to_np(_diff(_col(pl_df, column)))
        sign = np.where(d != d, np.nan, (d > 0).astype(float) - (d < 0).astype(float))
        r = pl.Series(sign) * _col(pl_df, column)
        cp = _ewm_mean(r, span=period, adjust=adjust)
        tc = cls.EMA(pl_df, period, column=column, adjust=adjust)
        return _series_out(
            100 * (cp / tc), "{} period PZO".format(period)
        )

    @classmethod
    @inputvalidator(input_="ohlcv")
    def EFI(
        cls,
        ohlcv: pl.DataFrame,
        period: int = 13,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """Elder's Force Index is an indicator that uses price and volume to assess the power
        behind a move or identify possible turning points."""
        pl_df = ohlcv
        fi = _diff(_col(pl_df, column)) * _col(pl_df, "volume")
        result = _ewm_mean(fi, span=period, adjust=adjust)
        return _series_out(
            result, "{0} period Force Index".format(period)
        )

    @classmethod
    @inputvalidator(input_="ohlcv")
    def CFI(
        cls, ohlcv: pl.DataFrame, column: str = "close", adjust: bool = True
    ) -> pl.Series:
        """
        Cummulative Force Index.
        Adopted from  Elder's Force Index.
        """
        pl_df = ohlcv
        fi1 = _col(pl_df, "volume") * _diff(_col(pl_df, column))
        cfi = _ewm_mean(fi1, span=10, min_periods=9, adjust=adjust)
        return _series_out(cfi.cum_sum(), "CFI")

    @classmethod
    def EBBP(cls, ohlc: pl.DataFrame) -> pl.DataFrame:
        """Bull power and bear power by Dr. Alexander Elder show where today's high and low lie relative to the a 13-day EMA"""
        pl_df = ohlc
        ema13 = cls.EMA(pl_df, 13)
        bull_power = _col(pl_df, "high") - ema13
        bear_power = _col(pl_df, "low") - ema13
        return _frame_out(
            {"Bull.": bull_power, "Bear.": bear_power}
        )

    @classmethod
    @inputvalidator(input_="ohlcv")
    def EMV(cls, ohlcv: pl.Series, period: int = 14) -> pl.Series:
        """Ease of Movement (EMV) is a volume-based oscillator that fluctuates above and below the zero line.
        As its name implies, it is designed to measure the 'ease' of price movement.
        prices are advancing with relative ease when the oscillator is in positive territory.
        Conversely, prices are declining with relative ease when the oscillator is in negative territory.
        """
        pl_df = ohlcv
        distance = ((_col(pl_df, "high") + _col(pl_df, "low")) / 2) - (
            (_shift(_col(pl_df, "high")) + _shift(_col(pl_df, "low"))) / 2
        )
        box_ratio = (_col(pl_df, "volume") / 1000000) / (
            _col(pl_df, "high") - _col(pl_df, "low")
        )
        _emv = distance / box_ratio
        return _series_out(
            _rolling_mean(_emv, period),
            "{0} period EMV.".format(period)
        )

    @classmethod
    def CCI(cls, ohlc: pl.DataFrame, period: int = 20, constant: float = 0.015) -> pl.Series:
        """Commodity Channel Index (CCI) is a versatile indicator that can be used to identify a new trend or warn of extreme conditions.
        CCI measures the current price level relative to an average price level over a given period of time.
        The CCI typically oscillates above and below a zero line. Normal oscillations will occur within the range of +100 and −100.
        Readings above +100 imply an overbought condition, while readings below −100 imply an oversold condition.
        As with other overbought/oversold indicators, this means that there is a large probability that the price will correct to more representative levels.

        source: https://stockcharts.com/school/doku.php?id=chart_school:technical_indicators:commodity_channel_index_cci

        :param pl.DataFrame ohlc: 'open, high, low, close' Polars DataFrame
        :period: int - number of periods to take into consideration
        :factor float: the constant at .015 to ensure that approximately 70 to 80 percent of CCI values would fall between -100 and +100.
        :return pl.Series: result is polars.Series
        """
        pl_df = ohlc
        tp = cls.TP(pl_df)
        tp_mean = _rolling_mean(tp, period, min_periods=0)

        def _mad(x) -> float:
            arr = _window_np(x)
            return float(np.mean(np.abs(arr - np.mean(arr))))

        mad = tp.rolling_map(_mad, window_size=period, min_samples=1)
        # pandas min_periods=0 still needs at least 1 sample for apply
        result = (tp - tp_mean) / (constant * mad)
        return _series_out(result, "{0} period CCI".format(period))

    @classmethod
    def COPP(cls, ohlc: pl.DataFrame, adjust: bool = True) -> pl.Series:
        """The Coppock Curve is a momentum indicator, it signals buying opportunities when the indicator moved from negative territory to positive territory."""
        pl_df = ohlc
        roc1 = cls.ROC(pl_df, 14)
        roc2 = cls.ROC(pl_df, 11)
        result = _ewm_mean(roc1 + roc2, span=10, min_periods=9, adjust=adjust)
        return _series_out(result, "Coppock Curve")

    @classmethod
    def BASP(cls, ohlc: pl.DataFrame, period: int = 40, adjust: bool = True) -> pl.DataFrame:
        """BASP indicator serves to identify buying and selling pressure."""
        pl_df = ohlc
        sp = _col(pl_df, "high") - _col(pl_df, "close")
        bp = _col(pl_df, "close") - _col(pl_df, "low")
        spavg = _ewm_mean(sp, span=period, adjust=adjust)
        bpavg = _ewm_mean(bp, span=period, adjust=adjust)
        nbp = bp / bpavg
        nsp = sp / spavg
        varg = _ewm_mean(_col(pl_df, "volume"), span=period, adjust=adjust)
        nv = _col(pl_df, "volume") / varg
        nbfraw = nbp * nv
        nsfraw = nsp * nv
        return _frame_out({"Buy.": nbfraw, "Sell.": nsfraw})

    @classmethod
    def BASPN(cls, ohlc: pl.DataFrame, period: int = 40, adjust: bool = True) -> pl.DataFrame:
        """
        Normalized BASP indicator
        """
        pl_df = ohlc
        sp = _col(pl_df, "high") - _col(pl_df, "close")
        bp = _col(pl_df, "close") - _col(pl_df, "low")
        spavg = _ewm_mean(sp, span=period, adjust=adjust)
        bpavg = _ewm_mean(bp, span=period, adjust=adjust)
        nbp = bp / bpavg
        nsp = sp / spavg
        varg = _ewm_mean(_col(pl_df, "volume"), span=period, adjust=adjust)
        nv = _col(pl_df, "volume") / varg
        nbf = _ewm_mean(nbp * nv, span=20, adjust=adjust)
        nsf = _ewm_mean(nsp * nv, span=20, adjust=adjust)
        return _frame_out({"Buy.": nbf, "Sell.": nsf})

    @classmethod
    def CMO(
        cls,
        ohlc: pl.DataFrame,
        period: int = 9,
        factor: int = 100,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.DataFrame:
        """
        Chande Momentum Oscillator (CMO) - technical momentum indicator invented by the technical analyst Tushar Chande.
        It is created by calculating the difference between the sum of all recent gains and the sum of all recent losses and then
        dividing the result by the sum of all price movement over the period.
        This oscillator is similar to other momentum indicators such as the Relative Strength Index and the Stochastic Oscillator
        because it is range bounded (+100 and -100)."""
        pl_df = ohlc
        delta = _diff(_col(pl_df, column))
        d = _to_np(delta)
        up = np.where(np.isnan(d), np.nan, np.where(d < 0, 0.0, d))
        down = np.where(np.isnan(d), np.nan, np.where(d > 0, 0.0, d))
        _gain = _ewm_mean(up, com=period, adjust=adjust)
        _loss = _ewm_mean(down, com=period, adjust=adjust).abs()
        result = factor * ((_gain - _loss) / (_gain + _loss))
        return _series_out(result, "CMO")

    @classmethod
    def CHANDELIER(
        cls,
        ohlc: pl.DataFrame,
        short_period: int = 22,
        long_period: int = 22,
        k: int = 3,
    ) -> pl.DataFrame:
        """
        Chandelier Exit sets a trailing stop-loss based on the Average True Range (ATR).

        The indicator is designed to keep traders in a trend and prevent an early exit as long as the trend extends.

        Typically, the Chandelier Exit will be above prices during a downtrend and below prices during an uptrend.
        """
        pl_df = ohlc
        atr22 = cls.ATR(pl_df, 22)
        l = _rolling_max(_col(pl_df, "high"), long_period) - atr22 * k
        s = _rolling_min(_col(pl_df, "low"), short_period) + atr22 * k
        return _frame_out({"Short.": s, "Long.": l})

    @classmethod
    def QSTICK(cls, ohlc: pl.DataFrame, period: int = 14) -> pl.Series:
        """
        QStick indicator shows the dominance of black (down) or white (up) candlesticks, which are red and green in Chart,
        as represented by the average open to close change for each of past N days."""
        pl_df = ohlc
        n = len(pl_df)
        start = max(0, n - period)
        close = _col(pl_df, "close").slice(start, period)
        open_ = _col(pl_df, "open").slice(start, period)
        result = (close - open_) / period
        return _series_out(result, "{0} period QSTICK.".format(period))

    @classmethod
    def TMF(cls, ohlcv: pl.DataFrame, period: int = 21) -> pl.Series:
        """Indicator by Colin Twiggs which improves upon CMF.
        source: https://user42.tuxfamily.org/chart/manual/Twiggs-Money-Flow.html"""
        raise NotImplementedError

    @classmethod
    def WTO(
        cls,
        ohlc: pl.DataFrame,
        channel_length: int = 10,
        average_length: int = 21,
        adjust: bool = True,
    ) -> pl.DataFrame:
        """
        Wave Trend Oscillator
        source: http://www.fxcoaching.com/WaveTrend/
        """
        pl_df = ohlc
        ap = cls.TP(pl_df)
        esa = _ewm_mean(ap, span=average_length, adjust=adjust)
        d = _ewm_mean((ap - esa).abs(), span=channel_length, adjust=adjust)
        ci = (ap - esa) / (0.015 * d)
        wt1 = _ewm_mean(ci, span=average_length, adjust=adjust)
        wt2 = _rolling_mean(wt1, 4)
        return _frame_out({"WT1.": wt1, "WT2.": wt2})

    @classmethod
    def FISH(cls, ohlc: pl.DataFrame, period: int = 10, adjust: bool = True) -> pl.Series:
        """
        Fisher Transform was presented by John Ehlers. It assumes that price distributions behave like square waves.
        """
        from numpy import log, seterr

        seterr(divide="ignore")

        pl_df = ohlc
        med = (_col(pl_df, "high") + _col(pl_df, "low")) / 2
        ndaylow = _rolling_min(med, period)
        ndayhigh = _rolling_max(med, period)
        raw = (2 * ((med - ndaylow) / (ndayhigh - ndaylow))) - 1
        smooth = _ewm_mean(raw, span=5, adjust=adjust)
        _smooth = smooth.fill_null(0)
        # also fill NaN from inf/-inf division
        sm = _to_np(_smooth)
        sm = np.nan_to_num(sm, nan=0.0)
        fisher = log((1 + sm) / (1 - sm))
        result = _ewm_mean(pl.Series(fisher), span=3, adjust=adjust)
        return _series_out(
            result, "{0} period FISH.".format(period)
        )

    @classmethod
    def ICHIMOKU(
        cls,
        ohlc: pl.DataFrame,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_period: int = 52,
        chikou_period: int = 26,
    ) -> pl.DataFrame:
        """
        The Ichimoku Cloud, also known as Ichimoku Kinko Hyo, is a versatile indicator that defines support and resistance,
        identifies trend direction, gauges momentum and provides trading signals.

        Ichimoku Kinko Hyo translates into "one look equilibrium chart".
        """
        pl_df = ohlc
        tenkan_sen = (
            _rolling_max(_col(pl_df, "high"), tenkan_period)
            + _rolling_min(_col(pl_df, "low"), tenkan_period)
        ) / 2
        kijun_sen = (
            _rolling_max(_col(pl_df, "high"), kijun_period)
            + _rolling_min(_col(pl_df, "low"), kijun_period)
        ) / 2
        senkou_span_a = _shift((tenkan_sen + kijun_sen) / 2, kijun_period)
        senkou_span_b = _shift(
            (
                _rolling_max(_col(pl_df, "high"), senkou_period)
                + _rolling_min(_col(pl_df, "low"), senkou_period)
            )
            / 2,
            kijun_period,
        )
        chikou_span = _shift(_col(pl_df, "close"), -chikou_period)
        return _frame_out(
            {
                "TENKAN": tenkan_sen,
                "KIJUN": kijun_sen,
                "senkou_span_a": senkou_span_a,
                "SENKOU": senkou_span_b,
                "CHIKOU": chikou_span,
            }
        )

    @classmethod
    def APZ(
        cls,
        ohlc: pl.DataFrame,
        period: int = 21,
        dev_factor: int = 2,
        MA: pl.Series = None,
        adjust: bool = True,
    ) -> pl.DataFrame:
        """
        The adaptive price zone (APZ) is a technical indicator developed by Lee Leibfarth.

        The APZ is a volatility based indicator that appears as a set of bands placed over a price chart.

        Especially useful in non-trending, choppy markets,

        the APZ was created to help traders find potential turning points in the markets.
        """
        pl_df = ohlc
        ma_vals = _ensure_ma(MA, len(pl_df))
        if ma_vals is None:
            ma = cls.DEMA(pl_df, period, adjust=adjust)
        else:
            ma = pl.Series(ma_vals)
        price_range = _ewm_mean(
            _col(pl_df, "high") - _col(pl_df, "low"), span=period, adjust=adjust
        )
        volatility_value = _ewm_mean(price_range, span=period, adjust=adjust)
        upper_band = (volatility_value * dev_factor) + ma
        lower_band = ma - (volatility_value * dev_factor)
        return _frame_out(
            {"UPPER": upper_band, "LOWER": lower_band}
        )

    @classmethod
    def SQZMI(cls, ohlc: pl.DataFrame, period: int = 20, MA: pl.Series = None) -> pl.DataFrame:
        """
        Squeeze Momentum Indicator

        The Squeeze indicator attempts to identify periods of consolidation in a market.
        In general the market is either in a period of quiet consolidation or vertical price discovery.
        By identifying these calm periods, we have a better opportunity of getting into trades with the potential for larger moves.
        Once a market enters into a "squeeze", we watch the overall market momentum to help forecast the market direction and await a release of market energy.

        :param pl.DataFrame ohlc: 'open, high, low, close' Polars DataFrame
        :period: int - number of periods to take into consideration
        :MA pl.Series: override internal calculation which uses SMA with moving average of your choice
        :return pl.Series: indicator calcs as Polars Series

        SQZMI['SQZ'] is bool True/False, if True squeeze is on. If false, squeeeze has fired.
        """
        pl_df = ohlc
        # Preserve pandas-ref quirk: when MA is a Series, pass ma=None to BBANDS
        if not _is_series_like(MA):
            ma = cls.SMA(pl_df, period)
        else:
            ma = None
        bb = cls.BBANDS(pl_df, period=period, MA=ma)
        kc = cls.KC(pl_df, period=period, kc_mult=1.5)
        bb_lower = _to_np(bb.get_column("BB_LOWER"))
        bb_upper = _to_np(bb.get_column("BB_UPPER"))
        kc_lower = _to_np(kc.get_column("KC_LOWER"))
        kc_upper = _to_np(kc.get_column("KC_UPPER"))
        sqz = (bb_lower > kc_lower) & (bb_upper < kc_upper)
        return _series_out(sqz, "{0} period SQZMI".format(period))

    @classmethod
    @inputvalidator(input_="ohlcv")
    def VPT(cls, ohlc: pl.DataFrame) -> pl.Series:
        """
        Volume Price Trend
        The Volume Price Trend uses the difference of price and previous price with volume and feedback to arrive at its final form.
        If there appears to be a bullish divergence of price and the VPT (upward slope of the VPT and downward slope of the price) a buy opportunity exists.
        Conversely, a bearish divergence (downward slope of the VPT and upward slope of the price) implies a sell opportunity.
        """
        pl_df = ohlc
        hilow = (_col(pl_df, "high") - _col(pl_df, "low")) * 100
        openclose = (_col(pl_df, "close") - _col(pl_df, "open")) * 100
        vol = _col(pl_df, "volume") / hilow
        spreadvol = (openclose * vol).cum_sum()
        vpt = spreadvol + spreadvol
        return _series_out(vpt, "VPT")

    @classmethod
    @inputvalidator(input_="ohlcv")
    def FVE(cls, ohlc: pl.DataFrame, period: int = 22, factor: int = 0.3) -> pl.Series:
        """
        FVE is a money flow indicator, but it has two important innovations: first, the F VE takes into account both intra and
        interday price action, and second, minimal price changes are taken into account by introducing a price threshold.
        """
        pl_df = ohlc
        hl2 = (_col(pl_df, "high") + _col(pl_df, "low")) / 2
        tp = TA.TP(pl_df)
        smav = _rolling_mean(_col(pl_df, "volume"), period)
        mf = _col(pl_df, "close") - hl2 + _diff(tp)
        mf_a = _to_np(mf)
        close_a = _to_np(_col(pl_df, "close"))
        vol_a = _to_np(_col(pl_df, "volume"))
        vol_shift = np.zeros(len(mf_a))
        for i in range(len(mf_a)):
            if mf_a[i] > factor * close_a[i] / 100:
                vol_shift[i] = vol_a[i]
            elif mf_a[i] < -factor * close_a[i] / 100:
                vol_shift[i] = -vol_a[i]
            else:
                vol_shift[i] = 0
        _sum = _rolling_sum(pl.Series(vol_shift), period)
        return _series_out((_sum / smav) / period * 100, None)

    @classmethod
    def VFI(
        cls,
        ohlc: pl.DataFrame,
        period: int = 130,
        smoothing_factor: int = 3,
        factor: int = 0.2,
        vfactor: int = 2.5,
        adjust: bool = True,
    ) -> pl.Series:
        """
        This indicator tracks volume based on the direction of price
        movement. It is similar to the On Balance Volume Indicator.
        For more information see "Using Money Flow to Stay with the Trend",
        and "Volume Flow Indicator Performance" in the June 2004 and
        July 2004 editions of Technical Analysis of Stocks and Commodities.

        :period: Specifies the number of Periods used for VFI calculation
        :factor: Specifies the fixed scaling factor for the VFI calculation
        :vfactor: Specifies the cutoff for maximum volume in the VFI calculation
        :smoothing_factor: Specifies the number of periods used in the short moving average
        """
        pl_df = ohlc
        typical = TA.TP(pl_df)
        inter = _diff(pl.Series(np.log(_to_np(typical))))
        vinter = _rolling_std(inter, 30)
        cutoff = factor * vinter * _col(pl_df, "close")
        price_change = _diff(typical)
        mav = _rolling_mean(_col(pl_df, "volume"), period)
        mav_shift = _shift(mav)

        vol = _to_np(_col(pl_df, "volume"))
        mav_s = _to_np(mav_shift)
        pc = _to_np(price_change)
        cut = _to_np(cutoff)
        # fillna 0 like pandas
        pc = np.nan_to_num(pc, nan=0.0)
        cut = np.nan_to_num(cut, nan=0.0)

        added_vol = np.where(
            vol > vfactor * mav_s, vfactor * mav_s, vol
        )
        # when mav_s is nan, comparison is false, use vol — match apply behavior with NaN
        added_vol = np.where(mav_s != mav_s, vol, added_vol)

        multiplier = np.where(pc > cut, 1, np.where(pc < 0 - cut, -1, 0))
        raw_sum = _rolling_sum(pl.Series(multiplier * added_vol), period)
        raw_value = raw_sum / mav_shift
        vfi = _ewm_mean(
            raw_value,
            span=smoothing_factor,
            min_periods=smoothing_factor - 1,
            adjust=adjust,
        )
        return _series_out(vfi, "VFI")

    @classmethod
    def MSD(cls, ohlc: pl.DataFrame, period: int = 21, column: str = "close") -> pl.Series:
        """
        Standard deviation is a statistical term that measures the amount of variability or dispersion around an average.
        Standard deviation is also a measure of volatility. Generally speaking, dispersion is the difference between the actual value and the average value.
        The larger this dispersion or variability is, the higher the standard deviation.
        Standard Deviation values rise significantly when the analyzed contract of indicator change in value dramatically.
        When markets are stable, low Standard Deviation readings are normal.
        Low Standard Deviation readings typically tend to come before significant upward changes in price.
        Analysts generally agree that high volatility is part of major tops, while low volatility accompanies major bottoms.

        :period: Specifies the number of Periods used for MSD calculation
        """
        pl_df = ohlc
        return _series_out(
            _rolling_std(_col(pl_df, column), period), "MSD"
        )

    @classmethod
    def STC(
        cls,
        ohlc: pl.DataFrame,
        period_fast: int = 23,
        period_slow: int = 50,
        k_period: int = 10,
        d_period: int = 3,
        column: str = "close",
        adjust: bool = True,
    ) -> pl.Series:
        """
        The Schaff Trend Cycle (Oscillator) can be viewed as Double Smoothed
        Stochastic of the MACD.

        Schaff Trend Cycle - Three input values are used with the STC:
        – Sh: shorter-term Exponential Moving Average with a default period of 23
        – Lg: longer-term Exponential Moving Average with a default period of 50
        – Cycle, set at half the cycle length with a default value of 10. (Stoch K-period)
        - Smooth, set at smoothing at 3 (Stoch D-period)

        The STC is calculated in the following order:
        EMA1 = EMA (Close, fast_period);
        EMA2 = EMA (Close, slow_period);
        MACD = EMA1 – EMA2.
        Second, the 10-period Stochastic from the MACD values is calculated:
        STOCH_K, STOCH_D  = StochasticFull(MACD, k_period, d_period)  // Stoch of MACD
        STC =  average(STOCH_D, d_period) // second smoothed

        In case the STC indicator is decreasing, this indicates that the trend cycle
        is falling, while the price tends to stabilize or follow the cycle to the downside.
        In case the STC indicator is increasing, this indicates that the trend cycle
        is up, while the price tends to stabilize or follow the cycle to the upside.
        """
        pl_df = ohlc
        ema_fast = _ewm_mean(_col(pl_df, column), span=period_fast, adjust=adjust)
        ema_slow = _ewm_mean(_col(pl_df, column), span=period_slow, adjust=adjust)
        macd = ema_fast - ema_slow
        stok = (
            (macd - _rolling_min(macd, k_period))
            / (_rolling_max(macd, k_period) - _rolling_min(macd, k_period))
        ) * 100
        stod = _rolling_mean(stok, d_period)
        stod_double = _rolling_mean(stod, d_period)
        return _series_out(
            stod_double, "{0} period STC".format(k_period)
        )

    @classmethod
    @inputvalidator(input_="ohlcv")
    def EVSTC(
        cls,
        ohlc: pl.DataFrame,
        period_fast: int = 12,
        period_slow: int = 30,
        k_period: int = 10,
        d_period: int = 3,
        adjust: bool = True,
    ) -> pl.Series:
        """Modification of Schaff Trend Cycle using EVWMA MACD for calculation"""
        pl_df = ohlc
        ema_slow = cls.EVWMA(pl_df, period_slow)
        ema_fast = cls.EVWMA(pl_df, period_fast)
        macd = ema_fast - ema_slow
        stok = (
            (macd - _rolling_min(macd, k_period))
            / (_rolling_max(macd, k_period) - _rolling_min(macd, k_period))
        ) * 100
        stod = _rolling_mean(stok, d_period)
        stod_double = _rolling_mean(stod, d_period)
        return _series_out(
            stod_double, "{0} period EVSTC".format(k_period)
        )

    @classmethod
    def WILLIAMS_FRACTAL(cls, ohlc: pl.DataFrame, period: int = 2) -> pl.DataFrame:
        """
        Williams Fractal Indicator
        Source: https://www.investopedia.com/terms/f/fractal.asp

        :param DataFrame ohlc: data
        :param int period: how many lower highs/higher lows the extremum value should be preceded and followed.
        :return DataFrame: fractals identified by boolean
        """
        pl_df = ohlc
        window_size = period * 2 + 1
        high = _to_np(_col(pl_df, "high"))
        low = _to_np(_col(pl_df, "low"))
        n = len(high)
        bearish = np.full(n, np.nan)
        bullish = np.full(n, np.nan)
        # center=True rolling: first valid at period, last at n-period-1
        half = period
        for i in range(n):
            start = i - half
            end = i + half + 1
            if start < 0 or end > n:
                continue
            window_h = high[start:end]
            window_l = low[start:end]
            bearish[i] = 1.0 if window_h[period] == np.max(window_h) else 0.0
            bullish[i] = 1.0 if window_l[period] == np.min(window_l) else 0.0
        return _frame_out(
            {"BearishFractal": bearish, "BullishFractal": bullish}
        )

    @classmethod
    def VC(cls, ohlc: pl.DataFrame, period: int = 5) -> pl.DataFrame:
        """Value chart
        Implementation based on a book by Mark Helweg & David Stendahl: Dynamic Trading Indicators: Winning with Value Charts and Price Action Profile

        :period: Specifies the number of Periods used for VC calculation
        """
        pl_df = ohlc
        float_axis = _rolling_mean(
            (_col(pl_df, "high") + _col(pl_df, "low")) / 2, period
        )
        vol_unit = _rolling_mean(_col(pl_df, "high") - _col(pl_df, "low"), period) * 0.2
        value_chart_high = (_col(pl_df, "high") - float_axis) / vol_unit
        value_chart_low = (_col(pl_df, "low") - float_axis) / vol_unit
        value_chart_close = (_col(pl_df, "close") - float_axis) / vol_unit
        value_chart_open = (_col(pl_df, "open") - float_axis) / vol_unit
        return _frame_out(
            {
                "Value Chart High": value_chart_high,
                "Value Chart Low": value_chart_low,
                "Value Chart Close": value_chart_close,
                "Value Chart Open": value_chart_open,
            }
        )

    @classmethod
    def WAVEPM(
        cls,
        ohlc: pl.DataFrame,
        period: int = 14,
        lookback_period: int = 100,
        column: str = "close",
    ) -> pl.Series:
        """
        The Wave PM (Whistler Active Volatility Energy Price Mass) indicator is an oscillator described in the Mark
        Whistler's book "Volatility Illuminated".

        :param DataFrame ohlc: data
        :param int period: period for moving average
        :param int lookback_period: period for oscillator lookback
        :return Series: WAVE PM
        """
        pl_df = ohlc
        ma = _rolling_mean(_col(pl_df, column), period)
        std = _rolling_std(_col(pl_df, column), period, ddof=0)

        def tanh(x):
            two = np.where(x > 0, -2, 2)
            what = two * x
            ex = np.exp(what)
            j = 1 - ex
            k = ex - 1
            l = np.where(x > 0, j, k)
            output = l / (1 + ex)
            return output

        ma_a = _to_np(ma)
        std_a = _to_np(std)
        dev = 3.2 * std_a
        power = np.power(dev / ma_a, 2)
        variance = (
            _to_np(_rolling_sum(pl.Series(power), lookback_period)) / lookback_period
        )
        calc_dev = np.sqrt(variance) * ma_a
        y = dev / calc_dev
        osc_line = tanh(y)
        return _series_out(
            osc_line, "{0} period WAVEPM".format(period)
        )

    @classmethod
    def ROLLING_MAX(cls, ohlc, periods=10, column="close") -> pl.Series:
        """
        Highest value in a rolling window

        :param DataFrame df: data
        :param int periods: number of periods to look back
        :param str column: column to look at
        :return Series: rolling max
        """
        pl_df = ohlc
        if column not in pl_df.columns:
            raise LookupError(column)
        result = _rolling_max(_col(pl_df, column), periods)
        return _series_out(result, None)

    @classmethod
    def ROLLING_MIN(cls, ohlc, periods=10, column="close") -> pl.Series:
        """
        Lowest value in a rolling window

        :param DataFrame df: data
        :param int periods: number of periods to look back
        :param str column: column to look at
        :return Series: rolling min
        """
        pl_df = ohlc
        if column not in pl_df.columns:
            raise LookupError(column)
        result = _rolling_min(_col(pl_df, column), periods)
        return _series_out(result, None)

    @classmethod
    def LINEAR_REGRESSION(cls, ohlc: pl.DataFrame, period: int = 14, column: str = "close") -> pl.Series:
        """
        Linear Regression indicator.
        
        Formula:
        - For each window of size 'period', compute the linear regression line
        - Return the predicted value at the end of each window
        
        This is useful for trend identification and can be used for:
        - Trend direction (slope of the line)
        - Entry/exit signals when price crosses the regression line
        
        Args:
            ohlc (DataFrame): pl.DataFrame containing OHLC data
            period (int): Period to compute linear regression over
            column (str): Column to use for calculation (default: 'close')
            
        Returns:
            Series: Linear regression line values
        """
        pl_df = ohlc

        def calculate_lr_point(values):
            arr = _window_np(values)
            if len(arr) < 2:
                return arr[-1] if len(arr) > 0 else np.nan

            x = np.arange(len(arr))
            y = arr

            n = len(x)
            x_mean = np.mean(x)
            y_mean = np.mean(y)
            denom = np.sum((x - x_mean) ** 2)
            slope = np.sum((x - x_mean) * (y - y_mean)) / denom
            intercept = y_mean - slope * x_mean
            return slope * (n - 1) + intercept

        result = _col(pl_df, column).rolling_map(
            calculate_lr_point, window_size=period, min_samples=1
        )
        return _series_out(
            result,
            "{0} period LINEAR_REGRESSION".format(period)
        )


if __name__ == "__main__":
    print([k for k in TA.__dict__.keys() if k[0] not in "_"])
