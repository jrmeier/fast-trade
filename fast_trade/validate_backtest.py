import re

import pandas as pd

from .transformers_map import transformers_map

TRANSFORMER_GENERATED_KEYS = [
    "_macd",
    "_signal",
    "_ppo_line",
    "_ppo_signal",
    "_vw_macd",
    "_ev_macd",
    "_di_plus",
    "_di_minus",
    "_adx",
    "_bb_upper",
    "_bb_middle",
    "_bb_lower",
    "_kc_upper",
    "_kc_lower",
    "_do_upper",
    "_do_middle",
    "_do_lower",
    "_vip",
    "_vim",
    "_kst_line",
    "_kst_signal",
    "_wt1",
    "_wt2",
    "_tenkan_sen",
    "_kijun_sen",
    "_senkou_span_a",
    "_senkou_span_b",
    "_chikou_span",
]


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
        "freq": None,
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
        "start_date",
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
    freq = backtest.get("freq")
    if freq:
        if not re.search(r"(^\d{1,4}((T)|(Min)|(H)|(h)|(D)|)$)", freq):
            backtest_mirror["freq"] = {
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

    indicator_keys = [dp.get("name") for dp in backtest.get("datapoints", [])]
    indicator_keys.extend(basic_keys)
    # by default these can always be used
    indicator_keys = list(set(indicator_keys))
    allowed_operators = [">", "=", "<", ">=", "<="]

    def process_logics(logics: list, logic_type: str):
        logic_errors = []
        for logic in logics:
            res = process_logic(logic, logic_type)
            if res.get("has_error"):
                logic_errors.append(res)

        if len(logic_errors):
            return {"error": True, "msgs": logic_errors}
        if len(logics) == 0 and logic_type not in ["any_enter", "any_exit"]:
            return {"error": True, "msgs": [f"No {logic_type} logic found"]}
        return None

    def process_logic(logic: list, logic_type: str):
        # each logic is a list of strings
        # check each of these individually
        pos1 = logic[0]
        operator = logic[1]
        pos2 = logic[2]
        if len(logic) > 3:
            lookback = logic[3]
        else:
            lookback = 0

        messages = []

        if pos1 not in indicator_keys:
            # look deepter
            if isinstance(pos1, str):
                if not pos1.isnumeric():
                    # check if it is a transformer generated key
                    for tg in TRANSFORMER_GENERATED_KEYS:
                        if pos1.endswith(tg):
                            break
                    else:
                        messages.append(
                            f'Datapoint "{pos1}" referenced in {logic_type} logic not found in datapoints.'
                        )

        if pos2 not in indicator_keys:
            # look deepter
            if isinstance(pos2, str):
                if not pos2.isnumeric():
                    for tg in TRANSFORMER_GENERATED_KEYS:
                        if pos2.endswith(tg):
                            break
                    else:
                        messages.append(
                            f'Datapoint "{pos2}" referenced in {logic_type} logic not found in datapoints.'
                        )

        if operator not in allowed_operators:
            messages.append(
                f'Operator "{operator}" not valid. See the allowed_operators list.'
            )

        if lookback < 0:
            messages.append("Lookback must be greater than 0.")

        if len(messages):
            return {"has_error": True, "msgs": messages}

        return {"has_error": False, "msgs": []}

    # process each logic
    backtest_mirror["enter"] = process_logics(backtest.get("enter", []), "enter")
    backtest_mirror["exit"] = process_logics(backtest.get("exit", []), "exit")
    backtest_mirror["any_enter"] = process_logics(
        backtest.get("any_enter", []), "any_enter"
    )
    backtest_mirror["any_exit"] = process_logics(
        backtest.get("any_exit", []), "any_exit"
    )

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


def validate_backtest_with_df(backtest: dict, df: pd.DataFrame) -> None:
    errors = validate_backtest(backtest)
    if errors.get("has_error"):
        raise Exception(errors)

    if df.empty:
        raise Exception("Dataframe is empty. Check your data source.")

    errors = []

    for dp in backtest.get("datapoints", []):
        # print("dp: ", dp)
        if dp.get("name") not in df.columns:
            # check if the db is a transfromer generated key it just need to start with one of the keys
            # does the name start with any of the df columns
            for col in df.columns:
                # check the column name and see if it starts with an existing column name
                if col.startswith(dp.get("name")):
                    break
            else:
                errors.append(f'Datapoint "{dp.get("name")}" not found in dataframe.')
    if len(errors):
        raise Exception(errors)
