"""Tests for the ML classifier → ml_signal → backtest helpers."""

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from fast_trade.build_data_frame import apply_transformers_to_dataframe
from fast_trade.ml.classifier import (
    _freqs_compatible,
    _time_split_index,
    attach_ml_signal,
    build_classifier_features,
    default_classifier_strategy,
    fit_return_classifier,
    label_forward_return,
    ml_signal_datapoint,
    predict_ml_signal,
    resolve_backtest_freq,
    run_classifier_backtest,
)
from fast_trade.utils import parse_freq
from fast_trade.validate_backtest import validate_backtest


def _synthetic_ohlcv(rows: int = 400, seed: int = 11) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = [start + timedelta(hours=i) for i in range(rows)]
    rets = rng.normal(0.0005, 0.012, size=rows)
    close = 50 * np.cumprod(1.0 + rets)
    high = close * (1.0 + rng.uniform(0.0, 0.01, size=rows))
    low = close * (1.0 - rng.uniform(0.0, 0.01, size=rows))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(10.0, 500.0, size=rows)
    return pl.DataFrame(
        {"date": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume},
    )


def test_build_classifier_features_and_labels():
    df = _synthetic_ohlcv()
    features = build_classifier_features(df)
    assert list(features.columns) == [
        "date",
        "ret_1",
        "ret_5",
        "ret_10",
        "vol_20",
        "range_pct",
        "sma_ratio",
        "volume_z",
    ]
    assert features["date"].equals(df["date"])
    labels = label_forward_return(df["close"], horizon=5, threshold=0.0)
    assert len(labels) - labels.null_count() == len(df) - 5
    assert labels.tail(5).null_count() == 5
    assert set(labels.drop_nulls().unique().to_list()).issubset({0.0, 1.0})


def test_classifier_features_preserve_sample_std_and_return_semantics():
    close = 10.0 + np.arange(25) * 0.25 + np.sin(np.arange(25)) * 0.2
    volume = 20.0 + np.arange(25)
    df = _synthetic_ohlcv(rows=25).with_columns(
        pl.Series("close", close),
        pl.Series("high", close + 1.5),
        pl.Series("low", close - 0.5),
        pl.Series("volume", volume),
    )
    features = build_classifier_features(df)
    row = features.row(20, named=True)
    returns = close[1:21] / close[:20] - 1.0

    assert features["vol_20"].head(20).null_count() == 20
    assert row["ret_1"] == pytest.approx(close[20] / close[19] - 1.0)
    assert row["ret_5"] == pytest.approx(close[20] / close[15] - 1.0)
    assert row["ret_10"] == pytest.approx(close[20] / close[10] - 1.0)
    assert row["vol_20"] == pytest.approx(np.std(returns, ddof=1))
    assert row["range_pct"] == pytest.approx(2.0 / close[20])
    assert row["sma_ratio"] == pytest.approx(close[20] / np.mean(close[1:21]) - 1.0)
    assert row["volume_z"] == pytest.approx(
        (volume[20] - np.mean(volume[1:21])) / np.std(volume[1:21], ddof=1)
    )


def test_classifier_features_normalize_nonfinite_and_zero_variance():
    close = np.full(50, 10.0)
    close[25] = 0.0
    close[30] = np.inf
    close[35] = np.nan
    df = _synthetic_ohlcv(rows=50).with_columns(
        pl.Series("close", close), pl.lit(10.0).alias("volume")
    )
    features = build_classifier_features(df)

    assert features["range_pct"][25] is None
    assert features["ret_1"][26] is None
    assert features["ret_1"][30] is None
    assert features["ret_1"][35] is None
    assert features["volume_z"].null_count() == len(df)
    for col in features.columns:
        if col != "date":
            assert features[col].drop_nulls().is_finite().all()


def test_forward_labels_ignore_unavailable_or_nonfinite_prices():
    close = pl.Series("close", [1.0, 2.0, 0.0, 4.0, None, np.nan, np.inf, 8.0])
    labels = label_forward_return(close, horizon=1, threshold=0.0)

    assert labels.to_list() == [1.0, 0.0, None, None, None, None, None, None]
    assert labels.dtype == pl.Float64
    assert label_forward_return(pl.Series("close", [1.0, 2.0]), threshold=0.0).to_list() == [None, None]


