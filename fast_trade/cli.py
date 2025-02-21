# flake8: noqa
import argparse
import datetime
import json
import os
import sys
from pprint import pprint

import matplotlib.pyplot as plt

from fast_trade.archive.cli import download_asset, get_assets
from fast_trade.archive.update_archive import update_archive
from fast_trade.validate_backtest import validate_backtest

from .cli_helpers import create_plot, open_strat_file, save
from .run_backtest import run_backtest

parser = argparse.ArgumentParser(
    description="Fast Trade CLI",
    prog="ft",
)

sub_parsers = parser.add_subparsers()

# build the argement parser downloading stuff
default_archive_path = os.path.join(os.getcwd(), "archive")
default_end_date = datetime.datetime.now(datetime.timezone.utc)
default_start_date = default_end_date - datetime.timedelta(days=30)

download_parser = sub_parsers.add_parser("download", help="download data")
download_parser.add_argument("symbol", help="symbol to download", type=str)
download_parser.add_argument(
    "exchange",
    help="Which exchange to download data from. Defaults to binance.com",
    type=str,
    default="binanceus",
    choices=["binancecom", "binanceus", "coinbase"],
)
download_parser.add_argument(
    "--start",
    help="Date to start downloading data from. Defaults to 30 days ago.",
    type=str,
    default=default_start_date.isoformat(),
)

download_parser.add_argument(
    "--end",
    help="Date to end downloading data. Defaults to today.",
    type=str,
    default=default_end_date.isoformat(),
)


backtest_parser = sub_parsers.add_parser("backtest", help="backtest a strategy")
backtest_parser.add_argument(
    "strategy",
    help="path to strategy file",
    type=str,
)

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

get_assets_parser = sub_parsers.add_parser("assets", help="get assets")
get_assets_parser.add_argument(
    "--exchange",
    help="",
    type=str,
    default="local",
    choices=["local", "binanceus", "binancecom", "coinbase"],
)

update_archive_parser = sub_parsers.add_parser(
    "update_archive", help="update the archive"
)


def backtest_helper(*args, **kwargs):
    # match the mods to the kwargs

    strat_obj = open_strat_file(kwargs.get("strategy"))

    if not strat_obj:
        print("Could not open strategy file: {}".format(kwargs.get("strategy")))
        sys.exit(1)
    if kwargs.get("mods"):
        mods = {}
        i = 0
        while i < len(kwargs.get("mods")):
            mods[kwargs.get("mods")[i]] = kwargs.get("mods")[i + 1]
            i += 2

        strat_obj = {**strat_obj, **mods}

    result = run_backtest(strat_obj)
    summary = result.get("summary")

    if kwargs.get("save"):
        save(result)

    if kwargs.get("plot"):
        create_plot(result.get("df"), result.get("trade_df"))

        plt.show()

    # modify the summary to make it more readable
    try:
        summary["mean_trade_len"] = (
            summary.get("mean_trade_len") / 60
        )  # convert to minutes
    except BaseException:
        summary["mean_trade_len"] = 0
    try:
        summary["max_trade_held"] = (
            summary.get("max_trade_held") / 60
        )  # convert to minutes
    except BaseException:
        summary["max_trade_held"] = 0
    try:
        summary["min_trade_len"] = (
            summary.get("min_trade_len") / 60
        )  # convert to minutes
    except BaseException:
        summary["min_trade_len"] = 0
    try:
        summary["median_trade_len"] = (
            summary.get("median_trade_len") / 60
        )  # convert to minutes
    except BaseException:
        summary["median_trade_len"] = 0

    pprint(summary)


def validate_helper(args):
    strat_obj = open_strat_file(args.get("strategy"))
    if args.get("mods"):
        mods = {}
        i = 0
        while i < len(args.get("mods")):
            mods[args.get("mods")[i]] = args.get("mods")[i + 1]
            i += 2

        strat_obj = {**strat_obj, **mods}

    validate_backtest(strat_obj)


command_map = {
    "download": download_asset,
    "backtest": backtest_helper,
    "validate": validate_helper,
    "assets": get_assets,
    "update_archive": update_archive,
    "-h": parser.print_help,
}


def main():
    args = parser.parse_args()
    if not len(sys.argv) > 1:
        command = "-h"
    else:
        command = sys.argv[1]
    # try:
    command_map[command](**vars(args))
    print("Done running command: ", command)

    # except Exception as e:
    #     print(f"Error running command {command}: {e}")
    #     sys.exit(1)


if __name__ == "__main__":
    main()
