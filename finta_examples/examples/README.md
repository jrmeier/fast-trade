# Examples

I recommend using [ipython](https://ipython.org/) while playing with FinTA.

Fast Trade's FinTA fork is **Polars-native**. Pass a `polars.DataFrame` with lowercase OHLC columns.

## Loading data

```python
import polars as pl
from fast_trade.finta import TA

ohlc = pl.read_parquet("ft_archive/binanceus/BTCUSDT.parquet")
# or
ohlc = pl.read_csv("data/example.csv", try_parse_dates=True)
```

Expected columns (lowercase): `open`, `high`, `low`, `close`, and `volume` when needed. A `date` column is preferred when using the rest of Fast Trade.

## TA

```python
TA.SMA(ohlc, 42)
TA.RSI(ohlc).tail(10)
TA.EMA(ohlc, 5)
TA.AO(ohlc)
TA.BBANDS(ohlc)
```

That is enough to get started. See `docs/FINTA_README.md` for the full indicator list.
