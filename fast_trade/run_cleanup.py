def run_cleanup(df):
    # print(df.columns)

    # add perc change for each trade

    # perc_change = df['smooth_base'].pct_change()

    # print(perc_change)

    # df = analyze_df(df, commission, starting_aux_bal, exit_on_end)

    # if len(base) != len(df.index) and strategy.get("exit_on_end", True):
    #     new_row = pd.DataFrame(
    #         df[-1:].values,
    #         index=[df.index[-1] + pd.Timedelta(minutes=1)],
    #         columns=df.columns,
    #     )
    #     df = df.append(new_row)


    df['perc_change'] = df['smooth_base'].pct_change()
    return df
