from .transformers_map import transformers_map
import re


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
        "datapoints": None,
        "enter": None,
        "exit": None,
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
            backtest_mirror[req] = {
                "error": True,
                "msgs": [f'Paramater "{req}" required'],
            }

    base_balance = backtest.get("base_balance")
    if base_balance:
        bb = match_field_type_to_value(base_balance)

        if isinstance(bb, str):
            backtest_mirror["base_balance"] = {
                "error": True,
                "msgs": ["base_balance must be a float or string"],
            }
    chart_period = backtest.get("chart_period")
    if chart_period:
        if not re.search(r"(^\d{1,4}((T)|(Min)|(H)|(D)|)$)", chart_period):
            backtest_mirror["chart_period"] = {
                "error": True,
                "msgs": ["Chart period not valid"],
            }

    # check the datapints
    dp_errors = []

    for dp in backtest.get("datapoints", []):
        # check that we have the transformer function
        trans = dp.get("transformer", "")
        if trans not in list(transformers_map.keys()):
            dp_errors.append(
                f'Tranformer "{trans}" not valid. See the transformers_map for valid transformers.'
            )

        if not dp.get("name"):
            dp_errors.append("Name is required.")

    if len(dp_errors):
        backtest_mirror["datapoints"] = {"error": True, "msgs": dp_errors}

    # check the logics

    # fill the indicator keys
    basic_keys = ["open", "high", "low", "close", "volume"]
    indicator_keys = [
        dp.get("name") for dp in backtest.get("datapoints", []) if dp.get("name")
    ]
    indicator_keys.extend(basic_keys)

    exit_errors = []
    any_exit_errors = []
    enter_errors = []
    any_enter_errors = []
    # by default these can always be used
    indicator_keys = list(set(indicator_keys))

    for logic in backtest.get("exit", []):
        for log in logic:
            if (
                log not in indicator_keys
                and isinstance(log, str)
                and log not in [">", "=", "<"]
                and not log.isnumeric()
            ):
                exit_errors.append(
                    f'Datapoint "{log}" referenced in exit logic not found in datapoints. Check datapoints and logic.'
                )

        if len(exit_errors):
            backtest_mirror["exit"] = {"error": True, "msgs": exit_errors}

    for logic in backtest.get("enter", []):
        for log in logic:
            if (
                log not in indicator_keys
                and isinstance(log, str)
                and log not in [">", "=", "<"]
                and not log.isnumeric()
            ):
                enter_errors.append(
                    f'Datapoint "{log}" referenced in enter logic not found in datapoints. Check datapoints and logic.'
                )

        if len(enter_errors):
            backtest_mirror["enter"] = {"error": True, "msgs": enter_errors}

    for logic in backtest.get("any_enter", []):
        for log in logic:
            if (
                log not in indicator_keys
                and isinstance(log, str)
                and log not in [">", "=", "<"]
            ):
                any_enter_errors.append(
                    f'Datapoint "{log}" referenced in any_enter \
                    logic not found in datapoints. Check datapoints and logic.'
                )
        if len(any_enter_errors):
            backtest_mirror["any_enter"] = {"error": True, "msgs": any_enter_errors}

    for logic in backtest.get("any_exit", []):
        for log in logic:
            if (
                log not in indicator_keys
                and isinstance(log, str)
                and log not in [">", "=", "<"]
            ):
                any_exit_errors.append(
                    f'Datapoint "{log}" referenced in any_exit logic not found in datapoints. Check datapoints and logic.'
                )

        if len(any_exit_errors):
            backtest_mirror["any_exit"] = {"error": True, "msgs": any_exit_errors}

    lot_size = backtest.get("lot_size", 0)

    if lot_size > 1:
        backtest_mirror["lot_size"] = {
            "error": True,
            "msgs": ["Lot size must be less than 1."],
        }

    if lot_size < 0:
        backtest_mirror["lot_size"] = {
            "error": True,
            "msgs": ["Lot size be larger than 0."],
        }

    return_value = backtest_mirror
    return_value["has_error"] = any(
        [backtest_mirror[key] for key in backtest_mirror.keys()]
    )
    return return_value


def match_field_type_to_value(field):
    if isinstance(field, str):
        if field.isnumeric():
            return int(field)
        if re.match(r"^-?\d+(?:\.\d+)$", field):  # if its a string in a float
            return float(field)
    return field