def test_column_transformer_passthrough():
    df = _synthetic_ohlcv(rows=80)
    df = df.with_columns(pl.Series("ml_signal", [0] * 10 + [1] * 10 + [0] * 60))
    out = apply_transformers_to_dataframe(
        df,
        [ml_signal_datapoint()],
    )
    assert "ml_signal" in out.columns
    assert int(out["ml_signal"].sum()) == 10
    assert out["date"].equals(df["date"])


def test_column_transformer_missing_raises():
    df = _synthetic_ohlcv(rows=50)
    with pytest.raises(Exception, match="ml_signal"):
        apply_transformers_to_dataframe(df, [ml_signal_datapoint()])


def test_default_strategy_validates():
    strategy = default_classifier_strategy(freq="1h")
    errors = validate_backtest(strategy)
    assert errors.get("has_error") is False


def test_fit_and_predict_signal_shapes():
    df = _synthetic_ohlcv()
    fit, features, labels = fit_return_classifier(
        df, horizon=5, threshold=0.0, train_frac=0.7, random_state=0
    )
    assert fit.train_rows + fit.test_rows + fit.purged_train_rows == len(features)
    assert fit.purged_train_rows == 5
    assert 0.0 <= fit.train_accuracy <= 1.0
    assert 0.0 <= fit.test_accuracy <= 1.0
    assert fit.signal_threshold == 0.5
    signal = predict_ml_signal(fit.model, features, fit.feature_columns)
    assert signal.columns == ["date", "ml_signal"]
    assert signal["date"].equals(features["date"])
    assert set(signal["ml_signal"].unique().to_list()).issubset({0, 1})
    assert len(labels) == len(features)


def test_fit_keeps_dates_labels_and_selected_features_aligned_after_invalid_rows():
    df = _synthetic_ohlcv(rows=180)
    close = df["close"].to_list()
    close[50] = None
    close[80] = float("nan")
    close[110] = float("inf")
    df = df.with_columns(pl.Series("close", close))
    fit, features, labels = fit_return_classifier(
        df, horizon=2, threshold=0.0, feature_columns=["ret_1"], random_state=3
    )

    raw = np.array([np.nan if price is None else price for price in close])
    with np.errstate(invalid="ignore", divide="ignore"):
        returns = raw[1:] / raw[:-1] - 1.0
    expected_positions = [
        i for i in range(1, len(df) - 2)
        if np.isfinite(raw[i - 1:i + 1]).all()
        and np.isfinite(raw[i + 2])
        and np.isfinite(returns[i - 1])
    ]
    expected_labels = [int(raw[i + 2] / raw[i] - 1.0 > 0.0) for i in expected_positions]

    assert fit.feature_columns == ["ret_1"]
    assert features.columns == ["date", "ret_1"]
    assert features["date"].to_list() == [df["date"][i] for i in expected_positions]
    assert labels.to_list() == expected_labels
    assert features["ret_1"].is_finite().all()


def test_purge_gap_keeps_train_labels_out_of_sample():
    df = _synthetic_ohlcv(rows=300)
    horizon = 5
    features = build_classifier_features(df)
    labels = label_forward_return(df["close"], horizon=horizon, threshold=0.0)
    usable = features.with_columns(labels.alias("y")).drop_nulls()
    train_idx, test_idx, purged = _time_split_index(
        usable["date"], 0.7, purge_bars=horizon
    )
    assert purged == horizon
    positions = {date: i for i, date in enumerate(df["date"])}
    train_positions = np.array([positions[date] for date in train_idx])
    test_start_pos = positions[test_idx[0]]
    assert (train_positions + horizon).max() < test_start_pos
    cut = int(len(usable) * 0.7)
    assert train_idx.equals(usable["date"].head(cut - horizon))
    assert test_idx.equals(usable["date"].slice(cut))


def test_predict_ml_signal_respects_threshold():
    df = _synthetic_ohlcv()
    fit, features, _labels = fit_return_classifier(
        df, horizon=5, threshold=0.0, train_frac=0.7, random_state=0
    )
    loose = predict_ml_signal(
        fit.model, features, fit.feature_columns, threshold=0.1
    )
    tight = predict_ml_signal(
        fit.model, features, fit.feature_columns, threshold=0.9
    )
    assert int(loose["ml_signal"].sum()) >= int(tight["ml_signal"].sum())
    with pytest.raises(ValueError, match="threshold"):
        predict_ml_signal(fit.model, features, fit.feature_columns, threshold=1.5)


