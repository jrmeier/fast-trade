import sys
import json

from .cli_helpers import (
    open_strat_file,
    format_all_help_text,
    save,
    create_plot,
    format_command,
)
from .run_backtest import run_backtest
import matplotlib.pyplot as plt


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

        strat_obj = open_strat_file(args["strat"])
        strat_obj = {**strat_obj, **args}

        res = run_backtest(strat_obj, args["csv"])

        print(json.dumps((res["summary"]), indent=2))

        if args.get("save"):
            save(res, strat_obj)

        if args.get("plot"):
            create_plot(res["df"])

            plt.show()

        return

    if command == "help":
        print(format_all_help_text())
        return

    print("Command not found")
    print(format_all_help_text())


if __name__ == "__main__":
    main()
