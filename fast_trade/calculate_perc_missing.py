def calculate_perc_missing(df):
    """
    Parameters
    ----------
        df, pandas dataframe check

    Returns
    -------
        perc_missing, float, a float of the percentage of rows with the missing closing price

    """

    total_missing = df.close.isna().sum()

    perc_missing = 0.0
    if total_missing:
        total_tics = len(df.index)
        perc_missing = (total_missing / total_tics) * 100

        perc_missing = round(perc_missing, 2)

    return perc_missing, total_missing
