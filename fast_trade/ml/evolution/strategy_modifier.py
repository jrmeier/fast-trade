from typing import Any, Dict, List, Tuple
import random

# Constants
FREQUENCY_MAP = [
    "1Min",
    "5Min",
    "10Min",
    "15Min",
    "30Min",
    "45Min",
    "1h",
    "2h",
    "4h",
    "8h",
    "12h",
    "24h",
    "36h",
    "48h",
    "72h",
]
COLUMNS = ["close", "open", "low", "high", "volume"]
OPERATORS = ["<", ">", "=", "!="]
TRANSFORMERS = ["ema", "zlema", "sma"]


def process_conditions(
    original_conditions: List[List],
    gene_map: Dict[str, str],
    predefined_sets: Dict[str, List[str]],
    condition_type: str,
) -> List[List]:
    """Process enter or exit conditions with gene modifications.

    Args:
        original_conditions: List of original condition lists from strategy
        gene_map: Map of gene names to values
        predefined_sets: Dictionary of predefined value sets
        condition_type: Type of condition ("enter" or "exit")

    Returns:
        List of modified conditions
    """
    new_conditions = []
    for idx, condition in enumerate(original_conditions):
        new_condition = condition.copy()
        pos1 = new_condition[0]
        operator = new_condition[1]
        pos2 = new_condition[2]
        lookback = new_condition[3] if len(new_condition) > 3 else 1

        if pos1.startswith("#"):
            gene_name = pos1[1:]
            val = gene_map.get(gene_name)
            # If val matches a known column use it, else if it's a datapoint name use it, else leave as-is
            if isinstance(val, str):
                if val in predefined_sets.get("columns", []):
                    new_condition[0] = val
                else:
                    # allow referencing a datapoint by name
                    new_condition[0] = val
            else:
                # numeric on LHS is not meaningful for most comparisons; keep original
                pass

        if pos2.startswith("#"):
            gene_name = pos2[1:]
            val = gene_map.get(gene_name)
            # If numeric: use numeric threshold directly
            if isinstance(val, (int, float)) or (
                isinstance(val, str) and val.replace(".", "", 1).isdigit()
            ):
                try:
                    new_condition[2] = (
                        float(val) if "." in str(val) else int(float(val))
                    )
                except Exception:
                    new_condition[2] = val
            elif isinstance(val, str):
                # If it's a known column or datapoint name, pass it through
                if val in predefined_sets.get("columns", []):
                    new_condition[2] = val
                else:
                    new_condition[2] = val
            else:
                # default fallback: keep original token
                pass

        if operator.startswith("#"):
            gene_name = operator[1:]
            val = gene_map.get(gene_name)
            if isinstance(val, str) and val in predefined_sets.get("operators", []):
                new_condition[1] = val
            else:
                # try to coerce numeric to index if provided
                try:
                    idx = int(float(val))
                    ops = predefined_sets.get("operators", [])
                    if ops:
                        new_condition[1] = ops[max(0, min(idx, len(ops) - 1))]
                except Exception:
                    # leave operator unchanged if invalid
                    pass
        # Position 4 - lookback (if exists)
        if len(new_condition) > 3 and lookback.startswith("#"):
            gene_name = lookback[1:]
            try:
                new_condition[3] = int(float(gene_map[gene_name]))
            except (ValueError, TypeError):
                raise ValueError(f"Invalid gene name: {gene_name}")
        # print(new_condition)

        # make sure condition1 is not the same as condition2
        while new_condition[0] == new_condition[2]:
            new_condition[2] = random.choice(predefined_sets["columns"])

        new_conditions.append(new_condition)

    return new_conditions


