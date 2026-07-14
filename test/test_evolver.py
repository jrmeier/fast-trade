import datetime as dt
import json

import numpy as np
import pytest

from fast_trade.ml import evolver


def test_modify_strategy_transformer_placeholder():
    base_strategy = {
        "datapoints": [
            {"name": "ma_short", "transformer": "#ma_transformer", "args": [5]},
        ],
        "enter": [["close", ">", "ma_short"]],
        "exit": [["close", "<", "ma_short"]],
    }
    genes = [("ma_transformer", "ema")]

    modified = evolver.modify_strategy(base_strategy, genes)

    assert modified["datapoints"][0]["transformer"] == "ema"


def test_fitness_uses_summary_keys(monkeypatch):
    def fake_run_backtest(_strategy):
        return {
            "summary": {
                "market_adjusted_return": 10.0,
                "return_perc": 20.0,
                "sharpe_ratio": 1.5,
                "drawdown_metrics": {"max_drawdown_pct": -5.0},
                "num_trades": 30,
            }
        }

    monkeypatch.setattr(evolver, "run_backtest", fake_run_backtest)

    fitness = evolver.fitness_func(
        solution=[1], solution_idx=0, strategy={"datapoints": [], "enter": [], "exit": []}, genes=[("x", 1)]
    )

    assert pytest.approx(fitness, rel=1e-6) == 15.15


def test_save_yaml_creates_ml_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    filename = "sample.yml"

    evolver.save_yaml({"strategy": {"foo": "bar"}}, filename)

    expected_path = tmp_path / "ml" / filename
    assert expected_path.exists()


def test_normalize_types():
    now = dt.datetime(2024, 1, 1, 12, 0)
    today = dt.date(2024, 1, 1)
    assert evolver._normalize_types(now) == now.isoformat()
    assert evolver._normalize_types(today) == today.isoformat()
    assert evolver._normalize_types({"a": now, "b": [np.int64(3)]}) == {
        "a": now.isoformat(),
        "b": [3],
    }
    assert evolver._normalize_types((np.float64(1.5),)) == [1.5]
    assert evolver._normalize_types(np.array([1, 2])) == [1, 2]
    assert evolver._normalize_types("plain") == "plain"


def test_modify_strategy_with_columns_and_callables():
    base = {
        "freq": "#freq",
        "datapoints": [
        {"name": "ma", "transformer": "#transformer", "args": ["#period", "#data_column"]},
    ],
    "enter": [["close", ">", "#data_column"]],
        "exit": [],
        "start": dt.datetime(2024, 1, 1),
    }
    genes = [
        ("freq", lambda: 2),
        ("transformer", "sma"),
        ("period", lambda: 4.7),
        ("data_column", lambda: 5),
    ]
    modified = evolver.modify_strategy(base, genes, with_columns=True)
    assert modified["freq"] == "15Min"
    assert modified["datapoints"][0]["transformer"] == "sma"
    assert modified["datapoints"][0]["args"] == [5, "open"]
    assert modified["enter"][0][2] == "open"


def test_modify_strategy_static_column_and_invalid_transformer():
    base = {
        "datapoints": [{"name": "x", "transformer": "#t", "args": [1.2]}],
        "enter": [],
        "exit": [],
    }
    genes = [("t", "missing_transformer")]
    with pytest.raises(ValueError, match="Invalid transformer"):
        evolver.modify_strategy(base, genes)

    base2 = {
        "datapoints": [{"name": "x", "transformer": "sma", "args": [1]}],
        "enter": [["#price_column", ">", 1]],
        "exit": [],
    }
    modified = evolver.modify_strategy(base2, [("price_column", 6)], with_columns=True)
    assert modified["enter"][0][0] == "low"


def test_modify_strategy_freq_string_and_bounds():
    base = {"datapoints": [], "enter": [], "exit": []}
    assert evolver.modify_strategy(base, [("freq", "4h")])["freq"] == "4h"
    assert evolver.modify_strategy(base.copy(), [("freq", 999)])["freq"] == "12h"
    assert evolver.modify_strategy(base.copy(), [("freq", lambda: -1)])["freq"] == "1Min"


def test_get_metric_nested():
    summary = {"drawdown_metrics": {"max_drawdown_pct": -3.0}}
    assert evolver._get_metric(summary, "drawdown_metrics.max_drawdown_pct") == -3.0
    assert evolver._get_metric(summary, "missing.path", 9) == 9
    assert evolver._get_metric({"x": 1}, "x.y", 0) == 0


