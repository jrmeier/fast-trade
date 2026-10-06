"""Search contracts, chronology, audit files and real spawn-worker checks."""

from dataclasses import replace
import datetime
import hashlib

import numpy as np
import polars as pl
from polars.testing import assert_frame_equal
import pytest
import yaml

from fast_trade.ml import search_batch as batch, search_config as config, walk_forward as wf


def _df(rows=260):
    rng = np.random.default_rng(3)
    close = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, rows))
    return pl.DataFrame({
        "date": [datetime.datetime(2024, 1, 1) + datetime.timedelta(hours=i) for i in range(rows)],
        "open": np.r_[close[0], close[:-1]], "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": rng.uniform(50, 400, rows),
    })


def _raw():
    cut = str(_df()["date"][180])
    return dict(
        name="test_search", freq="1h", comission=0.1,
        data=dict(search_start="2024-01-01", search_stop=cut, holdout_start=cut),
        space=dict(horizons=[5], thresholds=[0.0], train_sizes=[60, 80], test_sizes=[30],
                   use_ta=[True, False], include_basic=[True]),
        screen=dict(baselines=["buy_hold"], min_trades=0, top_n=3),
        promote=dict(baselines=["buy_hold", "rsi", "random"], min_trades=0, top_n=2),
        holdout=dict(baselines=["buy_hold", "rsi"], must_beat=["buy_hold", "rsi"], min_trades=0, top_n=1),
    )


def _spec():
    return config.load_search_spec(_raw())


def test_load_expand_and_freeze_contract(tmp_path):
    path = tmp_path / "spec.yml"
    path.write_text(yaml.safe_dump(_raw()))
    spec = config.load_search_spec(path)
    trials = config.expand_trials(spec)
    assert len(trials) == 4
    assert len(config.expand_trials(spec, limit=1)) == 1
    assert config.expand_trials(spec, stage="promote")[0].baselines == spec.promote.baselines
    assert config.expand_trials(spec, baselines=["rsi"])[0].baselines == ("rsi",)
    assert trials[0].trial_id == config.expand_trials(spec)[0].trial_id
    assert config.trial_id_for({"x": 1, "y": 2}) == config.trial_id_for({"y": 2, "x": 1})
    assert config.trial_id_for({"x": 1}) != config.trial_id_for({"x": 2})
    with pytest.raises(AttributeError):
        spec.comission = 2
    mixed = replace(spec, space=replace(spec.space, include_basic=(True, False)))
    assert len(config.expand_trials(mixed)) == 6  # no trial with both feature families disabled
    scalar = _raw()
    scalar["space"] = dict(horizons=5, thresholds=0, train_sizes=60, test_sizes=30, use_ta=False)
    assert len(config.expand_trials(config.load_search_spec(scalar))) == 1
    with pytest.raises(FileNotFoundError):
        config.load_search_spec(tmp_path / "missing.yml")
    path.write_text("- not a mapping\n")
    with pytest.raises(ValueError):
        config.load_search_spec(path)


@pytest.mark.parametrize("change", [
    {"horizons": []}, {"horizons": [5, 5]}, {"test_sizes": [30, 40]}, {"freqs": ["1h", "2h"]},
    {"train_sizes": [1]}, {"test_sizes": [5]}, {"horizons": [0]}, {"horizons": [True]},
    {"thresholds": [float("nan")]}, {"use_ta": ["false"]}, {"use_ta": [False], "include_basic": [False]},
    {"freqs": ["0h"]}, {"unknown": [1]},
])
def test_invalid_search_space(change):
    raw = _raw()
    raw["space"].update(change)
    with pytest.raises(ValueError):
        config.load_search_spec(raw)


@pytest.mark.parametrize("change", [
    {"name": "../bad"}, {"name": ".."}, {"comission": 100}, {"base_balance": 0}, {"signal_lag": 0},
    {"signal_lag": True}, {"random_state": -1}, {"freq": "2h", "space": {"freqs": ["1h"]}},
    {"typo": 1}, {"space": []}, {"screen": {"must_beat": ["buy_hold"]}},
])
def test_invalid_spec(change):
    raw = _raw()
    raw.update(change)
    with pytest.raises(ValueError):
        config.load_search_spec(raw)


