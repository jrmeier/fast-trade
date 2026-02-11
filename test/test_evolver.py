import os

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

    # 10*0.4 + 20*0.3 + 1.5*0.1 - 5*0.1 + 30*0.1 = 4 + 6 + 0.15 - 0.5 + 3 = 12.65
    assert pytest.approx(fitness, rel=1e-6) == 12.65


def test_save_json_creates_ml_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    filename = "sample.json"

    evolver.save_json({"strategy": {"foo": "bar"}}, filename)

    expected_path = tmp_path / "ml" / filename
    assert expected_path.exists()