def test_fitness_func_paths(monkeypatch):
    def fake_run_backtest(_strategy):
        return {
            "summary": {
                "return_perc": 1.0,
                "market_adjusted_return": 1.0,
                "sharpe_ratio": 1.0,
                "drawdown_metrics": {"max_drawdown_pct": -1.0},
                "num_trades": 1,
                "risk_metrics": {"sortino_ratio": 1.0},
            }
        }

    monkeypatch.setattr(evolver, "run_backtest", fake_run_backtest)
    strategy = {"datapoints": [], "enter": [], "exit": []}

    conservative = evolver.fitness_func(
        solution=[1],
        solution_idx=0,
        strategy=strategy,
        genes=[("x", 1)],
        fitness_config={"preset": "conservative"},
    )
    assert isinstance(conservative, float)

    low_trades = evolver.fitness_func(
        solution=[1],
        solution_idx=0,
        strategy=strategy,
        genes=[("x", 1)],
        fitness_config={"weights": {"return_perc": 1.0}, "min_trades": 10, "low_trades_penalty": -2.0},
    )
    assert isinstance(low_trades, float)


def test_fitness_func_backtest_error(monkeypatch):
    errors = []
    monkeypatch.setattr(
        evolver,
        "run_backtest",
        lambda _s: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert evolver.fitness_func(
        solution=[1],
        solution_idx=0,
        strategy={"datapoints": [], "enter": [], "exit": []},
        genes=[("x", 1)],
        error_callback=errors.append,
    ) == -1e9
    assert errors


def test_fitness_func_callable_genes_and_column_mapping(monkeypatch):
    monkeypatch.setattr(
        evolver,
        "run_backtest",
        lambda _s: {"summary": {"return_perc": 5.0, "num_trades": 10}},
    )
    strategy = {"datapoints": [], "enter": [], "exit": []}
    genes = [("x", lambda: 1)]
    score = evolver.fitness_func(None, 0, strategy, genes)
    assert score > 0

    mapped_score = evolver.fitness_func(
        solution=[5],
        solution_idx=0,
        strategy=strategy,
        genes=[("price_column", 5)],
    )
    assert mapped_score > 0


def test_fitness_wrapper(monkeypatch):
    monkeypatch.setattr(evolver, "fitness_func", lambda *a, **k: 42.0)
    assert evolver.fitness_wrapper(None, [1], 0, {}, [("x", 1)], None, None) == 42.0


def test_save_yaml_fallback_without_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    real_import = __import__

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", broken_import)
    evolver.save_yaml({"a": 1}, "")
    files = list((tmp_path / "ml").glob("*.yml"))
    assert files
    assert json.loads(files[0].read_text(encoding="utf-8"))["a"] == 1


def test_save_yaml_creates_archive_root(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCHIVE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    evolver.save_yaml({"a": 1}, "out.yml")
    assert (tmp_path / "ft_archive" / "ml" / "out.yml").exists()


def test_optimize_strategy_callable_genes(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    monkeypatch.setattr(
        evolver,
        "run_backtest",
        lambda _s: {
            "summary": {
                "return_perc": 10.0,
                "market_adjusted_return": 5.0,
                "sharpe_ratio": 1.0,
                "drawdown_metrics": {"max_drawdown_pct": -1.0},
                "num_trades": 10,
            }
        },
    )
    base = {"datapoints": [], "enter": [], "exit": []}
    genes = [("x", lambda: 1), ("y", lambda: 2)]
    progress = []
    mapped, fitness = evolver.optimize_strategy(
        base,
        genes,
        num_generations=2,
        progress_callback=progress.append,
    )
    assert mapped
    assert fitness > 0
    assert progress


def test_optimize_strategy_ga_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    monkeypatch.setattr(
        evolver,
        "run_backtest",
        lambda _s: {
            "summary": {
                "return_perc": 10.0,
                "market_adjusted_return": 5.0,
                "sharpe_ratio": 1.0,
                "drawdown_metrics": {"max_drawdown_pct": -1.0},
                "num_trades": 10,
            }
        },
    )

    class FakeGA:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.generations_completed = 0
            self.on_generation = kwargs.get("on_generation")

        def run(self):
            self.generations_completed = 1
            if self.on_generation:
                self.on_generation(self)

        def best_solution(self):
            return [1, 0, 2, 1], 12.34, 0

    monkeypatch.setattr(evolver.pygad, "GA", FakeGA)
    base = {
        "freq": "#freq",
        "datapoints": [],
        "enter": [],
        "exit": [],
    }
    genes = [
        ("freq", {"low": 0, "high": 2}),
        ("ma_column", [0, 1, 2, 3]),
        ("period", None),
        ("x", {"low": 1, "high": 5}),
    ]
    progress = []
    mapped, fitness = evolver.optimize_strategy(
        base,
        genes,
        num_generations=1,
        sol_per_pop=2,
        progress_callback=progress.append,
        parallel_processing=4,
        gene_space_provider=lambda name: {"low": 1, "high": 3},
    )
    assert mapped[0][0] == "freq"
    assert fitness == 12.34
    assert progress


def test_modify_strategy_nested_placeholders_and_callables():
    base = {
        "datapoints": [
            {
                "name": "x",
                "transformer": "sma",
                "args": [["#nested"]],
                "tag": {"value": "#callable_gene"},
            }
        ],
        "enter": [],
        "exit": [],
        "note": "#top_level",
    }
    genes = [
        ("nested", lambda: 3),
        ("callable_gene", lambda: "dynamic"),
        ("top_level", "static"),
    ]
    modified = evolver.modify_strategy(base, genes)
    assert modified["datapoints"][0]["args"] == [[3]]
    assert modified["datapoints"][0]["tag"]["value"] == "dynamic"
    assert modified["note"] == "static"


def test_modify_strategy_column_gene_static_int():
    base = {"datapoints": [], "enter": [], "exit": []}
    genes = [("ma_column", 2)]
    modified = evolver.modify_strategy(base, genes, with_columns=True)
    assert modified  # mapped through with_columns path


def test_save_yaml_appends_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    evolver.save_yaml({"a": 1}, "noext")
    assert (tmp_path / "ml" / "noext.yml").exists()


def test_optimize_strategy_ga_error_callback(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))

    def failing_backtest(_strategy):
        raise RuntimeError("backtest failed")

    monkeypatch.setattr(evolver, "run_backtest", failing_backtest)

    class FakeGA:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.generations_completed = 0
            self.on_generation = kwargs.get("on_generation")

        def run(self):
            fitness = self.kwargs["fitness_func"](self, [1], 0)
            assert fitness == -1e9
            if self.on_generation:
                self.on_generation(self)

        def best_solution(self):
            return [1], -1e9, 0

    monkeypatch.setattr(evolver.pygad, "GA", FakeGA)
    evolver.optimize_strategy(
        {"datapoints": [], "enter": [], "exit": []},
        [("rsi_threshold", None)],
        num_generations=1,
        sol_per_pop=1,
    )
    assert "Fitness error" in capsys.readouterr().out


def test_normalize_types_numpy_import_failure(monkeypatch):
    real_import = __import__

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "numpy":
            raise ImportError("no numpy")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", broken_import)
    assert evolver._normalize_types([1, 2]) == [1, 2]


def test_evolver_main_block(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    source = Path(evolver.__file__).read_text(encoding="utf-8")
    source = source.replace(
        'if __name__ == "__main__":',
        'if __name__ == "__main__":\n    def optimize_strategy(*_a, **_k):\n        return ([], 0.0)',
        1,
    )
    namespace = {"__name__": "__main__", "__file__": evolver.__file__}
    exec(compile(source, evolver.__file__, "exec"), namespace)


def test_optimize_strategy_default_gene_space_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    monkeypatch.setattr(
        evolver,
        "run_backtest",
        lambda _s: {
            "summary": {
                "return_perc": 1.0,
                "market_adjusted_return": 1.0,
                "sharpe_ratio": 1.0,
                "drawdown_metrics": {"max_drawdown_pct": -1.0},
                "num_trades": 10,
            }
        },
    )

    captured = {}

    class FakeGA:
        def __init__(self, **kwargs):
            captured["gene_space"] = kwargs.get("gene_space")

        def run(self):
            return None

        def best_solution(self):
            return [1, 2, 3, 4], 1.0, 0

    monkeypatch.setattr(evolver.pygad, "GA", FakeGA)
    genes = [
        ("rsi_upper", None),
        ("rsi_period", None),
        ("ema_fast", None),
        ("other_gene", None),
    ]
    evolver.optimize_strategy(
        {"datapoints": [], "enter": [], "exit": []},
        genes,
        num_generations=1,
        sol_per_pop=1,
    )
    assert len(captured["gene_space"]) == 4
