"""Tests for ML search config, ranking, persistence, and batch funnel."""

import numpy as np
import pandas as pd
import pytest
import yaml

from fast_trade.ml.search_batch import (
    composite_score,
    confirm_holdout,
    execute_trial,
    holdout_passes,
    promote_trials,
    rank_trials,
    run_search,
    run_trials,
)
from fast_trade.ml.search_config import (
    SearchSpace,
    StageRules,
    TrialConfig,
    expand_trials,
    load_search_spec,
    slice_holdout_df,
    slice_search_df,
    trial_id_for,
)
from fast_trade.ml.walk_forward import evaluate_fixed_split


def _synthetic_ohlcv(rows: int = 900, seed: int = 4, freq: str = "1h") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq=freq, tz="UTC")
    rets = rng.normal(0.0004, 0.012, size=rows)
    close = 80 * np.cumprod(1.0 + rets)
    high = close * (1.0 + rng.uniform(0.0, 0.01, size=rows))
    low = close * (1.0 - rng.uniform(0.0, 0.01, size=rows))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(50.0, 400.0, size=rows)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _spec_dict(**overrides):
    raw = {
        "name": "unit_search",
        "symbol": "BTCUSDT",
        "exchange": "binanceus",
        "freq": "1h",
        "comission": 0.0,
        "random_state": 1,
        "data": {
            "search_start": "2024-01-01",
            "search_stop": "2024-01-25",
            "holdout_start": "2024-01-25",
            "holdout_stop": "2024-02-10",
        },
        "space": {
            "horizons": [5],
            "thresholds": [0.0],
            "train_sizes": [220],
            "test_sizes": [60],
            "use_ta": [False],
            "include_basic": [True],
        },
        "screen": {"baselines": ["buy_hold"], "min_trades": 0, "top_n": 5},
        "promote": {"baselines": ["buy_hold"], "min_trades": 0, "top_n": 2},
        "holdout": {
            "baselines": ["buy_hold"],
            "min_trades": 0,
            "top_n": 1,
            "must_beat": ["buy_hold"],
        },
        "output": {"dir": "ft_archive/ml_search"},
    }
    raw.update(overrides)
    return raw


def test_load_search_spec_and_expand(tmp_path):
    path = tmp_path / "spec.yml"
    raw = _spec_dict()
    raw["space"]["horizons"] = [3, 5]
    raw["space"]["use_ta"] = [True, False]
    path.write_text(yaml.safe_dump(raw))
    spec = load_search_spec(path)
    assert spec.data.holdout_start == "2024-01-25"
    trials = expand_trials(spec)
    assert len(trials) == 4
    limited = expand_trials(spec, limit=2)
    assert len(limited) == 2
    assert all(item.stage == "screen" for item in trials)


def test_search_spec_validation_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_search_spec(tmp_path / "missing.yml")
    bad = tmp_path / "bad.yml"
    bad.write_text("- not a mapping\n")
    with pytest.raises(ValueError, match="mapping"):
        load_search_spec(bad)

    raw = _spec_dict()
    raw["data"]["holdout_start"] = None
    path = tmp_path / "no_holdout.yml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="holdout_start"):
        load_search_spec(path)

    raw = _spec_dict()
    raw["data"]["search_stop"] = "2024-11-01"
    raw["data"]["holdout_start"] = "2024-10-01"
    path = tmp_path / "overlap.yml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="search_stop"):
        load_search_spec(path)

    with pytest.raises(ValueError, match="Unknown baselines"):
        StageRules(baselines=("magic",)).validate()
    with pytest.raises(ValueError, match="must_beat"):
        StageRules(must_beat=("magic",)).validate()
    with pytest.raises(ValueError, match="min_trades"):
        StageRules(min_trades=-1).validate()
    with pytest.raises(ValueError, match="top_n"):
        StageRules(top_n=0).validate()
    with pytest.raises(ValueError, match="non-empty"):
        SearchSpace(horizons=tuple()).validate()
    with pytest.raises(ValueError, match="use_ta"):
        SearchSpace(use_ta=(False,), include_basic=(False,)).validate()


def test_slice_search_and_holdout():
    df = _synthetic_ohlcv(rows=800)
    spec = load_search_spec(_spec_dict())
    search = slice_search_df(df, spec)
    holdout = slice_holdout_df(df, spec)
    assert search.index.max() < holdout.index.min()
    with pytest.raises(ValueError, match="empty"):
        slice_search_df(df.iloc[0:0], spec)
    with pytest.raises(ValueError, match="No rows"):
        slice_search_df(df, load_search_spec(_spec_dict(
            data={
                "search_start": "2030-01-01",
                "search_stop": "2030-02-01",
                "holdout_start": "2030-02-01",
                "holdout_stop": "2030-03-01",
            }
        )))


