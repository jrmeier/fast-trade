import re

# from .build_data_frame import transformers_map,


def validate_backtest(backtest):
    """validates a backtest object and returns errors/warnings

    Parameters
    -----------
        backtest, user constructed backtest object

    Returns
    -------
        tuple, [errors, warnings], returns a tuple with any
        errors and warnings, respectively
    """

    backtest_mirror = {
        "base_balance": None,
        "chart_period": None,
        "chart_start": None,
        "chart_stop": None,
        "comission": None,
        "datapoints": {},
        "enter": [],
        "exit": [],
        "any_enter": None,
        "any_exit": None,
        "trailing_stop_loss": None,
        "exit_on_end": None,
    }

    required_keys = [
        "datapoints",
        "enter",
        "exit",
    ]

    curr_keys = list(backtest.keys())

    for req in required_keys:
        if req not in curr_keys:
            backtest_mirror[req] = {"error": True, "msg": ["Paramater required"]}

    base_balance = backtest.get("base_balance")
    if base_balance:
        bb = match_field_type_to_value(base_balance)

        if isinstance(bb, str):
            backtest_mirror["base_balance"] = {
                "error": True,
                "msg": ["base_balance must be a float or string"],
            }
    chart_period = backtest.get("chart_period")
    if chart_period:
        if not re.search(r"(^\d{1,4}((T)|(Min)|(H)|(D)|)$)", chart_period):
            backtest_mirror["chart_period"] = {
                "error": True,
                "msg": ["Chart period not valid"],
            }

    chart_stop = backtest.get("chart_stop")

    # datapoints = backtest.get("datapoints", [])
    # # now check the logic fields to the data points
    # if not len(datapoints):
    #     warnings.append("No datapoints set.")

    # else:
    #     columns = []
    #     logics = []

    #     for ind in datapoints:
    #         transformer = ind.get("transformer")
    #         name = ind.get("name")
    #         col = ind.get("col")

    #         # check the function is in the transformer map
    #         if transformer not in list(datapoints.keys()):
    #             errors.append(f"Transformer \"{transformer}\" is not a valid transformer")

    # def clean_fields(raw_val):

    #     if type(raw_val) is str:
    #         if raw_val.isnumeric():
    #             clean_val = float(raw_val)
    #         else:
    #             clean_val = raw_val

    #     return clean_val

    # for log in self.exit_logic:
    #     logic_keys.append(clean_fields(log.field_1))
    #     logic_keys.append(clean_fields(log.field_2))

    # for log in self.enter_logic:
    #     logic_keys.append(clean_fields(log.field_1))
    #     logic_keys.append(clean_fields(log.field_2))

    return backtest_mirror


def match_field_type_to_value(field):
    if isinstance(field, str):
        if field.isnumeric():
            return int(field)
        if re.match(r"^-?\d+(?:\.\d+)$", field):  # if its a string in a float
            return float(field)
    return field
