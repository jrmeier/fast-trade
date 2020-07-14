import json

import json

def open_strat_file(fp):
    
    try:
        with open(fp,'r') as json_file:
            strat = json.load(json_file)

        return strat
    except Exception as e:
        print("error: ",e)

def format_command(command, command_obj):
    ret_str = f"\t{command}"
    ret_str += f"\n\t\t\t{command_obj['description']}"

    ret_str += f"\n\t\texample"
    for ex in command_obj['examples']:
        ret_str += f"\n\t\t\t{ex}"

    ret_str += f"\n\t\targs"
    for arg in command_obj['args'].keys():
        ret_str += f"\n\t\t\t{arg},"
        if command_obj['args'][arg]['required']:
            ret_str += " required,"
        
        ret_str += f" {command_obj['args'][arg]['desc']}"
    
    return ret_str

def format_all_help_text():
    with open('./fast_trade/cli_help.json','r') as help_file:
        help_file = json.load(help_file)
    
    formated_string = "\nFast Trade Help\n\nCommands\n\n"

    for command in help_file.keys():
        formated_string = formated_string+format_command(command, help_file[command])

    return formated_string