def test_rank_promote_and_holdout_rules():
    rows = [
        {
            "trial_id": "a",
            "status": "ok",
            "total_ml_trades": 2,
            "pct_folds_beat_buy_hold": 80,
            "pct_folds_beat_rsi": 20,
            "median_ml_return_perc": 1.0,
            "composite_score": composite_score(
                {"pct_folds_beat_buy_hold": 80, "pct_folds_beat_rsi": 20, "median_ml_return_perc": 1.0}
            ),
        },
        {
            "trial_id": "b",
            "status": "ok",
            "total_ml_trades": 20,
            "pct_folds_beat_buy_hold": 50,
            "pct_folds_beat_rsi": 50,
            "median_ml_return_perc": 0.5,
            "composite_score": composite_score(
                {"pct_folds_beat_buy_hold": 50, "pct_folds_beat_rsi": 50, "median_ml_return_perc": 0.5}
            ),
        },
        {"trial_id": "c", "status": "failed", "total_ml_trades": 99, "composite_score": 0},
    ]
    ranked = rank_trials(rows, min_trades=5)
    assert list(ranked["trial_id"]) == ["b"]
    assert promote_trials(ranked, top_n=1).iloc[0]["trial_id"] == "b"
    assert rank_trials([], min_trades=1).empty
    assert promote_trials(pd.DataFrame(), top_n=3).empty
    assert holdout_passes(
        {"total_ml_trades": 6, "beats_buy_hold": True, "beats_rsi": True},
        ["buy_hold", "rsi"],
        5,
    )
    assert not holdout_passes({"total_ml_trades": 1, "beats_buy_hold": True}, ["buy_hold"], 5)
    only_thin = rank_trials(
        [{"trial_id": "z", "status": "ok", "total_ml_trades": 1, "composite_score": 1}],
        min_trades=10,
    )
    assert only_thin.empty
    no_status = rank_trials(
        [{"trial_id": "n", "total_ml_trades": 12, "composite_score": 1, "median_ml_return_perc": 0.1}]
    )
    assert list(no_status["trial_id"]) == ["n"]


def test_execute_trial_and_run_search(tmp_path):
    df = _synthetic_ohlcv(rows=900)
    spec = load_search_spec(_spec_dict())
    payload = run_search(
        df,
        spec,
        run_dir=tmp_path / "run",
        limit=1,
        workers=1,
        promote=True,
        confirm=True,
    )
    assert payload["screen"]
    assert (tmp_path / "run" / "ranking.csv").is_file()
    assert (tmp_path / "run" / "spec.yml").is_file()
    trial_dirs = list((tmp_path / "run" / "trials").iterdir())
    assert trial_dirs
    assert (trial_dirs[0] / "config.yml").is_file()


def test_execute_trial_failure_and_parallel(tmp_path, monkeypatch):
    df = _synthetic_ohlcv(rows=120)
    spec = load_search_spec(_spec_dict())
    trials = expand_trials(spec, limit=1)
    # Too little data for the configured windows.
    failed = execute_trial(df, trials[0])
    assert failed.status == "failed"
    run_trials(df, trials, run_dir=tmp_path / "fail", workers=1)

    bigger = _synthetic_ohlcv(rows=900)
    raw = _spec_dict()
    raw["space"]["horizons"] = [3, 5]
    spec2 = load_search_spec(raw)
    ok_trials = expand_trials(spec2, limit=2)

    class _Future:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _Pool:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, fn, payload):
            return _Future(fn(payload))

    monkeypatch.setattr("fast_trade.ml.search_batch.ProcessPoolExecutor", _Pool)
    monkeypatch.setattr("fast_trade.ml.search_batch.as_completed", lambda futures: futures)
    results = run_trials(bigger.iloc[:700], ok_trials, run_dir=tmp_path / "par", workers=2)
    assert len(results) == 2
    assert {item.status for item in results} <= {"ok", "failed"}


def test_confirm_holdout_and_fixed_split():
    df = _synthetic_ohlcv(rows=900)
    spec = load_search_spec(_spec_dict())
    search = slice_search_df(df, spec)
    holdout = slice_holdout_df(df, spec)
    trial = expand_trials(spec, limit=1)[0]
    result = confirm_holdout(search, holdout, trial, baselines=("buy_hold",))
    assert result.status in {"ok", "failed"}
    metrics = evaluate_fixed_split(
        df,
        search.index,
        holdout.index,
        horizon=5,
        threshold=0.0,
        use_ta=False,
        include_basic=True,
        freq="1h",
        comission=0.0,
        baselines=("buy_hold",),
    )
    assert metrics.test_rows > 0
    tiny = holdout.iloc[:2]
    failed = confirm_holdout(search, tiny, trial, baselines=("buy_hold",))
    assert failed.status == "failed"


