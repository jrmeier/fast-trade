"""Deterministic research-contract tests; no network or external archive."""

import datetime

import numpy as np
import polars as pl
from polars.testing import assert_frame_equal
import pytest

from fast_trade.ml import walk_forward as wf


def _ohlcv(rows=220, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, rows))
    return pl.DataFrame({
        "date": [datetime.datetime(2024, 1, 1) + datetime.timedelta(hours=i) for i in range(rows)],
        "open": np.r_[close[0], close[:-1]], "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": rng.uniform(50, 400, rows),
    })


def _evaluate(df=None, **overrides):
    options = dict(train_size=60, test_size=30, horizon=5, threshold=0.0)
    options.update(overrides)
    return wf.walk_forward_evaluate(_ohlcv() if df is None else df, **options)


def test_fold_windows_are_chronological_and_disjoint():
    dates = _ohlcv(100)["date"]
    folds = wf.iter_rolling_folds(dates, train_size=40, test_size=10)
    assert len(folds) == 6
    assert folds[0].train_start == dates[0]
    assert folds[0].train_end == dates[39]
    assert folds[0].test_start == dates[40]
    assert folds[0].test_end == dates[49]
    assert folds[0].test_end < folds[1].test_start
    assert len(wf.iter_rolling_folds(dates, train_size=40, test_size=10, step_size=20)) == 3


@pytest.mark.parametrize("options", [
    {"train_size": 10, "test_size": 10}, {"train_size": 40, "test_size": 2},
    {"train_size": 40, "test_size": 10, "step_size": 5}, {"train_size": 100, "test_size": 10},
])
def test_invalid_fold_windows(options):
    with pytest.raises(ValueError):
        wf.iter_rolling_folds(_ohlcv(100)["date"], **options)


def test_default_features_are_causal_and_date_keyed():
    df = _ohlcv()
    full, cols = wf.build_feature_matrix(df)
    prefix, prefix_cols = wf.build_feature_matrix(df.head(120))
    assert {"ret_1", "rsi", "ema_fast", "atr"} <= set(cols)
    assert cols == prefix_cols
    assert_frame_equal(full.head(120), prefix)
    ta, ta_cols = wf.build_feature_matrix(df, include_basic=False, feature_columns=["rsi"])
    assert ta_cols == ["rsi"]
    assert ta.columns == ["date", "rsi"]


@pytest.mark.parametrize("options", [
    {"use_ta": False, "include_basic": False},
    {"feature_columns": ["missing"]}, {"feature_columns": []},
    {"include_basic": False, "ta_datapoints": []},
    {"ta_datapoints": [{"name": "slow", "transformer": "sma", "args": [3], "freq": "2h"}]},
])
def test_invalid_feature_selections(options):
    with pytest.raises(ValueError):
        wf.build_feature_matrix(_ohlcv(), **options)


def test_returns_include_both_fees_and_initial_cash():
    df = _ohlcv(4).with_columns(pl.Series("close", [90.0, 100.0, 105.0, 110.0]))
    net, trades, sharpe = wf._run_signal_backtest(
        df, np.ones(4), freq="1h", comission=1.0, signal_lag=1, base_balance=1000,
    )
    # 1000 -> 9.9 units after entry fee -> 1089 before exit fee -> 1078.11.
    assert net == pytest.approx(7.811)
    assert trades == 1
    returns = np.array([0.0, -0.01, 0.05, 1078.11 / 1039.5 - 1.0])
    assert sharpe == pytest.approx(2 * returns.mean() / returns.std(ddof=1))


def test_execution_waits_for_next_bar_and_counts_completed_trades():
    df = _ohlcv(4).with_columns(pl.Series("close", [100.0, 10.0, 200.0, 100.0]))
    net, trades, _ = wf._run_signal_backtest(
        df, np.array([0, 1, 0, 0]), freq="1h", comission=0, signal_lag=1, base_balance=1000,
    )
    assert net == pytest.approx(-50.0)
    assert trades == 1
    df = _ohlcv(5).with_columns(pl.lit(100.0).alias("close"))
    net, trades, sharpe = wf._run_signal_backtest(
        df, np.array([1, 0, 1, 0, 0]), freq="1h", comission=0, signal_lag=1, base_balance=1000,
    )
    assert (net, trades, sharpe) == (0.0, 2, 0.0)


def test_rsi_state_holds_until_exit_and_starts_flat():
    assert wf._rsi_signal(np.array([np.nan, 20, 40, 80, 20, 80])).tolist() == [0, 1, 1, 0, 1, 0]


