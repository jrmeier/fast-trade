import pandas as pd
import pytest

from fast_trade import utils


def test_to_dataframe_converts_ticks():
    ticks = [
        {"time": 1_600_000_000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"time": 1_600_000_060, "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 12},
    ]
    df = utils.to_dataframe(ticks)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df.index.name == "time"


def test_resample_and_resample_calendar():
    idx = pd.date_range("2024-01-01", periods=4, freq="min")
    df = pd.DataFrame(
        {"open": [1, 2, 3, 4], "high": [2, 3, 4, 5], "low": [0.5, 1.5, 2.5, 3.5],
         "close": [1.5, 2.5, 3.5, 4.5], "volume": [10, 20, 30, 40]},
        index=idx,
    )
    out = utils.resample(df, "2min")
    assert len(out) == 2
    assert out.iloc[0]["open"] == 1
    assert out.iloc[0]["close"] == 2.5
    assert out.iloc[0]["volume"] == 30

    cal = utils.resample_calendar(df, "2min")
    assert len(cal) == 2


def test_trending_up_and_down():
    series = pd.Series([1, 2, 3, 2, 4], name="close")
    up = utils.trending_up(series, 1)
    down = utils.trending_down(series, 1)
    assert bool(up.iloc[1]) is True
    assert bool(down.iloc[3]) is True
    assert up.name == "trending_up 1"
    assert down.name == "trending_down 1"


def test_infer_frequency_all_branches():
    idx_with_freq = pd.date_range("2024-01-01", periods=3, freq="h")
    df = pd.DataFrame({"close": [1, 2, 3]}, index=idx_with_freq)
    assert utils.infer_frequency(df) == df.index.freq

    cases = [
        ("30S", [0, 30, 60]),
        ("5Min", [0, 300, 600]),
        ("2H", [0, 7200, 14400]),
        ("3D", [0, 259200, 518400]),
    ]
    base = pd.Timestamp("2024-01-01")
    for expected, offsets in cases:
        idx = pd.DatetimeIndex([base + pd.Timedelta(seconds=s) for s in offsets])
        frame = pd.DataFrame({"close": [1, 2, 3]}, index=idx)
        assert utils.infer_frequency(frame) == expected

    with pytest.raises(ValueError):
        utils.infer_frequency(pd.DataFrame({"close": [1, 2, 3]}))