def test_evaluate_fixed_split_errors():
    df = _synthetic_ohlcv(rows=200)
    with pytest.raises(ValueError, match="Unknown baselines"):
        evaluate_fixed_split(df, df.index[:80], df.index[80:120], baselines=("nope",))
    with pytest.raises(ValueError, match="non-empty"):
        evaluate_fixed_split(df, df.index[:0], df.index[:10], use_ta=False)
    with pytest.raises(ValueError, match="Too few"):
        evaluate_fixed_split(
            df,
            df.index[:25],
            df.index[25:40],
            horizon=20,
            threshold=0.0,
            use_ta=False,
            comission=0.0,
        )
    with pytest.raises(ValueError, match="Too few test"):
        evaluate_fixed_split(
            df,
            df.index[:80],
            df.index[80:82],
            horizon=5,
            threshold=0.0,
            use_ta=False,
            comission=0.0,
        )
    with pytest.raises(ValueError, match="both classes"):
        evaluate_fixed_split(
            df,
            df.index[:120],
            df.index[120:160],
            horizon=5,
            threshold=50.0,
            use_ta=False,
            comission=0.0,
        )


def test_evaluate_fixed_split_full_baselines(monkeypatch):
    df = _synthetic_ohlcv(rows=400)
    metrics = evaluate_fixed_split(
        df,
        df.index[:250],
        df.index[250:350],
        horizon=5,
        threshold=0.0,
        use_ta=True,
        include_basic=True,
        freq="1h",
        comission=0.0,
        baselines=("buy_hold", "rsi", "random"),
    )
    assert metrics.test_rows >= 5
    from fast_trade.ml import walk_forward as wf

    class _Empty:
        def dropna(self):
            return pd.DataFrame()

    monkeypatch.setattr(wf, "build_feature_matrix", lambda *a, **k: (_Empty(), ["ret_1"]))
    with pytest.raises(ValueError, match="No usable feature"):
        evaluate_fixed_split(
            df,
            df.index[:250],
            df.index[250:350],
            use_ta=False,
            horizon=5,
            threshold=0.0,
        )


def test_align_naive_index_and_scalar_space():
    idx = pd.date_range("2024-01-01", periods=10, freq="h")
    df = pd.DataFrame(
        {
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        },
        index=idx,
    )
    from fast_trade.ml.search_config import slice_by_split

    sliced = slice_by_split(df, "2024-01-01T00:00:00+00:00", "2024-01-01T05:00:00+00:00")
    assert len(sliced) == 5
    naive = slice_by_split(df, "2024-01-01", "2024-01-01T05:00:00")
    assert len(naive) == 5
    aware_idx = df.copy()
    aware_idx.index = df.index.tz_localize("UTC")
    converted = slice_by_split(
        aware_idx, "2024-01-01T00:00:00+00:00", "2024-01-01T05:00:00+00:00"
    )
    assert len(converted) == 5
    spec = load_search_spec(
        {
            "data": {"holdout_start": "2024-06-01"},
            "space": {"horizons": 5, "thresholds": 0.01, "train_sizes": 100, "test_sizes": 20},
        }
    )
    assert spec.space.horizons == (5,)


def test_trial_id_stable_and_row_helper():
    a = trial_id_for({"horizon": 5, "threshold": 0.01})
    b = trial_id_for({"threshold": 0.01, "horizon": 5})
    assert a == b
    cfg = TrialConfig(
        trial_id="x",
        horizon=5,
        threshold=0.0,
        train_size=220,
        test_size=60,
        step_size=60,
        use_ta=False,
        include_basic=True,
        freq="1h",
        comission=0.0,
        random_state=1,
        baselines=("buy_hold",),
    )
    assert "train_size" in cfg.walk_forward_kwargs()


def test_expand_skips_empty_feature_combo():
    spec = load_search_spec(_spec_dict())
    spec.space = SearchSpace(
        horizons=(5,),
        thresholds=(0.0,),
        train_sizes=(220,),
        test_sizes=(60,),
        use_ta=(True, False),
        include_basic=(True, False),
        freqs=("1h",),
    )
    trials = expand_trials(spec)
    assert len(trials) == 3
    assert not any((not t.use_ta) and (not t.include_basic) for t in trials)

    spec.space = SearchSpace(
        horizons=(5,),
        thresholds=(0.0,),
        train_sizes=(220,),
        test_sizes=(60,),
        use_ta=(False,),
        include_basic=(False,),
        freqs=("1h",),
    )
    with pytest.raises(ValueError, match="use_ta"):
        spec.validate()
    spec.validate = lambda: None
    spec.space = SearchSpace(
        horizons=(5,),
        thresholds=(0.0,),
        train_sizes=(220,),
        test_sizes=(60,),
        use_ta=(False,),
        include_basic=(False,),
        freqs=("1h",),
    )
    with pytest.raises(ValueError, match="no trials"):
        expand_trials(spec)


def test_write_table_empty(tmp_path):
    from fast_trade.ml.search_batch import write_table

    path = tmp_path / "empty.csv"
    write_table(path, pd.DataFrame())
    assert path.is_file()


def test_run_search_without_promote(tmp_path):
    df = _synthetic_ohlcv(rows=900)
    spec = load_search_spec(_spec_dict())
    payload = run_search(
        df,
        spec,
        run_dir=tmp_path / "nopromo",
        limit=1,
        workers=1,
        promote=False,
        confirm=False,
    )
    assert payload["promote_results"] == []
    assert payload["holdout"].empty
