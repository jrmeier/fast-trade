# flake8: noqa
from fast_trade.validate_backtest import validate_backtest
import sys
import json
from .cli_helpers import (
    open_strat_file,
    save,
    create_plot,
)
from .run_backtest import run_backtest
import matplotlib.pyplot as plt
import datetime
import argparse
import os
from pprint import pprint
from fast_trade.archive.cli import get_assets, download_asset
from fast_trade.archive.update_archive import update_archive

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


def backtest_helper(args):
    # match the mods to the kwargs
    strat_obj = open_strat_file(args.strategy)

    if not strat_obj:
        print("Could not open strategy file: {}".format(args.strategy))
        sys.exit(1)
    if args.mods:
        mods = {}
        i = 0
        while i < len(args.mods):
            mods[args.mods[i]] = args.mods[i + 1]
            i += 2

        strat_obj = {**strat_obj, **mods}
    backtest = run_backtest(strat_obj, data_path=args.data)

    if args.save:
        save(backtest, backtest["backtest"])

    if args.plot:
        create_plot(backtest["df"])

        plt.show()
    print(backtest)
    pprint(backtest["summary"])


def validate_helper(args):
    strat_obj = open_strat_file(args.strategy)
    if args.mods:
        mods = {}
        i = 0
        while i < len(args.mods):
            mods[args.mods[i]] = args.mods[i + 1]
            i += 2

        strat_obj = {**strat_obj, **mods}


command_map = {
    "download": download_asset,
    "backtest": backtest_helper,
    "validate": validate_helper,
    "assets": get_assets,
    "update_archive": update_archive,
}


def main():
    args = parser.parse_args()
    if not len(sys.argv) > 1:
        print("No command provided")
        sys.exit(1)
    command = sys.argv[1]
    try:
        command_map[command](**vars(args))
        print("Done running command: ", command)

    except Exception as e:
        print(f"Error running command {command}: {e}")
        sys.exit(1)
