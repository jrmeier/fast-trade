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


def format_command(command):

    command_obj = help_dict[command]
    ret_str = f"\n\t{command}"
    ret_str += f"\n\t\t\t{command_obj['description']}"

    ret_str += f"\n\t\tusage"
    for ex in command_obj["examples"]:
        ret_str += f"\n\t\t\t{ex}"

    ret_str += f"\n\t\targs"
    for arg in command_obj["args"].keys():
        ret_str += f"\n\t\t\t{arg},"
        if command_obj["args"][arg]["required"]:
            ret_str += " required,"

        ret_str += f" {command_obj['args'][arg]['desc']}"

    return ret_str


def format_all_help_text():

    formated_string = "\nFast Trade Help\n\nCommands\n\n"

    for command in help_dict.keys():
        formated_string = formated_string + format_command(command)

    return formated_string


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


help_dict = {
    "validate": {
        "description": """Takes in a backtest object and returns
            a mirror object with errors if they exist
        """,
        "examples": ["ft validate --backtest./backtest.json"],
        "args": {"--backtest": {"desc": "path to the backtest file", "required": True}},
    },
    "download": {
        "description": "download data from Binance",
        "examples": ["ft download --symbol=BTCUSDT --start=2019-01-01"],
        "args": {
            "--symbol": {"desc": "Symbol to download", "required": False},
            "--archive": {
                "desc": "Path to the archive where the CSVs live",
                "required": False,
            },
            "--start": {"desc": "date to start downloading from", "required": False},
            "--end": {"desc": "date to stop downloading_from", "required": False},
            "--exchange": {
                "desc": "Exchange to use. Either binance.us or binance.com. binance.com is the default.",
                "required": False,
            },
        },
    },
    "backtest": {
        "description": """Runs a backtest with the given parameters.
            Any backtest modifications can be passed at the end of the command.
            """,
        "examples": ["ft backtest --csv=./datafile.csv/ --backtest=./backtest.json"],
        "args": {
            "--csv": {
                "desc": "path or paths to csv_file seperated by commands",
                "required": True,
            },
            "--backtest": {
                "desc": "path to backtest file, must json format",
                "required": True,
            },
            "--plot": {
                "desc": "opens a basic plot using matlib.plot",
                "required": False,
            },
            "--save": {
                "desc": "saves the dataframe, backtest, and plot in to the path",
                "required": False,
            },
        },
    },
}
