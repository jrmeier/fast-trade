def handle_rule(result: dict, rule: list) -> bool:
    """
    Handle a single rule with support for dotted notation in nested dictionaries.
    Example: Using "a.b.c" will access result["a"]["b"]["c"]

    Returns
    -------
    bool, the result of the rule
    """
    column_name = rule[0]
    operator = rule[1]
    value_or_column_name = rule[2]

    # Handle nested dictionary access using dotted notation
    def get_nested_value(d: dict, key: str):
        keys = key.split(".")
        value = d
        for k in keys:
            value = value[k]
        return value

    # Get the actual value for comparison
    result_value = float(get_nested_value(result, column_name))

    # Handle the comparison value
    if isinstance(value_or_column_name, str):
        value = float(get_nested_value(result, value_or_column_name))
    else:
        value = float(value_or_column_name)

    if operator == ">":
        return result_value > value
    elif operator == "<":
        return result_value < value
    elif operator == ">=":
        return result_value >= value
    elif operator == "<=":
        return result_value <= value
    return False


def evaluate_rules(result: dict, rules: list) -> tuple:
    """
    Evaluate a backtest result against a list of rules. Useful for quickly checking if a backtest result meets certain criteria.

    Parameters
    ----------
    result: dict, the result of the backtest
    rules: list, the rules to evaluate

    Rule:
    [
        "column_name", # column name to compare
        "operator", # operator to compare
        "value_or_column_name" # value to compare
    ]

    Returns
    -------
    tuple, (all(res), any(res), res)
    """
    if not rules:
        return False, False, []

    res = []
    for rule in rules:
        try:
            res.append(handle_rule(result, rule))
        except Exception as e:
            print(e)

    if len(res) == 0:
        return False, False, []

    return all(res), any(res), res


def extract_error_messages(error_dict: dict) -> str:
    """
    Extract and format error messages from the error dictionary.

    Parameters
    ----------
    error_dict: dict, the dictionary containing error information

    Returns
    -------
    str, formatted error messages
    """
    messages = []

    def traverse_errors(d):
        if isinstance(d, dict):
            for key, value in d.items():
                if key == "msgs" and isinstance(value, list):
                    for msg in value:
                        if isinstance(msg, str):
                            messages.append(msg)
                        else:
                            messages.append(str(msg))
                else:
                    traverse_errors(value)
        elif isinstance(d, list):
            for item in d:
                traverse_errors(item)

    traverse_errors(error_dict)

    return "\n".join(messages)


if __name__ == "__main__":
    rules = [["trade_streaks.avg_win_streak", ">", 6]]
    result = {"trade_streaks": {"avg_win_streak": 5}}
    print(evaluate_rules(result, rules))

    # Example usage
    error_example = {
        "enter": {
            "error": True,
            "msgs": [
                'Datapoint "macd_macd" referenced in enter logic not found in datapoints.',
                'Datapoint "macd_signal" referenced in enter logic not found in datapoints.',
            ],
        }
    }
    print(extract_error_messages(error_example))
