import datetime

import numpy as np
import polars as pl

from fast_trade.ml.markov import (
    calculate_transition_matrix,
    convert_states_to_prices,
    create_hmm,
    define_granular_states,
    simulate_markov_chain,
)


def _kline(rows: int = 200, seed: int = 3) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1.0 + rng.normal(0.001, 0.02, size=rows))
    return pl.DataFrame(
        {
            "date": pl.datetime_range(
                start=datetime.datetime(2024, 1, 1),
                end=datetime.datetime(2024, 1, 1) + datetime.timedelta(days=rows - 1),
                interval="1d",
                eager=True,
            ),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.uniform(100, 1000, size=rows),
        }
    )


def test_create_hmm_adds_future_predictions(monkeypatch):
    class FakeModel:
        n_components = 3
        means_ = np.array([[0.1], [0.2], [0.3]])

        def fit(self, observations):
            return self

        def predict(self, observations):
            return np.zeros(len(observations), dtype=int)

        def sample(self, n):
            return np.zeros((n, 1), dtype=int), None

    monkeypatch.setattr("fast_trade.ml.markov.hmm.GaussianHMM", lambda **kwargs: FakeModel())
    df = create_hmm(_kline())
    assert "hidden_state" in df.columns
    assert "future_state" in df.columns
    assert "predicted_price" in df.columns
    assert df["predicted_price"].is_not_null().any()


def test_define_granular_states_labels():
    df = _kline()
    close = df["close"].to_list()
    close[10] = close[9] * 1.03
    close[11] = close[10] * 0.97
    df = df.with_columns(pl.Series("close", close))
    labeled = define_granular_states(df)
    assert "state" in labeled.columns
    assert labeled["state"].is_in(
        [
            "Strong Increase",
            "Moderate Increase",
            "Slight Increase",
            "Stable",
            "Slight Decrease",
            "Moderate Decrease",
            "Strong Decrease",
        ]
    ).all()


def test_calculate_transition_matrix_and_simulation():
    df = define_granular_states(_kline())
    matrix = calculate_transition_matrix(df)
    assert matrix.shape == (7, 7)
    assert np.allclose(matrix.to_numpy().sum(axis=1), 1.0)

    np.random.seed(0)
    chain = simulate_markov_chain(matrix, "Stable", num_steps=5)
    assert len(chain) == 6
    assert chain[0] == "Stable"


def test_markov_main_guard(monkeypatch):
    monkeypatch.setattr("fast_trade.archive.db_helpers.get_kline", lambda **k: pl.DataFrame())
    monkeypatch.setattr("fast_trade.prepare_df", lambda df, backtest: df)
    import runpy

    runpy.run_module("fast_trade.ml.markov", run_name="__main__")


def test_convert_states_to_prices():
    prices = convert_states_to_prices(["Strong Increase", "Stable", "Strong Decrease"], 100.0)
    assert prices[0] == 100.0
    assert prices[1] > 100.0
    assert prices[-1] < prices[1]
