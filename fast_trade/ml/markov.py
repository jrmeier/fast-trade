import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from hmmlearn import hmm

from fast_trade import prepare_df
from fast_trade.archive.db_helpers import get_kline


@dataclass
class StateConfig:
    name: str
    min_change: float
    max_change: float
    price_multiplier: float
    volume_threshold: float = 1.0  # Volume multiplier relative to average
    rsi_range: Tuple[float, float] = (0, 100)  # RSI range for this state
    volatility_threshold: float = 0.0  # Minimum volatility required

    def __post_init__(self):
        if self.min_change >= self.max_change:
            raise ValueError("min_change must be less than max_change")


class MarkovChain:
    def __init__(
        self,
        states: List[StateConfig],
        initial_state: Optional[str] = None,
        random_seed: Optional[int] = None,
        confidence_interval: float = 0.95,
    ):
        self.states = {state.name: state for state in states}
        self.state_names = [state.name for state in states]
        self.initial_state = initial_state or states[0].name
        self.transition_matrix = None
        self.random_state = np.random.RandomState(random_seed)
        self.confidence_interval = confidence_interval
        self.volatility = None
        self.volume_mean = None

    def calculate_volatility(self, kline_df: pd.DataFrame) -> pd.Series:
        """Calculate rolling volatility"""
        returns = kline_df["close"].pct_change()
        return returns.rolling(window=24).std() * np.sqrt(24)

    def calculate_volume_profile(self, kline_df: pd.DataFrame) -> pd.Series:
        """Calculate volume profile relative to average"""
        return kline_df["volume"] / kline_df["volume"].rolling(window=24).mean()

    def fit(self, kline_df: pd.DataFrame) -> None:
        """Fit the Markov chain to historical data"""
        if not isinstance(kline_df, pd.DataFrame):
            raise ValueError("kline_df must be a pandas DataFrame")

        # Calculate basic metrics
        kline_df["pct_change"] = kline_df["close"].pct_change() * 100
        kline_df["volatility"] = self.calculate_volatility(kline_df)
        kline_df["volume_profile"] = self.calculate_volume_profile(kline_df)

        # Store global metrics and scalers
        self.volatility = kline_df["volatility"].mean()
        self.volume_mean = kline_df["volume"].mean()

        # Calculate price changes and their statistics
        self.price_changes = kline_df["close"].pct_change()
        self.price_mean = self.price_changes.mean()
        self.price_std = self.price_changes.std()

        # Store technical indicators for state determination
        self.indicators = {}
        if "rsi" in kline_df.columns:
            self.indicators["rsi"] = kline_df["rsi"]
        if "zlema" in kline_df.columns:
            self.indicators["zlema"] = kline_df["zlema"]
        if "roc" in kline_df.columns:
            self.indicators["roc"] = kline_df["roc"]
        if "macd" in kline_df.columns:
            self.indicators["macd"] = kline_df["macd"]
            self.indicators["macd_signal"] = kline_df["macd_signal"]
            self.indicators["macd_hist"] = kline_df["macd_hist"]

        # Assign states based on multiple criteria including all indicators
        conditions = []
        choices = []
        for state in self.states.values():
            state_condition = (
                (kline_df["pct_change"] > state.min_change)
                & (kline_df["pct_change"] <= state.max_change)
                & (kline_df["volume_profile"] >= state.volume_threshold)
                & (kline_df["volatility"] >= state.volatility_threshold)
            )

            # Add technical indicator conditions
            if "rsi" in self.indicators:
                state_condition &= (self.indicators["rsi"] >= state.rsi_range[0]) & (
                    self.indicators["rsi"] <= state.rsi_range[1]
                )

            if "zlema" in self.indicators:
                # ZLEMA trend condition
                zlema_trend = self.indicators["zlema"].diff() > 0
                if state.name in [
                    "Strong Increase",
                    "Moderate Increase",
                    "Slight Increase",
                ]:
                    state_condition &= zlema_trend
                elif state.name in [
                    "Strong Decrease",
                    "Moderate Decrease",
                    "Slight Decrease",
                ]:
                    state_condition &= ~zlema_trend

            if "roc" in self.indicators:
                # Rate of Change condition
                if state.name in ["Strong Increase", "Moderate Increase"]:
                    state_condition &= self.indicators["roc"] > 0
                elif state.name in ["Strong Decrease", "Moderate Decrease"]:
                    state_condition &= self.indicators["roc"] < 0

            if "macd" in self.indicators:
                # MACD conditions
                if state.name in ["Strong Increase", "Moderate Increase"]:
                    state_condition &= (
                        self.indicators["macd"] > self.indicators["macd_signal"]
                    ) & (self.indicators["macd_hist"] > 0)
                elif state.name in ["Strong Decrease", "Moderate Decrease"]:
                    state_condition &= (
                        self.indicators["macd"] < self.indicators["macd_signal"]
                    ) & (self.indicators["macd_hist"] < 0)

            conditions.append(state_condition)
            choices.append(state.name)

        kline_df["state"] = np.select(conditions, choices, default=self.initial_state)

        # Calculate transition matrix with confidence
        self.transition_matrix = pd.DataFrame(
            0, index=self.state_names, columns=self.state_names
        )
        self.transition_counts = pd.DataFrame(
            0, index=self.state_names, columns=self.state_names
        )

        for i in range(1, len(kline_df)):
            prev_state = kline_df.iloc[i - 1]["state"]
            current_state = kline_df.iloc[i]["state"]
            self.transition_matrix.loc[prev_state, current_state] += 1
            self.transition_counts.loc[prev_state, current_state] += 1

        # Normalize to get probabilities
        self.transition_matrix = self.transition_matrix.div(
            self.transition_matrix.sum(axis=1), axis=0
        )

    def simulate(
        self, num_steps: int, num_simulations: int = 10000
    ) -> Tuple[List[str], List[List[str]]]:
        """Simulate the Markov chain with confidence intervals"""
        if self.transition_matrix is None:
            raise ValueError("Model must be fit before simulation")

        # Generate multiple simulations with Monte Carlo
        all_simulations = []
        simulation_weights = []  # Track likelihood of each simulation

        for _ in range(num_simulations):
            current_state = self.initial_state
            chain = [current_state]
            log_likelihood = 0.0

            for _ in range(num_steps):
                # Get transition probabilities
                probs = self.transition_matrix.loc[current_state]

                # Add noise to probabilities based on indicator agreement
                noise = self.random_state.normal(0, 0.1, size=len(probs))
                noisy_probs = probs * (1 + noise)
                noisy_probs = noisy_probs / noisy_probs.sum()  # Normalize

                # Choose next state
                next_state = self.random_state.choice(self.state_names, p=noisy_probs)

                # Update likelihood
                log_likelihood += np.log(noisy_probs[next_state])

                chain.append(next_state)
                current_state = next_state

            all_simulations.append(chain)
            simulation_weights.append(np.exp(log_likelihood))

        # Normalize weights
        simulation_weights = np.array(simulation_weights)
        simulation_weights = simulation_weights / simulation_weights.sum()

        # Calculate most likely path using weighted average
        most_likely_path = []
        current_state = self.initial_state
        most_likely_path.append(current_state)

        for step in range(num_steps):
            # Get all possible next states and their weights
            next_states = [sim[step + 1] for sim in all_simulations]
            state_weights = {}

            for state, weight in zip(next_states, simulation_weights):
                state_weights[state] = state_weights.get(state, 0) + weight

            # Choose state with highest weight
            next_state = max(state_weights.items(), key=lambda x: x[1])[0]
            most_likely_path.append(next_state)
            current_state = next_state

        return most_likely_path, all_simulations

    def predict_prices(
        self, states: List[str], last_price: float, include_confidence: bool = True
    ) -> Tuple[List[float], Optional[List[Tuple[float, float]]]]:
        """Convert state sequence to price predictions with confidence intervals"""
        prices = [last_price]
        confidence_intervals = [] if include_confidence else None

        # Monte Carlo price simulation
        num_simulations = 1000
        price_simulations = np.zeros((num_simulations, len(states)))
        price_simulations[:, 0] = last_price

        # Skip the first state since it's the initial state
        for i, state in enumerate(states[1:], 1):
            # Get base multiplier for the state
            base_multiplier = self.states[state].price_multiplier

            # Generate multiple price changes
            price_changes = self.random_state.normal(
                self.price_mean, self.price_std, size=num_simulations
            )

            # Apply state-specific scaling
            scaled_changes = price_changes * (base_multiplier - 1)

            # Apply dynamic influence from all indicators
            for indicator_name, indicator_data in self.indicators.items():
                # Get the latest indicator value
                latest_value = indicator_data.iloc[-1]

                # Calculate influence based on indicator type
                if indicator_name == "rsi":
                    influence = (latest_value - 50) / 100  # Normalize RSI influence
                else:
                    # For other indicators, use their relative change
                    influence = indicator_data.pct_change().iloc[-1]

                # Add random noise to influence
                noise = self.random_state.normal(0, 0.1, size=num_simulations)
                scaled_changes *= 1 + influence + noise

            # Calculate new prices
            price_simulations[:, i] = price_simulations[:, i - 1] * (1 + scaled_changes)

        # Calculate mean and confidence intervals
        mean_prices = np.mean(price_simulations, axis=0)
        prices = mean_prices.tolist()

        if include_confidence:
            # Calculate confidence intervals using percentiles
            lower_bound = np.percentile(price_simulations, 2.5, axis=0)
            upper_bound = np.percentile(price_simulations, 97.5, axis=0)
            confidence_intervals = list(zip(lower_bound[1:], upper_bound[1:]))

        return prices, confidence_intervals


