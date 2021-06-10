import pandas as pd
import numpy as np


def check_missing_dates(df):
    """
    Parameters
    ----------
        df, pandas dataframe check

    Returns
    -------
        perc_missing, float, a float of the percentage of missing dates.
        gaps, pandas dataframe, a pandas dataframe of the missing data

    """

    # we want the very end and very begining
    first_date = df.head(1)
    last_date = df.tail(1)

    # This will have 100% of the rows that should exist
    freq = pd.infer_freq(df.index)
    # df = df.dropna()
    print("FREQ: ", freq)
    print(df)
    date_range = pd.date_range(
        first_date.index[0].strftime("%Y-%m-%d %H:%M:%S"),
        last_date.index[0].strftime("%Y-%m-%d %H:%M:%S"),
        freq=pd.infer_freq(df.index),
    )

    # this just makes its easier to work with
    test_df = pd.DataFrame(np.random.randint(1, 20, (date_range.shape[0], 1)))
    test_df.index = date_range

    # this is the missing date ranges
    # gaps = date_range[~date_range.isin(df.index)]

    gaps = pd.DataFrame()

    print("test df len: ", len(date_range))
    print("test test df: ", len(test_df.index))
    # print("gaps!: ", gaps)

    perc_missing = (len(gaps) / len(df.index)) * 100
    perc_missing = round(perc_missing, 2)

    return perc_missing, gaps
