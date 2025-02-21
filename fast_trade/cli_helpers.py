# flake8: noqa
import datetime
import json
import os
import re

import matplotlib.pyplot as plt
import pandas as pd
import requests

from fast_trade.archive.db_helpers import connect_to_db

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "ft_archive")


class MissingStrategyFile(Exception):
    pass


def open_strat_file(fp):
    reg = r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"

    is_url = re.search(reg, fp)
    if is_url:
        # url
        req = requests.get(fp)
        if req.status_code in [200, 201, 202, 301]:
            return req.json()
        else:
            raise MissingStrategyFile(
                "Could not open strategy file at url: {}".format(fp)
            )

    strat_obj = {}
    try:
        with open(fp, "r") as json_file:
            strat_obj = json.load(json_file)
            return strat_obj

    except FileNotFoundError:
        raise MissingStrategyFile("Could not open strategy file at path: {}".format(fp))


def create_plot(df, trade_df):
    # Filter for numeric columns only
    numeric_df = df.select_dtypes(include=["number"])

    numeric_df = numeric_df.drop(
        columns=[
            "open",
            "high",
            "low",
            "adj_account_value",
            "account_value",
            "aux",
            "fee",
            "adj_account_value_change_perc",
            "adj_account_value_change",
        ]
    )

    # Calculate the range of each column
    ranges = numeric_df.max() - numeric_df.min()

    # Define a threshold for grouping columns with similar ranges
    close_range = ranges["close"]
    threshold = close_range * 0.1  # Adjust this factor as needed

    # Group columns based on their range
    close_group = [
        col for col in numeric_df.columns if abs(ranges[col] - close_range) < threshold
    ]
    separate_group = [col for col in numeric_df.columns if col not in close_group]

    # Create subplots
    num_plots = 1 + len(
        separate_group
    )  # One plot for the close group, others for separate columns
    fig, axs = plt.subplots(num_plots, 1, figsize=(10, 6 * num_plots), sharex=True)

    # Ensure axs is iterable
    if num_plots == 1:
        axs = [axs]

    # Plot the close group together
    for column in close_group:
        numeric_df.plot(y=column, ax=axs[0], legend=True, label=column)

    # Iterate over the trade DataFrame and plot each point with the appropriate color
    for index, row in trade_df.iterrows():
        color = "green" if row["in_trade"] else "red"
        for column in close_group:
            axs[0].scatter(index, row[column], color=color, s=10, alpha=0.7)

    axs[0].set_title("Close Group Over Time")
    axs[0].set_ylabel("Value")
    axs[0].grid(True, linestyle="--", alpha=0.5)

    # Plot each separate column in its own subplot
    for ax, column in zip(axs[1:], separate_group):
        numeric_df.plot(y=column, ax=ax, legend=False, label=column)

        for index, row in trade_df.iterrows():
            color = "green" if row["in_trade"] else "red"
            ax.scatter(index, row[column], color=color, s=10, alpha=0.7)

        ax.set_title(f"{column} Over Time")
        ax.set_ylabel(column)
        ax.grid(True, linestyle="--", alpha=0.5)

    # Set the x-axis label for the last subplot
    axs[-1].set_xlabel("Date")

    # Adjust layout
    plt.tight_layout()
    plt.show()
    return fig


def save(result):
    """
    Save the dataframe, backtest, and plot into the specified path
    """

    save_path = ARCHIVE_PATH
    if not os.path.exists(save_path):
        os.mkdir(save_path)
    if not os.path.exists(f"{save_path}/backtests"):
        os.mkdir(f"{save_path}/backtests")
    # dir exists, now make a new dir with the files
    new_dir = (
        f"{datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H_%M_%S')}"
    )

    new_save_dir = f"{save_path}/backtests/{new_dir}"

    os.mkdir(new_save_dir)

    # save the backtest args
    # summary file
    with open(f"{new_save_dir}/summary.json", "w") as summary_file:
        summary_file.write(json.dumps(result["summary"], indent=2))

    # dataframe
    # result["df"].to_csv(f"{new_save_dir}/dataframe.csv")
    # result["trade_df"].to_csv(f"{new_save_dir}/trade_dataframe.csv")
    df_con = connect_to_db(f"{new_save_dir}/dataframe.db", create=True)
    result["df"].to_sql(
        "dataframe", con=df_con, if_exists="replace", index=True, index_label="date"
    )
    trade_con = connect_to_db(f"{new_save_dir}/trade_log.db", create=True)
    result["trade_df"].to_sql(
        "trade_log", con=trade_con, if_exists="replace", index=True, index_label="date"
    )

    # plot
    create_plot(result["df"], result["trade_df"])

    plt.savefig(f"{new_save_dir}/plot.png")
