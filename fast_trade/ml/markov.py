import pandas as pd
import numpy as np
from hmmlearn import hmm


def create_hmm(kline_df: pd.DataFrame):
    """Create a Hidden Markov Model (HMM) from a strategy

    Args:
        strategy (dict): A dictionary containing the strategy parameters
    """
    # Get the historical data
    
    # Calculate percentage change as observations
    kline_df['pct_change'] = kline_df['close'].pct_change().fillna(0) * 100
    observations = kline_df['pct_change'].values.reshape(-1, 1)

    # Define the HMM model
    model = hmm.GaussianHMM(n_components=3, covariance_type="full", n_iter=100)

    # Fit the model
    model.fit(observations)

    # Predict hidden states
    hidden_states = model.predict(observations)
    kline_df['hidden_state'] = hidden_states
    # print("Hidden States:\n", hidden_states)

    # Predict future states
    future_states_seq, _ = model.sample(24)
    # print("Predicted Future States:\n", future_states)
    
    # Create a separate DataFrame for future predictions
    last_date = kline_df.index[-1]
    future_dates = pd.date_range(start=last_date, periods=25)[1:]  # Exclude the last known date
    
    future_df = pd.DataFrame({
        'future_state': future_states_seq.flatten(),
        'date': future_dates
    })
    future_df.set_index('date', inplace=True)
    
    # Create future price predictions based on the last closing price
    last_price = kline_df['close'].iloc[-1]
    means = model.means_.flatten()
    
    # Convert states to integers and use them as indices
    future_states_int = future_states_seq.flatten().astype(int)
    future_df['predicted_pct_change'] = [means[state] for state in future_states_int]
    
    # Calculate predicted prices
    future_df['predicted_price'] = last_price
    for i in range(len(future_df)):
        if i == 0:
            # Calculate first predicted price based on last known price
            pct_change = future_df['predicted_pct_change'].iloc[i]
            future_df.loc[future_df.index[i], 'predicted_price'] = last_price * (1 + pct_change/100)
        else:
            # Calculate subsequent prices based on previous prediction
            pct_change = future_df['predicted_pct_change'].iloc[i]
            prev_price = future_df['predicted_price'].iloc[i-1]
            future_df.loc[future_df.index[i], 'predicted_price'] = prev_price * (1 + pct_change/100)

    # add the future_df to the kline_df
    kline_df = pd.concat([kline_df, future_df], axis=1)
    return kline_df


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
    # Create test data for the HMM
    from fast_trade.archive.db_helpers import get_kline
    from fast_trade import prepare_df
    import time
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
    start = time.time()
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
