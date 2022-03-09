# flake8: noqa
from fast_trade.validate_backtest import validate_backtest
import sys
import json
from .cli_helpers import (
    open_strat_file,
    save,
    create_plot,
)
from fast_trade.update_symbol_data import update_symbol_data
from .run_backtest import run_backtest
import matplotlib.pyplot as plt
import datetime
import argparse
import os
from pprint import pprint


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

    args = parser.parse_args()
    command = sys.argv[1]

    if command == "download":
        update_symbol_data(
            args.symbol, args.start, args.end, args.archive, args.exchange
        )

    if command == "backtest":
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

    if command == "validate":
        strat_obj = open_strat_file(args.strategy)
        if args.mods:
            mods = {}
            i = 0
            while i < len(args.mods):
                mods[args.mods[i]] = args.mods[i + 1]
                i += 2

            strat_obj = {**strat_obj, **mods}

        backtest = validate_backtest(strat_obj)

        pprint(backtest)


if __name__ == "__main__":
    main()
