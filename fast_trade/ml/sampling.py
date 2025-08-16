import concurrent.futures
import numpy as np
import pandas as pd
from functools import partial
from typing import List


def generate_path_wrapper(
    ohlcv_df: pd.DataFrame,
    regime_indices: dict,
    transition_matrix: np.ndarray,
    num_regimes: int,
    path_length: int,
    min_chunk_size: int = 10,
    max_chunk_size: int = 100,
) -> pd.DataFrame:
    """
    Wrapper function for generating a single path that can be used with concurrent.futures.
    This function is designed to be picklable for multiprocessing.
    """
    if path_length <= 0:
        return pd.DataFrame()

    # Start with a random chunk
    initial_regime = np.random.choice(list(regime_indices.keys()))
    initial_start_index = np.random.choice(regime_indices[initial_regime])
    initial_chunk_size = np.random.randint(min_chunk_size, max_chunk_size + 1)

    # Ensure the initial chunk doesn't go out of bounds
    initial_start_loc = ohlcv_df.index.get_loc(initial_start_index)
    initial_end_loc = initial_start_loc + initial_chunk_size
    if initial_end_loc > len(ohlcv_df):
        initial_end_loc = len(ohlcv_df)

    synthetic_path = ohlcv_df.iloc[initial_start_loc:initial_end_loc].copy()

    current_regime = synthetic_path["regime"].iloc[-1]

    while len(synthetic_path) < path_length:
        # Determine next regime
        next_regime = np.random.choice(num_regimes, p=transition_matrix[current_regime])

        # Select a random chunk from the chosen regime
        if not regime_indices[next_regime].empty:
            start_index = np.random.choice(regime_indices[next_regime])
            chunk_size = np.random.randint(min_chunk_size, max_chunk_size + 1)

            start_loc = ohlcv_df.index.get_loc(start_index)
            end_loc = start_loc + chunk_size
            if end_loc > len(ohlcv_df):
                end_loc = len(ohlcv_df)

            if start_loc == end_loc:
                current_regime = next_regime
                continue

            new_chunk = ohlcv_df.iloc[start_loc:end_loc].copy()

            # Stitch chunks together
            last_close = synthetic_path["close"].iloc[-1]
            first_open = new_chunk["open"].iloc[0]
            price_adjustment = last_close - first_open

            for col in ["open", "high", "low", "close"]:
                new_chunk[col] += price_adjustment

            synthetic_path = pd.concat([synthetic_path, new_chunk])
            current_regime = new_chunk["regime"].iloc[-1]
        else:
            # Handle empty regime by transitioning again
            current_regime = next_regime

    return synthetic_path.iloc[:path_length].drop(columns=["regime"])


