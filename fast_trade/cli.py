# flake8: noqa
from fast_trade.validate_backtest import validate_backtest
import sys
import json
from .build_data_frame import prepare_df

from .cli_helpers import (
    open_strat_file,
    format_all_help_text,
    save,
    create_plot,
    format_command,
)
from fast_trade.update_symbol_data import load_archive_to_df, update_symbol_data
from .run_backtest import run_backtest
import matplotlib.pyplot as plt
import datetime


def parse_args(raw_args):
    """
    args: raw args after the command line

    returns: dict of args as key value pairs
    """
    arg_dict = {}
    for raw_arg in raw_args:
        arg = raw_arg.split("=")
        arg_key = arg[0].split("--").pop()
        if len(arg) > 1:
            if arg[1] == "false":
                arg_dict[arg_key] = False
            elif arg[1] == "true":
                arg_dict[arg_key] == True
                # flake8: noqa
            elif arg[1] != "false" or arg[1] != "true":
                arg_dict[arg_key] = arg[1]
        else:
            arg_dict[arg_key] = True

    return arg_dict


def main():
    if len(sys.argv) < 2:
        print(format_all_help_text())
        return

    command = sys.argv[1]

    args = parse_args(sys.argv[2:])

    if command == "backtest":
        # check for help
        if "help" in args.keys():
            print(format_command(command))
            return

        strat_obj = open_strat_file(args["backtest"])
        strat_obj = {**strat_obj, **args}
        if args.get("data", "").endswith(".csv"):
            # use a csv file
            data = args["data"]
            try:
                res = run_backtest(strat_obj, ohlcv_path=data)
            except Exception as e:
                print("Error running backtest: ", e)
                return
        else:
            # load from the archive
            archive = args.get("archive", "./archive")
            try:
                archive_df = load_archive_to_df(strat_obj["symbol"], archive)
            except Exception as e:
                print("Error loading archive file: ", e)
                return

            try:

                archive_df = prepare_df(archive_df, strat_obj)
            except Exception as e:
                print("Error preparing the dataframe: ", e)
                return
            try:
                res = run_backtest(strat_obj, df=archive_df)
            except Exception as e:
                print("Error running backtest: ", e)
                return

        if res["summary"]:
            print(json.dumps((res["summary"]), indent=2))
        else:
            print("There was an error:")
            print(json.dumps((res["backtest_validation"]), indent=2))

        if args.get("save"):
            save(res, strat_obj)

        if args.get("plot"):
            create_plot(res["df"])

            plt.show()

        return

    if command == "help":
        print(format_all_help_text())
        return

    if command == "download":
        default_end = (
            datetime.datetime.utcnow() + datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        symbol = args.get("symbol", "BTCUSDT")
        arc_path = args.get("archive", "./archive/")
        start_date = args.get("start", "2017-01-01")
        end_date = args.get("end", default_end)
        exchange = args.get("exchange", "binance.com")
        update_symbol_data(symbol, start_date, end_date, arc_path, exchange)

        print("Done downloading ", symbol)
        return

    if command == "validate":
        print("args: ", args)
        backtest = open_strat_file(args["backtest"])
        if not backtest:
            print("backtest not found! ")
            return
        print("backtest: ", backtest)
        backtest = {**backtest, **args}

        res = validate_backtest(backtest)

        print(json.dumps(res, indent=2))
        return
    print("Command not found")
    print(format_all_help_text())


if __name__ == "__main__":
    main()