@pytest.mark.parametrize("split", [
    config.DataSplit(), config.DataSplit(search_stop="2024-02-01", holdout_start="2024-01-01"),
    config.DataSplit(search_start="2024-01-01", holdout_start="2024-01-01"),
    config.DataSplit(holdout_start="2024-02-01", holdout_stop="2024-01-01"),
])
def test_invalid_date_splits(split):
    with pytest.raises(ValueError):
        split.validate()


@pytest.mark.parametrize("rules", [
    config.StageRules(baselines=()), config.StageRules(baselines=("magic",)),
    config.StageRules(baselines=("rsi",), must_beat=("buy_hold",)),
    config.StageRules(min_trades=-1), config.StageRules(top_n=0),
])
def test_invalid_stage_rules(rules):
    with pytest.raises(ValueError):
        rules.validate()


def test_half_open_utc_slices_and_invalid_data():
    df, spec = _df(), _spec()
    for frame in (df, df.with_columns(pl.col("date").dt.replace_time_zone("UTC")),
                  df.with_columns(pl.col("date").dt.replace_time_zone("UTC").dt.convert_time_zone("America/Denver"))):
        search = config.slice_search_df(frame, spec)
        holdout = config.slice_holdout_df(frame, spec)
        assert search.height == 180
        assert holdout.height == 80
        assert search["date"][-1] < holdout["date"][0]
    implicit = replace(spec, data=replace(spec.data, search_stop=None, search_start=None, holdout_stop=str(df["date"][-1])))
    assert config.slice_search_df(df, implicit).height == 180
    assert config.slice_holdout_df(df, implicit).height == 79
    for frame in (df.head(0), df.drop("date"), df.with_columns(pl.col("date").cast(pl.String))):
        with pytest.raises(ValueError):
            config.slice_search_df(frame, spec)
    with pytest.raises(ValueError, match="No rows"):
        config.slice_by_split(df, "2030-01-01", None)
    shifted = replace(spec, data=replace(spec.data, holdout_start="2024-01-08T05:00:00-07:00"))
    assert config.slice_holdout_df(df, shifted).height == 80
    shifted.data.validate()
    with pytest.raises(ValueError, match="nonempty"):
        config.DataSplit(holdout_start=" ").validate()


def test_fair_windows_across_training_sizes_and_features(tmp_path):
    trials = config.expand_trials(_spec())
    results = batch.run_trials(_df().head(180), trials, run_dir=tmp_path)
    assert all(r.status == "ok" for r in results)
    windows = [[(f.test_start, f.test_end) for f in r.report.folds] for r in results]
    assert windows == [windows[0]] * len(windows)
    for r in results:
        assert r.report.folds[0].train_rows == r.trial.train_size - r.trial.horizon
        assert r.report.folds[0].test_start == str(_df()["date"][100])


def test_spawn_workers_match_serial_results(tmp_path):
    trials = config.expand_trials(_spec(), limit=2)
    serial = batch.run_trials(_df().head(180), trials, run_dir=tmp_path / "serial")
    parallel = batch.run_trials(_df().head(180), trials, run_dir=tmp_path / "parallel", workers=2)
    assert [r.row for r in serial] == [r.row for r in parallel]
    assert all(r.status == "ok" for r in parallel)
    for a, b in zip(serial, parallel):
        assert_frame_equal(wf.report_to_frame(a.report), wf.report_to_frame(b.report))


def test_fixed_holdout_labels_do_not_use_holdout_prices(monkeypatch):
    captured = []
    original = wf.HistGradientBoostingClassifier

    def factory(**options):
        model = original(**options)
        fit = model.fit

        def record(x, y):
            captured.append((x.copy(), y.copy()))
            return fit(x, y)

        model.fit = record
        return model

    monkeypatch.setattr(wf, "HistGradientBoostingClassifier", factory)
    trial = config.expand_trials(_spec(), limit=1)[0]
    df = _df()
    first = batch.confirm_holdout(df.head(180), df.slice(180), trial, baselines=["buy_hold"])
    changed = df.slice(180).with_columns((pl.col("close") * 5).alias("close"))
    second = batch.confirm_holdout(df.head(180), changed, trial, baselines=["buy_hold"])
    assert first.status == second.status == "ok"
    assert len(captured) == 2  # exactly one fit per confirmation; no holdout refit
    np.testing.assert_array_equal(captured[0][0], captured[1][0])
    np.testing.assert_array_equal(captured[0][1], captured[1][1])
    metrics = first.report.folds[0]
    assert metrics.train_rows == trial.train_size - trial.horizon
    assert metrics.purged_train_rows == trial.horizon
    assert first.row["beats_rsi"] is None
    assert first.row["pct_folds_beat_rsi"] is None


