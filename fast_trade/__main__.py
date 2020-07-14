import sys
import json
from pprint import pprint
from .cli_helpers import open_strat_file, format_all_help_text
from .run_backtest import run_backtest


def parse_args(raw_args):
    """
    args: raw args after the command line

    returns: dict of args as key value pairs
    """
    arg_dict = {}
    for raw_arg in raw_args:
        arg = raw_arg.split("=")
        arg_key = arg[0].split("--").pop()
        arg_dict[arg_key]=arg[1]
    
    return arg_dict

def main():
    if len(sys.argv) < 2:
        print(format_all_help_text())
        return

    command = sys.argv[1]

    args = parse_args(sys.argv[2:])

    if command == "backtest":
        strat_obj = open_strat_file(args['strat'])
        res = run_backtest(args['csv'], {**strat_obj, **args})
        
        pprint(res['summary'])
        return

    if command == "help":
        print(format_all_help_text())
        return
    
    print("Command not found")
    print(format_all_help_text())
    



if __name__ == "__main__":
    main()