class RegimeAwareBootstrapper:
    """
    Generates new price paths by stitching together actual segments of historical
    OHLCV data, guided by market regimes.
    """

    def __init__(
        self,
        ohlcv_df: pd.DataFrame,
        volatility_window: int = 20,
        num_regimes: int = 3,
    ):
        if not isinstance(ohlcv_df, pd.DataFrame) or not all(
            col in ohlcv_df.columns
            for col in ["open", "high", "low", "close", "volume"]
        ):
            raise ValueError("ohlcv_df must be a DataFrame with OHLCV columns")

        self.ohlcv_df = ohlcv_df.copy()
        self.volatility_window = volatility_window
        self.num_regimes = num_regimes

        self._identify_regimes()
        self._calculate_regime_transitions()

    def _identify_regimes(self):
        """
        Identifies market regimes based on rolling volatility.
        """
        returns = self.ohlcv_df["close"].pct_change().dropna()
        rolling_vol = returns.rolling(window=self.volatility_window).std().dropna()

        # Align rolling_vol with the original dataframe
        self.ohlcv_df["regime"] = pd.qcut(
            rolling_vol, self.num_regimes, labels=False, duplicates="drop"
        )
        self.ohlcv_df.dropna(subset=["regime"], inplace=True)
        self.ohlcv_df["regime"] = self.ohlcv_df["regime"].astype(int)

        self.regime_indices = {
            regime: self.ohlcv_df.index[self.ohlcv_df["regime"] == regime]
            for regime in range(self.num_regimes)
        }

    def _calculate_regime_transitions(self):
        """
        Calculates the historical transition probabilities between regimes.
        """
        regimes = self.ohlcv_df["regime"]
        transitions = pd.crosstab(regimes, regimes.shift(-1), normalize="index")
        self.transition_matrix = transitions.reindex(
            range(self.num_regimes),
            columns=range(self.num_regimes),
            fill_value=0,
        ).values

    def generate_path(
        self,
        path_length: int,
        min_chunk_size: int = 10,
        max_chunk_size: int = 100,
    ) -> pd.DataFrame:
        """
        Generates a single synthetic OHLCV path.
        """
        if path_length <= 0:
            return pd.DataFrame()

        # Start with a random chunk
        initial_regime = np.random.choice(list(self.regime_indices.keys()))
        initial_start_index = np.random.choice(self.regime_indices[initial_regime])
        initial_chunk_size = np.random.randint(min_chunk_size, max_chunk_size + 1)

        # Ensure the initial chunk doesn't go out of bounds
        initial_start_loc = self.ohlcv_df.index.get_loc(initial_start_index)
        initial_end_loc = initial_start_loc + initial_chunk_size
        if initial_end_loc > len(self.ohlcv_df):
            initial_end_loc = len(self.ohlcv_df)

        synthetic_path = self.ohlcv_df.iloc[initial_start_loc:initial_end_loc].copy()

        current_regime = synthetic_path["regime"].iloc[-1]

        while len(synthetic_path) < path_length:
            # Determine next regime
            next_regime = np.random.choice(
                self.num_regimes, p=self.transition_matrix[current_regime]
            )

            # Select a random chunk from the chosen regime
            if not self.regime_indices[next_regime].empty:
                start_index = np.random.choice(self.regime_indices[next_regime])
                chunk_size = np.random.randint(min_chunk_size, max_chunk_size + 1)

                start_loc = self.ohlcv_df.index.get_loc(start_index)
                end_loc = start_loc + chunk_size
                if end_loc > len(self.ohlcv_df):
                    end_loc = len(self.ohlcv_df)

                if start_loc == end_loc:
                    current_regime = next_regime
                    continue

                new_chunk = self.ohlcv_df.iloc[start_loc:end_loc].copy()

                # Stitch chunks together
                last_close = synthetic_path["close"].iloc[-1]
                first_open = new_chunk["open"].iloc[0]
                price_adjustment = last_close - first_open

                for col in ["open", "high", "low", "close"]:
                    new_chunk[col] += price_adjustment

                synthetic_path = pd.concat([synthetic_path, new_chunk])
                current_regime = new_chunk["regime"].iloc[-1]
            else:
                # Handle empty regime by transitioning again
                current_regime = next_regime

        return synthetic_path.iloc[:path_length].drop(columns=["regime"])

    def generate_many_paths(
        self,
        num_paths: int,
        path_length: int,
        min_chunk_size: int = 10,
        max_chunk_size: int = 100,
        use_parallel: bool = True,
        parallel_processing: int = 4,
    ) -> List[pd.DataFrame]:
        """
        Generates multiple synthetic OHLCV paths using parallel processing.

        Args:
            num_paths: Number of paths to generate
            path_length: Length of each path
            min_chunk_size: Minimum size of chunks to stitch together
            max_chunk_size: Maximum size of chunks to stitch together
            use_parallel: Whether to use parallel processing
            parallel_processing: Number of parallel workers to use
        """
        if use_parallel and parallel_processing > 1:
            # Use parallel processing
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=parallel_processing
            ) as executor:
                # Create partial function with fixed arguments
                path_generator = partial(
                    generate_path_wrapper,
                    ohlcv_df=self.ohlcv_df,
                    regime_indices=self.regime_indices,
                    transition_matrix=self.transition_matrix,
                    num_regimes=self.num_regimes,
                    path_length=path_length,
                    min_chunk_size=min_chunk_size,
                    max_chunk_size=max_chunk_size,
                )

                # Generate paths in parallel
                paths = list(executor.map(path_generator, [None] * num_paths))
                return paths
        else:
            # Sequential processing (original implementation)
            return [
                self.generate_path(path_length, min_chunk_size, max_chunk_size)
                for _ in range(num_paths)
            ]
