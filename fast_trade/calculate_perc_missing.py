import pandas as pd


def calculate_perc_missing(df):
    """
    Calculate the percentage and total count of missing entries
    in a DataFrame based on a time-index.

    Parameters:
    - df (pd.DataFrame): The input DataFrame with a DatetimeIndex.

    Returns:
    - list: [percentage_missing (float), total_missing (float)]
    """
    # Handle empty DataFrame
    if df.empty:
        raise ValueError("DataFrame is empty")

    # Get the original frequency and reindex with it
    # check if the index is a DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index is not a DatetimeIndex")
    freq = df.index.freq
    if freq is None:
        freq = "1Min"
    # Get the full range of expected dates
    start = df.index.min()
    end = df.index.max()
    expected_index = pd.date_range(start=start, end=end, freq=freq)

    # Calculate missing values
    total_possible = len(expected_index)
    total_actual = len(df)

    total_missing = total_possible - total_actual

    # Calculate percentage
    perc_missing = (total_missing / total_possible) * 100 if total_possible > 0 else 0.0
    perc_missing = round(perc_missing, 2)
    return [perc_missing, 0 if total_missing < 0 else total_missing]