def test_selection_and_stage_artifacts_are_frozen_before_holdout(tmp_path, monkeypatch):
    df, spec = _df(), _spec()
    original = batch.confirm_holdout
    calls = []
    output = tmp_path / "first"

    def confirm(search, holdout, trial, **options):
        selection = yaml.safe_load((output / "selection.yml").read_text())
        assert trial.trial_id in selection["trial_ids"]
        assert selection["basis"] == "search data only"
        calls.append(trial.trial_id)
        return original(search, holdout, trial, **options)

    monkeypatch.setattr(batch, "confirm_holdout", confirm)
    first = batch.run_search(df, spec, run_dir=output, confirm=True)
    monkeypatch.setattr(batch, "confirm_holdout", original)
    changed = df.with_columns(pl.when(pl.col("date") >= df["date"][180]).then(pl.col("close") * 5).otherwise(pl.col("close")).alias("close"))
    second = batch.run_search(changed, spec, run_dir=tmp_path / "second", confirm=True)
    assert calls
    assert_frame_equal(first["screen_ranked"], second["screen_ranked"])
    assert_frame_equal(first["promote_ranked"], second["promote_ranked"])
    assert (output / "selection.yml").read_bytes() == (tmp_path / "second" / "selection.yml").read_bytes()
    chosen = calls[0]
    for stage in ("screen", "promote", "holdout"):
        trial_dir = output / "trials" / stage / chosen
        assert (trial_dir / "folds.csv").is_file()
        summary = yaml.safe_load((trial_dir / "summary.yml").read_text())
        assert summary["row"]["stage"] == stage
        if stage == "holdout":
            assert "passed" in summary["row"]
    saved = yaml.safe_load((output / "spec.yml").read_text())
    assert config.load_search_spec(output / "spec.yml") == spec
    assert saved["comission"] == spec.comission
    assert saved["space"]["train_sizes"] == [60, 80]
    run = yaml.safe_load((output / "run.yml").read_text())
    for name, digest in run["input_sha256"].items():
        assert hashlib.sha256((output / f"{name}.parquet").read_bytes()).hexdigest() == digest
    assert_frame_equal(pl.read_parquet(output / "search.parquet"), df.head(180))
    with pytest.raises(FileExistsError):
        batch.run_search(df, spec, run_dir=output)


def test_no_confirmation_does_not_access_holdout(tmp_path):
    payload = batch.run_search(_df().head(180), _spec(), run_dir=tmp_path / "screen", promote=False)
    assert payload["holdout_results"] == []
    assert payload["promote_results"] == []
    assert payload["holdout"].is_empty()
    assert not (tmp_path / "screen" / "holdout.parquet").exists()
    limited = batch.run_search(_df().head(180), _spec(), run_dir=tmp_path / "limited", limit=1, promote=False)
    first_id = limited["screen"][0].trial.trial_id
    corresponding = next(result for result in payload["screen"] if result.trial.trial_id == first_id)
    assert limited["screen"][0].row == corresponding.row
    assert_frame_equal(wf.report_to_frame(limited["screen"][0].report), wf.report_to_frame(corresponding.report))
    confirmed = batch.run_search(_df(), _spec(), run_dir=tmp_path / "direct", promote=False, confirm=True)
    assert confirmed["holdout_results"]
    empty = replace(_spec(), screen=replace(_spec().screen, min_trades=1_000_000))
    no_candidates = batch.run_search(_df(), empty, run_dir=tmp_path / "empty", confirm=True)
    assert no_candidates["holdout_results"] == []


def test_promotion_keeps_identical_ml_returns(tmp_path):
    payload = batch.run_search(_df(), _spec(), run_dir=tmp_path / "promote")
    screen = {result.trial.trial_id: result for result in payload["screen"]}
    assert payload["promote_results"]
    for result in payload["promote_results"]:
        previous = screen[result.trial.trial_id]
        assert result.row["median_ml_return_perc"] == previous.row["median_ml_return_perc"]
        assert result.row["total_ml_trades"] == previous.row["total_ml_trades"]