def create_hmm(strategy: dict) -> Tuple[np.ndarray, np.ndarray]:
    """Create a Hidden Markov Model (HMM) from a strategy"""
    kline_df = get_kline(
        symbol=strategy["symbol"],
        exchange=strategy["exchange"],
        freq=strategy["freq"],
        start_date=strategy["start_date"],
        end_date=strategy["end_date"],
    )
    kline_df = prepare_df(kline_df, backtest=strategy)

    # Calculate percentage change as observations
    kline_df["pct_change"] = kline_df["close"].pct_change().fillna(0) * 100
    observations = kline_df["pct_change"].values.reshape(-1, 1)

    # Define and fit the HMM model
    model = hmm.GaussianHMM(n_components=3, covariance_type="full", n_iter=100)
    model.fit(observations)

    # Predict states and future samples
    hidden_states = model.predict(observations)
    future_states = model.sample(24)[0]

    return hidden_states, future_states


def run_markov(strategy: dict) -> None:
    """Run the Markov chain with a given strategy"""

    # \


if __name__ == "__main__":
    # Example usage with more realistic states
    states = [
        StateConfig(
            "Strong Increase",
            1.0,
            float("inf"),
            1.005,  # 0.5% increase
            volume_threshold=1.5,
            rsi_range=(70, 100),
            volatility_threshold=0.02,
        ),
        StateConfig(
            "Moderate Increase",
            0.5,
            1.0,
            1.002,  # 0.2% increase
            volume_threshold=1.2,
            rsi_range=(60, 70),
            volatility_threshold=0.01,
        ),
        StateConfig(
            "Slight Increase",
            0.0,
            0.5,
            1.001,  # 0.1% increase
            volume_threshold=1.0,
            rsi_range=(50, 60),
            volatility_threshold=0.005,
        ),
        StateConfig(
            "Stable",
            -0.25,
            0.25,
            1.0,  # No change
            volume_threshold=0.8,
            rsi_range=(40, 60),
            volatility_threshold=0.001,
        ),
        StateConfig(
            "Slight Decrease",
            -0.5,
            -0.25,
            0.999,  # 0.1% decrease
            volume_threshold=1.0,
            rsi_range=(30, 40),
            volatility_threshold=0.005,
        ),
        StateConfig(
            "Moderate Decrease",
            -1.0,
            -0.5,
            0.998,  # 0.2% decrease
            volume_threshold=1.2,
            rsi_range=(20, 30),
            volatility_threshold=0.01,
        ),
        StateConfig(
            "Strong Decrease",
            float("-inf"),
            -1.0,
            0.995,  # 0.5% decrease
            volume_threshold=1.5,
            rsi_range=(0, 20),
            volatility_threshold=0.02,
        ),
    ]

    # Create and fit Markov chain
    chain = MarkovChain(states, random_seed=42, confidence_interval=0.95)

    # Example strategy with current data
    strat = {
        "symbol": "BTCUSDT",
        "exchange": "binanceus",
        "freq": "15Min",
        "start_date": "2025-01-01",
        "end_date": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "datapoints": [
            {"name": "rsi", "transformer": "rsi", "args": [14]},
            {"name": "bbands", "transformer": "bbands", "args": [20, 2]},
            {"name": "zlema", "transformer": "zlema", "args": [24]},
            {"name": "roc", "transformer": "roc", "args": [50]},
            {"name": "macd", "transformer": "macd", "args": [12, 26, 9]},
        ],
    }

    # Get historical data
    kline_df = get_kline(
        symbol=strat["symbol"],
        exchange=strat["exchange"],
        freq=strat["freq"],
        start_date=strat["start_date"],
        end_date=strat["end_date"],
    )
    kline_df = prepare_df(kline_df, backtest=strat)

    # Fit the chain
    chain.fit(kline_df)

    # Simulate future states with confidence intervals
    most_likely_path, all_simulations = chain.simulate(24, num_simulations=10000)

    # Predict prices with confidence intervals
    last_price = kline_df["close"].iloc[-1]
    predicted_prices, confidence_intervals = chain.predict_prices(
        most_likely_path, last_price, include_confidence=True
    )

    # Create date interval for the predicted prices
    date_interval = pd.date_range(
        start=kline_df.index[-1],
        periods=len(predicted_prices),  # Match the length of predicted prices
        freq=strat["freq"],
    )

    # Create DataFrame with predictions and confidence intervals
    predicted_prices_df = pd.DataFrame(
        {
            "predicted_price": predicted_prices,
            "lower_bound": (
                [None] + [ci[0] for ci in confidence_intervals]
                if confidence_intervals
                else None
            ),
            "upper_bound": (
                [None] + [ci[1] for ci in confidence_intervals]
                if confidence_intervals
                else None
            ),
        },
        index=date_interval,
    )

    print("\nLast known price:", last_price)
    print("\nPredicted prices with 95% confidence intervals:")
    print(predicted_prices_df)
