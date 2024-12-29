def handle_rule(result: dict, rule: list) -> bool:
    """
    Handle a single rule

    Returns
    -------
    bool, the result of the rule
    """
    column_name = rule[0]
    operator = rule[1]
    value_or_column_name = rule[2]

    if isinstance(value_or_column_name, str):
        value = float(result[value_or_column_name])
    else:
        value = float(value_or_column_name)

    if operator == ">":
        return result[column_name] > value
    elif operator == "<":
        return result[column_name] < value
    elif operator == ">=":
        return result[column_name] >= value
    elif operator == "<=":
        return result[column_name] <= value
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
    res = []
    for rule in rules:
        try:
            res.append(handle_rule(result, rule))
        except Exception as e:
            print(e)
    return all(res), any(res), res