def test_failure_artifacts_and_invalid_execution(tmp_path):
    trial = config.expand_trials(_spec(), limit=1)[0]
    invalid = replace(trial, horizon=30)
    result = batch.execute_trial(_df(), invalid)
    assert result.status == "failed"
    assert "ValueError" in result.error
    batch.persist_trial(tmp_path, result)
    assert yaml.safe_load(open(result.summary_path))["status"] == "failed"
    with pytest.raises(FileExistsError):
        batch.persist_trial(tmp_path, result)
    assert batch.confirm_holdout(_df().head(5), _df().slice(180), trial, baselines=["buy_hold"]).status == "failed"
    bad = _df().with_columns(pl.lit(100.0).alias("volume"))
    results = batch.run_trials(bad, [trial], run_dir=tmp_path / "bad")
    assert results[0].status == "failed"
    assert batch.rank_trials([r.row for r in results]).is_empty()
    for limit in (0, -1, True):
        with pytest.raises(ValueError):
            config.expand_trials(_spec(), limit=limit)
    for workers, trials in ((0, [trial]), (1, [])):
        with pytest.raises(ValueError):
            batch.run_trials(_df(), trials, run_dir=tmp_path, workers=workers)
    with pytest.raises(ValueError):
        batch.run_search(_df(), _spec(), run_dir=tmp_path / "workers", workers=0)


def test_rank_ties_and_holdout_gates():
    rows = [dict(trial_id=name, status="ok", total_ml_trades=5, median_ml_return_perc=1.0, composite_score=101.0)
            for name in ("b", "a")]
    rows.append(dict(trial_id="failure", status="failed", total_ml_trades=100, composite_score=float("-inf")))
    ranked = batch.rank_trials(rows)
    assert ranked["trial_id"].to_list() == ["a", "b"]
    assert batch.promote_trials(ranked, top_n=1)["trial_id"].to_list() == ["a"]
    assert batch.rank_trials([]).is_empty()
    assert batch.composite_score({"pct_folds_beat_buy_hold": 80, "pct_folds_beat_rsi": 20, "median_ml_return_perc": 1}) == 101
    row = dict(status="ok", total_ml_trades=5, beats_buy_hold=True)
    assert batch.holdout_passes(row, ["buy_hold"], 5)
    assert not batch.holdout_passes(row, ["rsi"], 0)
    assert not batch.holdout_passes(row, ["buy_hold"], 6)
    assert not batch.holdout_passes(dict(row, status="failed"), [], 0)
    with pytest.raises(ValueError):
        batch.holdout_passes(row, ["unknown"], 0)


def test_fixed_split_rejects_unordered_overlapping_or_missing_ranges():
    df = _df()
    with pytest.raises(ValueError):
        wf.walk_forward_evaluate(df, train_size=60, test_size=30, test_start_row=10)
    with pytest.raises(ValueError):
        wf.walk_forward_evaluate(df, test_start_row=1.5)
    for train, test in ((df["date"].head(0), df["date"].slice(180)),
                        (df["date"].head(180), df["date"].slice(180).reverse()),
                        (df["date"].head(180), df["date"].slice(170)),
                        (df["date"].head(180), pl.Series("date", [datetime.datetime(2030, 1, 1)]))):
        with pytest.raises(ValueError):
            wf.evaluate_fixed_split(df, train, test)


def test_direct_dataclass_validation():
    with pytest.raises(ValueError):
        config.SearchSpace(horizons=(True,)).validate()
    with pytest.raises(ValueError):
        config.SearchSpace(use_ta=(1,)).validate()


def test_fixed_split_distinguishes_repeated_daylight_saving_hour():
    start = datetime.datetime(2024, 10, 31, 20)
    dates = pl.datetime_range(start, start + datetime.timedelta(hours=99), interval="1h", eager=True)
    df = _df(100).with_columns(dates.dt.replace_time_zone("UTC").dt.convert_time_zone("America/Denver").alias("date"))
    assert df["date"][59].hour == df["date"][60].hour == 1
    with batch.threadpool_limits(limits=1):
        fold = wf.evaluate_fixed_split(df, df["date"].slice(30, 30), df["date"].slice(60, 30),
                                       horizon=5, threshold=0.0, use_ta=False, baselines=["buy_hold"])
    assert fold.test_start == str(df["date"][60])
