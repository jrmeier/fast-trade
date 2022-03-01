# flake8: noqa
import json
import os
import datetime
import pandas as pd
import matplotlib.pyplot as plt


def open_strat_file(fp):

    try:
        with open(fp, "r") as json_file:
            backtest = json.load(json_file)

        return backtest
    except Exception as e:
        print("error: ", e)


def create_plot(df):
    plot_df = pd.DataFrame(
        data={
            "Date": df.index,
            "Portfolio_Value": df["account_value"],
            "Close": df["close"],
            "Fees": df["fee"],
        }
    )

    plot_df.plot(x="Date", y=["Portfolio_Value", "Close", "Fees"])

    return plot_df


def save(result, strat_obj):
    """
    Save the dataframe, backtest, and plot into the specified path
    """
    save_path = "./saved_backtests"
    if not os.path.exists(save_path):
        os.mkdir(save_path)

    # dir exists, now make a new dir with the files
    new_dir = datetime.datetime.strftime(datetime.datetime.now(), "%Y_%m_%d_%H_%M_%S")

    new_save_dir = f"{save_path}/{new_dir}"
    os.mkdir(new_save_dir)

    # save the backtest args
    with open(f"{new_save_dir}/backtest.json", "w") as summary_file:
        summary_file.write(json.dumps(strat_obj, indent=2))

    # summary file
    with open(f"{new_save_dir}/summary.json", "w") as summary_file:
        summary_file.write(json.dumps(result["summary"], indent=2))

    # dataframe
    result["df"].to_csv(f"{new_save_dir}/dataframe.csv")
    result["trade_df"].to_csv(f"{new_save_dir}/trade_dataframe.csv")

    # plot
    create_plot(result["df"])

    plt.savefig(f"{new_save_dir}/plot.png")
