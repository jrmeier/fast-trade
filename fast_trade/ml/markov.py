import datetime

import numpy as np
import polars as pl
from hmmlearn import hmm


STATES = [
    "Strong Increase",
    "Moderate Increase",
    "Slight Increase",
    "Stable",
    "Slight Decrease",
    "Moderate Decrease",
    "Strong Decrease",
]


def create_hmm(kline_df: pl.DataFrame) -> pl.DataFrame:
    """Create a Hidden Markov Model (HMM) from a strategy

    Args:
        strategy (dict): A dictionary containing the strategy parameters
    """
    # Calculate percentage change as observations
    kline_df = kline_df.with_columns(
        (pl.col("close").pct_change().fill_null(0.0) * 100).alias("pct_change")
    )
    observations = kline_df["pct_change"].to_numpy().reshape(-1, 1)

    # Define the HMM model
    model = hmm.GaussianHMM(n_components=3, covariance_type="full", n_iter=100)

    # Fit the model
    model.fit(observations)

    # Predict hidden states
    hidden_states = model.predict(observations)
    kline_df = kline_df.with_columns(pl.Series("hidden_state", hidden_states))

    # Predict future states
    future_states_seq, _ = model.sample(24)
    future_states_int = future_states_seq.flatten().astype(int)
    last_date = kline_df["date"][-1]
    future_dates = [last_date + datetime.timedelta(days=step) for step in range(1, 25)]

    # Create future price predictions based on the last closing price
    last_price = float(kline_df["close"][-1])
    means = model.means_.flatten()
    predicted_changes = means[future_states_int]
    predicted_prices = last_price * np.cumprod(1.0 + predicted_changes / 100.0)
    future_df = pl.DataFrame(
        {
            "date": future_dates,
            "future_state": future_states_int,
            "predicted_pct_change": predicted_changes,
            "predicted_price": predicted_prices,
        },
        schema_overrides={"date": kline_df.schema["date"]},
    )
    return pl.concat([kline_df, future_df], how="diagonal_relaxed")


def define_granular_states(kline_df: pl.DataFrame) -> pl.DataFrame:
    # Calculate percentage change
    pct = pl.col("close").pct_change() * 100
    return kline_df.with_columns(pct.alias("pct_change")).with_columns(
        pl.when(pl.col("pct_change") > 2)
        .then(pl.lit("Strong Increase"))
        .when((pl.col("pct_change") > 1) & (pl.col("pct_change") <= 2))
        .then(pl.lit("Moderate Increase"))
        .when((pl.col("pct_change") > 0) & (pl.col("pct_change") <= 1))
        .then(pl.lit("Slight Increase"))
        .when((pl.col("pct_change") > -0.5) & (pl.col("pct_change") <= 0.5))
        .then(pl.lit("Stable"))
        .when((pl.col("pct_change") > -1) & (pl.col("pct_change") <= -0.5))
        .then(pl.lit("Slight Decrease"))
        .when((pl.col("pct_change") > -2) & (pl.col("pct_change") <= -1))
        .then(pl.lit("Moderate Decrease"))
        .when(pl.col("pct_change") <= -2)
        .then(pl.lit("Strong Decrease"))
        .otherwise(pl.lit("Stable"))
        .alias("state")
    )


def calculate_transition_matrix(kline_df: pl.DataFrame) -> pl.DataFrame:
    # Calculate transition probabilities
    state_index = {state: index for index, state in enumerate(STATES)}
    counts = np.zeros((len(STATES), len(STATES)), dtype=float)
    values = kline_df["state"].to_list()
    for previous, current in zip(values, values[1:]):
        counts[state_index[previous], state_index[current]] += 1
    totals = counts.sum(axis=1)
    for index, total in enumerate(totals):
        if total:
            counts[index] /= total
        else:
            counts[index, index] = 1.0
    return pl.DataFrame({state: counts[:, index] for index, state in enumerate(STATES)})


def simulate_markov_chain(transition_matrix: pl.DataFrame, initial_state, num_steps):
    states = transition_matrix.columns
    current_state = initial_state
    chain = [current_state]

    for _ in range(num_steps):
        probabilities = np.asarray(transition_matrix.row(states.index(current_state)), dtype=float)
        current_state = np.random.choice(states, p=probabilities)
        chain.append(current_state)

    return chain


def convert_states_to_prices(states, last_price):
    # Define typical price changes for each state
    price_changes = {
        'Strong Increase': 0.03,  # 3% increase
        'Moderate Increase': 0.02,  # 2% increase
        'Slight Increase': 0.01,  # 1% increase
        'Stable': 0.0,  # No change
        'Slight Decrease': -0.01,  # 1% decrease
        'Moderate Decrease': -0.02,  # 2% decrease
        'Strong Decrease': -0.03  # 3% decrease
    }

    prices = [last_price]
    for state in states:
        last_price *= (1 + price_changes[state])
        prices.append(last_price)

    return prices


if __name__ == "__main__":
    # Create test data for the HMM
    from fast_trade.archive.db_helpers import get_kline
    from fast_trade import prepare_df
    strat_config = {
        "symbol": "BTC-USDT",
        "exchange": "coinbase",
        "freq": "1h",
        "start": "2024-02-01",
        "stop": "2025-03-01",
        "datapoints": [
            {
                "name": "rsi",
                "transformer": "rsi",
                "args": [14]
            },
            {
                "name": "zlema",
                "transformer": "zlema",
                "args": [400]
            },
            {
                "name": "roc",
                "transformer": "roc",
                "args": [50]
            }
        ]
    }
    
    # Get the data
    kline_data = get_kline(
        symbol=strat_config["symbol"],
        exchange=strat_config["exchange"],
        freq=strat_config["freq"],
        start_date=strat_config["start"],
        end_date=strat_config["stop"]
    )
    kline_data = prepare_df(kline_data, backtest=strat_config)
    print(kline_data)
    # # Create a simple Strategy object with a data attribute
    # kline_df = create_hmm(kline_data)
    # end = time.time()
    # print(f"Time taken: {end - start} seconds")

    # # print("Future States:\n", kline_df['future_state'])
    # print(kline_df)
