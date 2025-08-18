import json
from pathlib import Path

from fast_trade.ml.evolution.genetic_algorithm import GeneticAlgorithm
from fast_trade.ml.evolution.models import GeneDefinition, OptimizationConfig
from fast_trade.ml.evolution.reporter import (
    CompositeReporter,
    FileReporter,
    ConsoleReporter,
)


def tiny_base_strategy():
    return {
        "freq": "1h",
        "datapoints": [
            {"name": "sma_10", "transformer": "sma", "args": [10]},
            {"name": "sma_20", "transformer": "sma", "args": [20]},
        ],
        "enter": [["sma_10", ">", "sma_20"]],
        "exit": [["sma_10", "<", "sma_20"]],
        "predefined_sets": {
            "transformers": ["sma", "ema"],
            "operators": ["<", ">"],
            "columns": ["close", "open", "low", "high", "volume"],
        },
        "symbol": "BTC-USD",
        "exchange": "coinbase",
        "base_balance": 1000.0,
        "comission": 0.0,
        "lot_size_perc": 1.0,
    }


def test_ga_runs_and_writes_payload(tmp_path, monkeypatch):
    # mock run_backtest to avoid IO and data dependencies
    def fake_run_backtest(strategy):
        return {"summary": {"win_rate": 0.5}}

    monkeypatch.setattr("fast_trade.run_backtest", fake_run_backtest)
    # Minimal genes: one categorical, one int
    genes = [
        GeneDefinition(name="freq", type="categorical", values_ref="frequencies"),
        GeneDefinition(name="num_enter", type="int", args=[0, 1]),
    ]

    cfg = OptimizationConfig(
        num_generations=1,
        sol_per_pop=4,
        num_parents_mating=2,
        parallel_processing=1,
        use_parallel=False,
        mutation_percent_genes=0.0,
    )

    fitness = {"win_rate": 1.0}
    base = tiny_base_strategy()
    # include frequencies for categorical gene
    base_cfg = {
        "predefined_sets": {
            "frequencies": ["1h", "2h"],
            "operators": ["<", ">"],
            "transformers": ["sma", "ema"],
            "columns": ["close", "open", "low", "high", "volume"],
        }
    }

    ga = GeneticAlgorithm(
        base_strategy=base,
        genes=genes,
        config=cfg,
        fitness=fitness,
        run_id="test_run",
        api_url=None,
        config_file=base_cfg,
    )
    # Redirect winners dir and reporter to tmp
    ga.winners_dir = str(tmp_path)
    ga.reporter = CompositeReporter(
        [ConsoleReporter(), FileReporter(str(tmp_path), "payload.json")]
    )

    res = ga.run()
    # payload file should exist
    payload_path = Path(tmp_path) / "payload.json"
    assert payload_path.exists()
    # current and best winners should exist
    assert (Path(tmp_path) / "current.json").exists()
    assert (Path(tmp_path) / "best.json").exists()
    # result sanity
    assert res.fitness == ga.best_fitness
    assert isinstance(res.mapped_genes, list)
