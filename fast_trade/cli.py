# flake8: noqa
from fast_trade.validate_backtest import validate_backtest
import sys
import json
from .cli_helpers import (
    open_strat_file,
    save,
    create_plot,
    run_backtest_helper,
    validate_helper
)
from fast_trade.update_symbol_data import update_symbol_data
from .run_backtest import run_backtest
import matplotlib.pyplot as plt
import datetime
import argparse
import os
from pprint import pprint
from .asset_explorer.actions.create_playground import create_playgroud
from .asset_explorer.actions.load_playground import load_playground
from .gui import start_playground

def main():
    parser = argparse.ArgumentParser(
        description="Fast Trade CLI",
        prog="ft",
    )

    sub_parsers = parser.add_subparsers()


    # build the argement parser downloading stuff
    default_archive_path = os.path.join(os.getcwd(), "archive")
    default_end_date = datetime.datetime.utcnow()
    default_start_date = default_end_date - datetime.timedelta(days=30)

    download_parser = sub_parsers.add_parser("download", help="download data")
    download_parser.add_argument("symbol", help="symbol to download", type=str)
    download_parser.add_argument(
        "--archive",
        help="path to directory to serve as the 'archive'",
        type=str,
        default=default_archive_path,
    )

    download_parser.add_argument(
        "--start",
        help="first date to start downloading data from. Recently Listed coins might not have a lot of data.",
        type=str,
        default=default_start_date.strftime("%Y-%m-%d"),
    )

    download_parser.add_argument(
        "--end",
        help="Last date to download data. Defaults to today.",
        type=str,
        default=default_end_date.strftime("%Y-%m-%d"),
    )

    download_parser.add_argument(
        "--exchange",
        help="Which exchange to download data from. Defaults to binance.com",
        type=str,
        default="binance.com",
        choices=["binance.com", "binance.us"],
    )

    backtest_parser = sub_parsers.add_parser("backtest", help="backtest a strategy")
    backtest_parser.add_argument(
        "strategy",
        help="path to strategy file",
        type=str,
    )

    backtest_parser.add_argument("data", help="path to data file for kline data.")
    backtest_parser.add_argument(
        "--mods", help="Modifiers for strategy/backtest", nargs="*"
    )
    backtest_parser.add_argument(
        "--save",
        help="save the backtest results to a directory",
        action="store_true",
        default=False,
    )
    backtest_parser.add_argument(
        "--plot",
        help="plot the backtest results",
        action="store_true",
        default=False,
    )

    validate_backtest_parser = sub_parsers.add_parser(
        "validate", help="validate a strategy file"
    )

    validate_backtest_parser.add_argument(
        "strategy",
        help="path to strategy file",
        type=str,
    )
    validate_backtest_parser.add_argument(
        "--mods", help="Modifiers for strategy/backtest", nargs="*"
    )

    playground_parser = sub_parsers.add_parser(
        "playground", help="create a playground"
    )


    args = parser.parse_args()
    command = sys.argv[1]

    commandMap = {
        "download": update_symbol_data,
        "backtest": run_backtest_helper,
        "validate": validate_helper,
        "create_playground": create_playgroud,
        "playground": start_playground


    }

    if command in commandMap:
        commandMap[command](args)
    else:
        raise Exception(f"Command {command} not found.")
    



if __name__ == "__main__":
    main()
