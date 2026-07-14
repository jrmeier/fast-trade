import numpy as np
import pandas as pd

from fast_trade.ml.markov import (
    calculate_transition_matrix,
    convert_states_to_prices,
    create_hmm,
    define_granular_states,
    simulate_markov_chain,
)


def _kline(rows: int = 200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq="D")
    close = 100 * np.cumprod(1.0 + rng.normal(0.001, 0.02, size=rows))
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.uniform(100, 1000, size=rows),
        },
        index=idx,
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
    assert df["predicted_price"].notna().any()


def test_define_granular_states_labels():
    df = _kline()
    df.loc[df.index[10], "close"] = df["close"].iloc[9] * 1.03
    df.loc[df.index[11], "close"] = df["close"].iloc[10] * 0.97
    labeled = define_granular_states(df)
    assert "state" in labeled.columns
    assert labeled["state"].isin(
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
    assert (matrix.sum(axis=1).round(6) == 1.0).all()

    np.random.seed(0)
    chain = simulate_markov_chain(matrix, "Stable", num_steps=5)
    assert len(chain) == 6
    assert chain[0] == "Stable"


def test_markov_main_guard(monkeypatch):
    monkeypatch.setattr("fast_trade.archive.db_helpers.get_kline", lambda **k: pd.DataFrame())
    monkeypatch.setattr("fast_trade.prepare_df", lambda df, backtest: df)
    import runpy

    runpy.run_module("fast_trade.ml.markov", run_name="__main__")


def test_convert_states_to_prices():
    prices = convert_states_to_prices(["Strong Increase", "Stable", "Strong Decrease"], 100.0)
    assert prices[0] == 100.0
    assert prices[1] > 100.0
    assert prices[-1] < prices[1]