def test_resolve_backtest_freq_infers_and_guards():
    df = _synthetic_ohlcv(rows=80)
    inferred = resolve_backtest_freq(df, {})
    assert inferred[0].isdigit()
    assert parse_freq(inferred) == parse_freq("1h")
    # Alias forms of the same bar size are accepted.
    resolve_backtest_freq(df, {"freq": "1h"})
    resolve_backtest_freq(df, {"freq": "1H"})
    with pytest.raises(ValueError, match="does not match"):
        resolve_backtest_freq(df, {"freq": "1D"})
    assert resolve_backtest_freq(df, {"freq": "1D"}, allow_resample=True) == "1D"


@pytest.mark.parametrize("left,right,expected", [
    ("1h", "60min", True),
    ("1H", "h", True),
    ("1M", "1mo", True),
    ("1M", "1m", False),
    ("1M", "30d", False),
    ("1Y", "365d", False),
    ("invalid", "INVALID", True),
    ("invalid", "1h", False),
])
def test_frequency_compatibility_preserves_alias_and_calendar_semantics(left, right, expected):
    assert _freqs_compatible(left, right) is expected


def test_resolve_backtest_freq_accepts_frequency_objects():
    class _Frequency:
        freqstr = "H"

    assert resolve_backtest_freq(_synthetic_ohlcv(rows=80), {"freq": _Frequency()}) == "1H"


def test_run_classifier_backtest_on_synthetic():
    df = _synthetic_ohlcv(rows=500)
    result = run_classifier_backtest(
        df,
        horizon=5,
        threshold=0.0,
        train_frac=0.7,
        backtest_on="test",
        strategy_overrides={"freq": "1h", "comission": 0.0},
        random_state=1,
    )
    assert result.fit.test_rows > 0
    assert isinstance(result.df, pl.DataFrame)
    assert isinstance(result.trade_df, pl.DataFrame)
    assert result.fit.purged_train_rows == 5
    assert "ml_signal" in result.df.columns
    assert "return_perc" in result.summary
    assert result.extras["backtest_on"] == "test"
    assert result.extras["purged_train_rows"] == 5
    assert len(result.df) <= result.fit.test_rows + 5
    dates = result.df["date"]
    test_start = datetime.fromisoformat(result.extras["test_start"])
    test_end = datetime.fromisoformat(result.extras["test_end"])
    assert dates.min() == test_start
    # The engine may append one synthetic row to close an open final position.
    assert dates.filter(dates <= test_end).to_list() == df["date"].filter(
        (df["date"] >= test_start) & (df["date"] <= test_end)
    ).to_list()
    assert dates.filter(dates > test_end).to_list() in ([], [test_end + timedelta(seconds=1)])


def test_run_classifier_backtest_infers_freq_when_omitted():
    df = _synthetic_ohlcv(rows=500)
    result = run_classifier_backtest(
        df,
        horizon=5,
        threshold=0.0,
        strategy_overrides={"comission": 0.0},
        random_state=1,
    )
    assert parse_freq(result.extras["freq"]) == parse_freq("1h")


def test_run_classifier_backtest_rejects_freq_mismatch():
    df = _synthetic_ohlcv(rows=500)
    with pytest.raises(ValueError, match="does not match"):
        run_classifier_backtest(
            df,
            horizon=5,
            threshold=0.0,
            strategy_overrides={"freq": "1D"},
            random_state=1,
        )


def test_attach_ml_signal_fills_missing():
    df = _synthetic_ohlcv(rows=30)
    signal = df.select("date").head(3).with_columns(pl.Series("ml_signal", [1, 0, 1]))
    out = attach_ml_signal(df, signal)
    assert out["ml_signal"].head(3).to_list() == [1, 0, 1]
    assert (out["ml_signal"].slice(3) == 0).all()
    assert out["date"].equals(df["date"])