def test_full_evaluation_is_reproducible_and_uses_shared_execution(monkeypatch):
    calls = []
    original = wf._run_signal_backtest

    def record(ohlcv, signal, **options):
        calls.append((ohlcv["date"].to_list(), dict(options)))
        return original(ohlcv, signal, **options)

    monkeypatch.setattr(wf, "_run_signal_backtest", record)
    first = _evaluate(comission=0.1)
    second = _evaluate(comission=0.1)
    assert_frame_equal(wf.report_to_frame(first), wf.report_to_frame(second))
    assert first.aggregate == second.aggregate
    assert first.aggregate["n_folds"] == 4
    for i in range(0, len(calls), 4):
        assert calls[i:i + 4] == [calls[i]] * 4
    for fold in first.folds:
        assert fold.train_rows == 55
        assert fold.purged_train_rows == 5
        assert datetime.datetime.fromisoformat(fold.train_end) + datetime.timedelta(hours=5) < datetime.datetime.fromisoformat(fold.test_start)
    assert first.extras["signal_lag"] == 1


def test_training_labels_do_not_use_test_prices(monkeypatch):
    captured = []
    original = wf.HistGradientBoostingClassifier

    def factory(**kwargs):
        model = original(**kwargs)
        fit = model.fit

        def record(x, y):
            captured.append((x.copy(), y.copy()))
            return fit(x, y)

        model.fit = record
        return model

    monkeypatch.setattr(wf, "HistGradientBoostingClassifier", factory)
    df = _ohlcv(110)
    report = _evaluate(df, baselines=[])
    test_start = datetime.datetime.fromisoformat(report.folds[0].test_start)
    changed = df.with_columns(pl.when(pl.col("date") >= test_start).then(pl.col("close") * 5).otherwise(pl.col("close")).alias("close"))
    _evaluate(changed, baselines=[])
    assert len(captured) == 2
    np.testing.assert_array_equal(captured[0][0], captured[1][0])
    np.testing.assert_array_equal(captured[0][1], captured[1][1])


def test_future_after_test_window_cannot_change_first_fold():
    df = _ohlcv()
    first = _evaluate(df, use_ta=False, baselines=["buy_hold"])
    boundary = datetime.datetime.fromisoformat(first.folds[0].test_end)
    changed = df.with_columns(pl.when(pl.col("date") > boundary).then(pl.col("close") * 3).otherwise(pl.col("close")).alias("close"))
    other = _evaluate(changed, use_ta=False, baselines=["buy_hold"])
    assert first.folds[0] == other.folds[0]
    assert first.folds[0].rsi_return_perc is None
    assert first.folds[0].beats_rsi is None


@pytest.mark.parametrize("options", [
    {"baselines": ["unknown"]}, {"horizon": 0}, {"horizon": 30}, {"train_size": 24},
    {"signal_lag": 0}, {"base_balance": 0}, {"base_balance": float("nan")},
    {"comission": 100}, {"comission": float("nan")}, {"threshold": float("nan")},
])
def test_invalid_evaluation_parameters(options):
    with pytest.raises(ValueError):
        _evaluate(**options)


def test_invalid_market_data_and_frequency():
    df = _ohlcv()
    frames = [df.drop("date"), df.head(0), df.with_columns(pl.col("date").cast(pl.String)),
              pl.concat([df.head(1), df]), df.with_columns(pl.lit(None).cast(pl.Datetime).alias("date")),
              df.with_columns(pl.lit("bad").alias("volume")), df.with_columns(pl.lit(float("nan")).alias("volume")),
              df.with_columns(pl.lit(0.0).alias("close")), df.filter(pl.col("date") != df["date"][100])]
    for frame in frames:
        with pytest.raises(ValueError):
            _evaluate(frame)
    with pytest.raises(ValueError, match="does not match"):
        _evaluate(df, freq="2h")


def test_unusable_features_or_training_labels():
    with pytest.raises(ValueError, match="No usable"):
        _evaluate(_ohlcv().with_columns(pl.lit(100.0).alias("volume")))
    with pytest.raises(ValueError, match="both label classes"):
        _evaluate(threshold=1e6)
    df = _ohlcv().with_row_index("row").with_columns(
        pl.when(pl.col("row") >= 15).then(100.0).otherwise(pl.col("volume")).alias("volume"),
    ).drop("row")
    with pytest.raises(ValueError, match="20 usable"):
        _evaluate(df)


def test_test_window_without_valid_features_stays_flat():
    df = _ohlcv(80).with_row_index("row").with_columns(
        pl.when(pl.col("row") >= 40).then(100.0).otherwise(pl.col("volume")).alias("volume"),
    ).drop("row")
    report = _evaluate(df, train_size=40, test_size=20, use_ta=False, baselines=[])
    assert report.folds[0].ml_num_trades == 0
    assert report.folds[0].ml_return_perc == 0
    assert report.folds[0].test_accuracy is None
    assert report.aggregate["median_test_roc_auc"] is None


def test_single_class_test_labels_have_no_auc():
    df = _ohlcv(80).with_row_index("row").with_columns(
        pl.when(pl.col("row") >= 60).then(pl.col("close").get(59)).otherwise(pl.col("close")).alias("close"),
    ).drop("row")
    report = _evaluate(df, train_size=40, test_size=20, use_ta=False, baselines=[])
    assert report.folds[0].test_accuracy is not None
    assert report.folds[0].test_roc_auc is None