def modify_strategy(
    strategy: Dict[str, Any],
    genes: List[Tuple[str, str]],
    predefined_sets: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Create a new strategy with evolved genes."""
    # Create a new strategy object with predefined sets
    new_strategy = {"predefined_sets": strategy.get("predefined_sets", {})}

    # Create a mapping of gene names to values
    gene_map = {gene_name: gene_value for gene_name, gene_value in genes}

    # Set frequency
    if "freq" in gene_map:
        freq_value = gene_map["freq"]
        # Check if the value is already a valid frequency
        new_strategy["freq"] = freq_value
    else:
        new_strategy["freq"] = strategy.get("freq", "1h")

    # Create datapoints
    new_strategy["datapoints"] = []
    for datapoint in strategy.get("datapoints", []):
        new_datapoint = datapoint.copy()
        transformer_name = new_datapoint["transformer"]
        if transformer_name.startswith("#"):
            transformer_name = transformer_name[1:]

        # Handle transformer - using direct gene name
        if transformer_name in gene_map:
            try:
                new_datapoint["transformer"] = gene_map[transformer_name]
            except (ValueError, TypeError):
                new_datapoint["transformer"] = gene_map[transformer_name]

        # Handle args (periods)
        if "args" in new_datapoint:
            new_args = []
            for arg in new_datapoint["args"]:
                if isinstance(arg, str) and arg.startswith("#"):
                    gene_name = arg[1:]  # Remove the # prefix
                    if gene_name in gene_map:
                        # Try to convert string to int if it represents a numeric value
                        try:
                            new_args.append(int(float(gene_map[gene_name])))
                        except (ValueError, TypeError):
                            new_args.append(gene_map[gene_name])
                    else:
                        new_args.append(arg)
                else:
                    new_args.append(arg)
            new_datapoint["args"] = new_args
        new_strategy["datapoints"].append(new_datapoint)

    def generate_random_datapoint(
        predefined_sets: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """Generate a random datapoint for the given predefined sets."""
        transformer = random.choice(predefined_sets["transformers"])
        args = [random.randint(1, 300)]
        name = f"{transformer}_{args[0]}"
        return {"name": name, "transformer": transformer, "args": args}

    # if there is a num_datapoints gene, generate the number of datapoints
    if "num_datapoints" in gene_map:
        num_datapoints = gene_map["num_datapoints"]
        new_dps = [
            generate_random_datapoint(predefined_sets)
            for _ in range(int(num_datapoints))
        ]
        new_strategy["datapoints"].extend(new_dps)

    # Process enter and exit conditions
    def generate_random_condition(
        predefined_sets: Dict[str, List[str]], condition_type: str
    ) -> List[List]:
        """Generate a random condition for the given condition type."""
        # Make a copy to avoid modifying the original
        pos_choices = predefined_sets["columns"].copy()

        # Only use datapoints from the CURRENT strategy
        dp_names = [dp["name"] for dp in new_strategy["datapoints"]]
        pos_choices.extend(dp_names)

        pos1 = random.choice(pos_choices)
        pos2 = random.choice(pos_choices)
        while pos1 == pos2:
            pos2 = random.choice(pos_choices)

        operator = random.choice(predefined_sets["operators"])
        return [pos1, operator, pos2]

    # Process enter conditions
    new_strategy["enter"] = []
    if len(strategy.get("enter", [])) > 0:
        new_strategy["enter"] = process_conditions(
            strategy.get("enter", []), gene_map, predefined_sets, "enter"
        )
    if "num_enter" in gene_map:
        gen_number = int(gene_map["num_enter"])
        for _ in range(gen_number):
            new_strategy["enter"].append(
                generate_random_condition(predefined_sets, "enter")
            )

    # Process exit conditions
    new_strategy["exit"] = []
    if len(strategy.get("exit", [])) > 0:
        new_strategy["exit"] = process_conditions(
            strategy.get("exit", []), gene_map, predefined_sets, "exit"
        )
    if "num_exit" in gene_map:
        gen_number = int(gene_map["num_exit"])
        for _ in range(gen_number):
            new_strategy["exit"].append(
                generate_random_condition(predefined_sets, "exit")
            )

    # Process any_enter conditions
    new_strategy["any_enter"] = []
    if len(strategy.get("any_enter", [])) > 0:
        new_strategy["any_enter"] = process_conditions(
            strategy.get("any_enter", []), gene_map, predefined_sets, "any_enter"
        )
    if "num_any_enter" in gene_map:
        gen_number = int(gene_map["num_any_enter"])
        for _ in range(gen_number):
            new_strategy["any_enter"].append(
                generate_random_condition(predefined_sets, "any_enter")
            )

    # Process any_exit conditions
    new_strategy["any_exit"] = []
    if len(strategy.get("any_exit", [])) > 0:
        new_strategy["any_exit"] = process_conditions(
            strategy.get("any_exit", []), gene_map, predefined_sets, "any_exit"
        )
    if "num_any_exit" in gene_map:
        gen_number = int(gene_map["num_any_exit"])
        for _ in range(gen_number):
            new_strategy["any_exit"].append(
                generate_random_condition(predefined_sets, "any_exit")
            )

    # Copy other strategy properties
    new_strategy = {
        **strategy,
        **new_strategy,
    }

    return new_strategy


def get_random_gene_values(
    genes: List[Dict[str, Any]], predefined_sets: Dict[str, List[str]]
) -> List[Tuple[str, Any]]:
    """Generate random values for a list of genes."""
    gene_values = []
    for gene in genes:
        gene_name = gene["name"]
        gene_type = gene["type"]
        if gene_type == "categorical":
            values_ref = gene.get("values_ref")
            if values_ref and values_ref in predefined_sets:
                gene_values.append(
                    (gene_name, random.choice(predefined_sets[values_ref]))
                )
        elif gene_type == "int":
            min_val, max_val = gene["args"]
            gene_values.append((gene_name, random.randint(min_val, max_val)))
    return gene_values


def to_numeric(new_value):
    """
    Helper function to convert string values to numeric types if possible.
    """
    if new_value.isdigit():
        return int(new_value)
    try:
        return float(new_value)
    except (ValueError, TypeError):
        return new_value


def replace_placeholders(data, replacements):
    """
    Recursively replace placeholders in a data structure (dict, list, string)
    with values from a replacements dictionary.
    """
    if isinstance(data, str):
        if data.startswith("#"):
            key = data[1:]
            if key in replacements:
                return to_numeric(replacements[key])
        return data
    if isinstance(data, list):
        return [replace_placeholders(item, replacements) for item in data]
    if isinstance(data, dict):
        return {k: replace_placeholders(v, replacements) for k, v in data.items()}
    return data


if __name__ == "__main__":
    predefined_sets = {
        "frequencies": [
            "1Min",
            "5Min",
            "10Min",
            "15Min",
            "30Min",
            "45Min",
            "1h",
            "2h",
            "4h",
            "8h",
        ],
        "operators": ["<", ">"],
        "transformers": ["sma", "ema", "zlema"],
        "columns": ["close", "open", "low", "high", "volume"],
    }
    genes = [
        {
            "name": "freq",
            "type": "categorical",
            "values_ref": "frequencies",
            "args": [],
        },
        {"name": "num_enter", "type": "int", "args": [2, 4]},
        {"name": "num_exit", "type": "int", "args": [2, 4]},
        {"name": "num_datapoints", "type": "int", "args": [1, 4]},
        {"name": "rsi_overbought", "type": "int", "args": [65, 95]},
        {"name": "rsi_oversold", "type": "int", "args": [5, 45]},
        {"name": "rsi_overbought_lookback", "type": "int", "args": [1, 10]},
        {"name": "rsi_oversold_lookback", "type": "int", "args": [1, 10]},
        {"name": "rsi_period", "type": "int", "args": [2, 30]},
    ]
    strategy = {
        "freq": "#freq",
        "enter": [["rsi", ">", "#rsi_overbought", "#rsi_overbought_lookback"]],
        "exit": [["rsi", "<", "#rsi_oversold", "#rsi_oversold_lookback"]],
        "datapoints": [{"name": "rsi", "transformer": "rsi", "args": ["#rsi_period"]}],
        "base_balance": 1000.0,
        "exit_on_end": False,
        "comission": 0.01,
        "trailing_stop_loss": 0.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0.0,
        "start_date": "2025-07-01T00:00:00",
        "end_date": "2025-09-01T00:00:00",
        "rules": None,
        "symbol": "BTC-USD",
        "exchange": "coinbase",
        "completed_at": None,
    }

    gene_values = get_random_gene_values(genes, predefined_sets)
    res = modify_strategy(strategy, gene_values, predefined_sets)
    import pprint

    pprint.pprint(res)
