from fast_trade.archive.db_helpers import get_kline
from fast_trade import prepare_df
import pandas as pd
import numpy as np
from hmmlearn import hmm


def create_hmm(strategy):
    """Create a Hidden Markov Model (HMM) from a strategy

    Args:
        strategy (dict): A dictionary containing the strategy parameters
    """
    # Get the klines
    kline_df = get_kline(
        symbol=strategy["symbol"],
        exchange=strategy["exchange"],
        freq=strategy["freq"],
        start_date=strategy["start_date"],
        end_date=strategy["end_date"]
    )
    kline_df = prepare_df(kline_df, backtest=strategy)
    print(kline_df)

    # Calculate percentage change as observations
    kline_df['pct_change'] = kline_df['close'].pct_change().fillna(0) * 100
    observations = kline_df['pct_change'].values.reshape(-1, 1)

    # Define the HMM model
    model = hmm.GaussianHMM(n_components=3, covariance_type="full", n_iter=100)

    # Fit the model
    model.fit(observations)

    # Predict hidden states
    hidden_states = model.predict(observations)
    print("Hidden States:\n", hidden_states)

    # Predict future states
    future_states = model.sample(24)[0]
    print("Predicted Future States:\n", future_states)

    return hidden_states, future_states


def define_granular_states(kline_df):
    # Calculate percentage change
    kline_df['pct_change'] = kline_df['close'].pct_change() * 100

    # Define states based on percentage change
    conditions = [
        (kline_df['pct_change'] > 2),
        (kline_df['pct_change'] > 1) & (kline_df['pct_change'] <= 2),
        (kline_df['pct_change'] > 0) & (kline_df['pct_change'] <= 1),
        (kline_df['pct_change'] > -0.5) & (kline_df['pct_change'] <= 0.5),
        (kline_df['pct_change'] > -1) & (kline_df['pct_change'] <= -0.5),
        (kline_df['pct_change'] > -2) & (kline_df['pct_change'] <= -1),
        (kline_df['pct_change'] <= -2)
    ]
    choices = [
        'Strong Increase', 'Moderate Increase', 'Slight Increase',
        'Stable', 'Slight Decrease', 'Moderate Decrease', 'Strong Decrease'
    ]
    kline_df['state'] = np.select(conditions, choices, default='Stable')
    return kline_df


def calculate_transition_matrix(kline_df):
    # Calculate transition probabilities
    states = ['Strong Increase', 'Moderate Increase', 'Slight Increase',
              'Stable', 'Slight Decrease', 'Moderate Decrease', 'Strong Decrease']
    transition_matrix = pd.DataFrame(0, index=states, columns=states)

    for i in range(1, len(kline_df)):
        prev_state = kline_df.iloc[i-1]['state']
        current_state = kline_df.iloc[i]['state']
        transition_matrix.loc[prev_state, current_state] += 1

    # Normalize to get probabilities
    transition_matrix = transition_matrix.div(transition_matrix.sum(axis=1), axis=0)
    return transition_matrix


def simulate_markov_chain(transition_matrix, initial_state, num_steps):
    states = transition_matrix.columns
    current_state = initial_state
    chain = [current_state]

    for _ in range(num_steps):
        current_state = np.random.choice(states, p=transition_matrix.loc[current_state])
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
    strat = {
        "symbol": "ETHUSDT",
        "exchange": "binanceus",
        "freq": "1Min",
        "start_date": "2024-01-01",
        "end_date": "2025-03-01",
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
    hidden_states, future_states = create_hmm(strat)

    print("Future States:\n", future_states)