def test_attach_ml_signal_aligns_shuffled_dates_and_replaces_custom_column():
    df = _synthetic_ohlcv(rows=5).with_columns(
        pl.lit(9).alias("prediction"),
        pl.Series("__signal_row_order", [5, 4, 3, 2, 1]),
    )
    signal = pl.DataFrame({
        "date": [df["date"][3], df["date"][0], df["date"][2]],
        "ml_signal": [1, 0, None],
    })
    out = attach_ml_signal(df, signal, column="prediction")

    assert out["date"].equals(df["date"])
    assert out["prediction"].to_list() == [0, 0, 0, 1, 0]
    assert out["__signal_row_order"].equals(df["__signal_row_order"])
    assert df["prediction"].to_list() == [9] * 5
    assert "ml_signal" not in out.columns


def test_feature_and_label_validation_errors():
    df = _synthetic_ohlcv(rows=80)
    with pytest.raises(ValueError, match="missing required columns"):
        build_classifier_features(df.drop("volume"))
    with pytest.raises(ValueError, match="horizon"):
        label_forward_return(df["close"], horizon=0)
    with pytest.raises(ValueError, match="train_frac"):
        fit_return_classifier(df, train_frac=1.5)
    with pytest.raises(ValueError, match="at least 40"):
        fit_return_classifier(_synthetic_ohlcv(rows=30), threshold=0.0)
    for column in ["not_a_feature", "date"]:
        with pytest.raises(ValueError, match="Unknown feature"):
            fit_return_classifier(df, feature_columns=[column], threshold=0.0)
    with pytest.raises(ValueError, match="signal_threshold"):
        fit_return_classifier(df, threshold=0.0, signal_threshold=0.0)


def test_fit_rejects_empty_usable_and_single_class(monkeypatch):
    df = _synthetic_ohlcv(rows=80)

    def _all_nan_features(_df):
        features = build_classifier_features(_df)
        return features.with_columns(
            pl.lit(float("nan")).alias(col) for col in features.columns if col != "date"
        )

    monkeypatch.setattr(
        "fast_trade.ml.classifier.build_classifier_features", _all_nan_features
    )
    with pytest.raises(ValueError, match="No usable rows"):
        fit_return_classifier(df, threshold=0.0)

    monkeypatch.undo()
    with pytest.raises(ValueError, match="both classes"):
        fit_return_classifier(df, horizon=5, threshold=10.0, train_frac=0.7)


def test_run_classifier_backtest_all_and_strategy_override():
    df = _synthetic_ohlcv(rows=500)
    with pytest.raises(ValueError, match="backtest_on"):
        run_classifier_backtest(df, backtest_on="train", threshold=0.0)

    result = run_classifier_backtest(
        df,
        horizon=5,
        threshold=0.0,
        train_frac=0.7,
        backtest_on="all",
        signal_threshold=0.45,
        strategy={"name": "custom_ml", "comission": 0.0},
        strategy_overrides={"freq": "1h"},
        random_state=2,
    )
    assert result.extras["backtest_on"] == "all"
    assert result.extras["signal_threshold"] == 0.45
    assert result.strategy["name"] == "custom_ml"
    assert len(result.df) >= result.fit.test_rows


def test_time_split_purge_validation_errors():
    idx = _synthetic_ohlcv(rows=50)["date"]
    with pytest.raises(ValueError, match="purge_bars"):
        _time_split_index(idx, 0.7, purge_bars=-1)
    with pytest.raises(ValueError, match="Not enough training rows after purge"):
        _time_split_index(idx, 0.7, purge_bars=25)


def test_resolve_backtest_freq_requires_explicit_when_uninferable(monkeypatch):
    df = _synthetic_ohlcv(rows=80)
    monkeypatch.setattr("fast_trade.ml.classifier.infer_frequency", lambda _df: None)
    with pytest.raises(ValueError, match="Could not infer"):
        resolve_backtest_freq(df, {})


def test_predict_ml_signal_falls_back_without_predict_proba():
    class _NoProba:
        def predict(self, x):
            return np.ones(len(x), dtype=int)

    df = _synthetic_ohlcv(rows=60)
    features = build_classifier_features(df).drop_nulls()
    cols = [col for col in features.columns if col != "date"]
    signal = predict_ml_signal(_NoProba(), features, cols, threshold=0.5)
    assert (signal["ml_signal"] == 1).all()
    assert signal["date"].equals(features["date"])
