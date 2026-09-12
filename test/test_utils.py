import datetime

import polars as pl
import pytest

from fast_trade import utils


def _ohlcv(dates, **columns):
    return pl.DataFrame({"date": dates, **columns})


def test_to_dataframe_converts_ticks():
    ticks = [
        {"time": 1_600_000_000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"time": 1_600_000_060, "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 12},
    ]
    df = utils.to_dataframe(ticks)
    assert df.columns == ["date", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert isinstance(df.schema["date"], pl.Datetime)
    assert df.get_column("date")[0] == datetime.datetime(2020, 9, 13, 12, 26, 40)


def test_resample_and_resample_calendar():
    dates = [
        datetime.datetime(2024, 1, 1) + datetime.timedelta(minutes=i) for i in range(4)
    ]
    df = _ohlcv(
        dates,
        open=[1.0, 2, 3, 4],
        high=[2.0, 3, 4, 5],
        low=[0.5, 1.5, 2.5, 3.5],
        close=[1.5, 2.5, 3.5, 4.5],
        volume=[10.0, 20, 30, 40],
    )
    out = utils.resample(df, "2min")
    assert len(out) == 2
    assert out.row(0, named=True)["open"] == 1
    assert out.row(0, named=True)["close"] == 2.5
    assert out.row(0, named=True)["high"] == 3
    assert out.row(0, named=True)["low"] == 0.5
    assert out.row(0, named=True)["volume"] == 30

    cal = utils.resample_calendar(df, "2min")
    assert len(cal) == 2


def test_upsample_to_freq_fills_gaps():
    base = datetime.datetime(2024, 1, 1)
    df = _ohlcv(
        [base, base + datetime.timedelta(minutes=3)],
        close=[1.0, 4.0],
    )

    out = utils.upsample_to_freq(df, "1Min")
    assert out.height == 4
    assert list(out.get_column("close")) == [1.0, None, None, 4.0]

    filled = utils.upsample_to_freq(df, "1Min", forward_fill=True)
    assert list(filled.get_column("close")) == [1.0, 1.0, 1.0, 4.0]


def test_trending_up_and_down():
    series = pl.Series("close", [1, 2, 3, 2, 4])
    up = utils.trending_up(series, 1)
    down = utils.trending_down(series, 1)
    assert bool(up[1]) is True
    assert bool(down[3]) is True
    assert bool(up[0]) is False
    assert up.name == "trending_up 1"
    assert down.name == "trending_down 1"


def test_parse_freq_aliases():
    assert utils.parse_freq("1Min") == "1m"
    assert utils.parse_freq("5min") == "5m"
    assert utils.parse_freq("3T") == "3m"
    assert utils.parse_freq("30S") == "30s"
    assert utils.parse_freq("2H") == "2h"
    assert utils.parse_freq("1h") == "1h"
    assert utils.parse_freq("1D") == "1d"
    assert utils.parse_freq("Min") == "1m"
    assert utils.parse_freq(datetime.timedelta(minutes=5)) == "300s"
    assert utils.parse_freq("not_a_freq") is None
    assert utils.parse_freq("") is None

    with pytest.raises(ValueError, match="Invalid frequency"):
        utils.freq_to_polars("not_a_freq")


def test_infer_frequency_all_branches():
    base = datetime.datetime(2024, 1, 1)
    cases = [
        ("30S", [0, 30, 60]),
        ("5Min", [0, 300, 600]),
        ("2H", [0, 7200, 14400]),
        ("3D", [0, 259200, 518400]),
    ]
    for expected, offsets in cases:
        frame = _ohlcv(
            [base + datetime.timedelta(seconds=s) for s in offsets],
            close=[1.0, 2, 3],
        )
        assert utils.infer_frequency(frame) == expected

    hourly = _ohlcv(
        [base + datetime.timedelta(hours=i) for i in range(3)], close=[1.0, 2, 3]
    )
    assert utils.infer_frequency(hourly) == "1H"

    sub_second = _ohlcv(
        [base + datetime.timedelta(milliseconds=500 * i) for i in range(3)],
        close=[1.0, 2, 3],
    )
    assert utils.infer_frequency(sub_second) == "500ms"

    # a single row has no gap to measure
    assert utils.infer_frequency(_ohlcv([base], close=[1.0])) is None

    # duplicated dates leave no positive gap
    assert utils.infer_frequency(_ohlcv([base, base], close=[1.0, 2.0])) is None

    with pytest.raises(ValueError):
        utils.infer_frequency(pl.DataFrame({"close": [1, 2, 3]}))

    with pytest.raises(ValueError, match="not a datetime"):
        utils.infer_frequency(pl.DataFrame({"date": ["a", "b"], "close": [1, 2]}))


def test_ensure_date_column_variants():
    epoch_s = utils.ensure_date_column(pl.DataFrame({"date": [1_523_937_784]}))
    assert epoch_s.get_column("date")[0] == datetime.datetime(2018, 4, 17, 4, 3, 4)

    epoch_ms = utils.ensure_date_column(pl.DataFrame({"date": [1_523_937_784_000]}))
    assert epoch_ms.get_column("date")[0] == datetime.datetime(2018, 4, 17, 4, 3, 4)

    epoch_str = utils.ensure_date_column(pl.DataFrame({"date": ["1523937784"]}))
    assert epoch_str.get_column("date")[0] == datetime.datetime(2018, 4, 17, 4, 3, 4)

    iso = utils.ensure_date_column(pl.DataFrame({"date": ["2024-01-01 00:00:00"]}))
    assert iso.get_column("date")[0] == datetime.datetime(2024, 1, 1)

    from_date = utils.ensure_date_column(
        pl.DataFrame({"date": [datetime.date(2024, 1, 1)]})
    )
    assert isinstance(from_date.schema["date"], pl.Datetime)

    already = pl.DataFrame({"date": [datetime.datetime(2024, 1, 1)]})
    assert utils.ensure_date_column(already).equals(already)

    # parquet files written from a pandas index land in this column
    legacy = utils.ensure_date_column(
        pl.DataFrame({"__index_level_0__": [datetime.datetime(2024, 1, 1)], "close": [1.0]})
    )
    assert legacy.columns == ["date", "close"]

    with pytest.raises(ValueError, match="does not have a 'date' column"):
        utils.ensure_date_column(pl.DataFrame({"close": [1.0]}))
