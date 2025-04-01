from typing import Any, Dict, List, Tuple

# Constants
FREQUENCY_MAP = ["1Min", "5Min", "15Min", "30Min", "1h", "4h", "8h", "12h"]
COLUMNS = ["close", "open", "low", "high"]


def modify_strategy(
    strategy: Dict[str, Any], genes: List[Tuple[str, str]]
) -> Dict[str, Any]:
    """Create a new strategy with evolved genes."""
    # Create a new strategy object with predefined sets
    new_strategy = {
        "predefined_sets": {
            "columns": COLUMNS,
            "operators": ["<", ">", "=", "!="],
            "transformers": ["ema", "zlema", "sma"],
            "frequencies": FREQUENCY_MAP,
        }
    }

    # Create a mapping of gene names to values
    gene_map = {gene_name: gene_value for gene_name, gene_value in genes}

    # Set frequency
    if "freq" in gene_map:
        freq_idx = int(float(gene_map["freq"]) * (len(FREQUENCY_MAP) - 1))
        freq_idx = max(0, min(freq_idx, len(FREQUENCY_MAP) - 1))
        new_strategy["freq"] = FREQUENCY_MAP[freq_idx]
    else:
        new_strategy["freq"] = strategy.get("freq", "1h")

    # Create datapoints
    new_strategy["datapoints"] = []
    for datapoint in strategy.get("datapoints", []):
        new_datapoint = datapoint.copy()
        base_name = new_datapoint["name"]

        # Handle transformer
        if f"{base_name}_transformer" in gene_map:
            try:
                float_value = float(gene_map[f"{base_name}_transformer"])
                transformer_idx = int(
                    float_value
                    * (len(new_strategy["predefined_sets"]["transformers"]) - 1)
                )
                transformer_idx = max(
                    0,
                    min(
                        transformer_idx,
                        len(new_strategy["predefined_sets"]["transformers"]) - 1,
                    ),
                )
                new_datapoint["transformer"] = new_strategy["predefined_sets"][
                    "transformers"
                ][transformer_idx]
            except (ValueError, TypeError):
                new_datapoint["transformer"] = "sma"

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

    # Create enter conditions
    new_strategy["enter"] = []
    for condition in strategy.get("enter", []):
        new_condition = condition.copy()
        base_name = new_condition[0]

        # Handle operator
        if f"{base_name}_operator" in gene_map:
            try:
                float_value = float(gene_map[f"{base_name}_operator"])
                operator_idx = int(
                    float_value
                    * (len(new_strategy["predefined_sets"]["operators"]) - 1)
                )
                operator_idx = max(
                    0,
                    min(
                        operator_idx,
                        len(new_strategy["predefined_sets"]["operators"]) - 1,
                    ),
                )
                new_condition[1] = new_strategy["predefined_sets"]["operators"][
                    operator_idx
                ]
            except (ValueError, TypeError):
                new_condition[1] = ">"

        # Handle column
        if f"{base_name}_column" in gene_map:
            try:
                float_value = float(gene_map[f"{base_name}_column"])
                column_idx = int(
                    float_value * (len(new_strategy["predefined_sets"]["columns"]) - 1)
                )
                column_idx = max(
                    0,
                    min(
                        column_idx, len(new_strategy["predefined_sets"]["columns"]) - 1
                    ),
                )
                new_condition[2] = new_strategy["predefined_sets"]["columns"][
                    column_idx
                ]
            except (ValueError, TypeError):
                new_condition[2] = "close"
        elif isinstance(new_condition[2], str) and new_condition[2].startswith("#"):
            gene_name = new_condition[2][1:]  # Remove the # prefix
            if gene_name in gene_map:
                # Try to convert to int if it represents a numeric value
                try:
                    new_condition[2] = int(float(gene_map[gene_name]))
                except (ValueError, TypeError):
                    new_condition[2] = gene_map[gene_name]

        new_strategy["enter"].append(new_condition)

    # Create exit conditions (similar to enter)
    new_strategy["exit"] = []
    for condition in strategy.get("exit", []):
        new_condition = condition.copy()
        base_name = new_condition[0]

        # Handle operator
        if f"{base_name}_operator" in gene_map:
            try:
                float_value = float(gene_map[f"{base_name}_operator"])
                operator_idx = int(
                    float_value
                    * (len(new_strategy["predefined_sets"]["operators"]) - 1)
                )
                operator_idx = max(
                    0,
                    min(
                        operator_idx,
                        len(new_strategy["predefined_sets"]["operators"]) - 1,
                    ),
                )
                new_condition[1] = new_strategy["predefined_sets"]["operators"][
                    operator_idx
                ]
            except (ValueError, TypeError):
                new_condition[1] = ">"

        # Handle column
        if f"{base_name}_column" in gene_map:
            try:
                float_value = float(gene_map[f"{base_name}_column"])
                column_idx = int(
                    float_value * (len(new_strategy["predefined_sets"]["columns"]) - 1)
                )
                column_idx = max(
                    0,
                    min(
                        column_idx, len(new_strategy["predefined_sets"]["columns"]) - 1
                    ),
                )
                new_condition[2] = new_strategy["predefined_sets"]["columns"][
                    column_idx
                ]
            except (ValueError, TypeError):
                new_condition[2] = "close"
        elif isinstance(new_condition[2], str) and new_condition[2].startswith("#"):
            gene_name = new_condition[2][1:]  # Remove the # prefix
            if gene_name in gene_map:
                # Try to convert to int if it represents a numeric value
                try:
                    new_condition[2] = int(float(gene_map[gene_name]))
                except (ValueError, TypeError):
                    new_condition[2] = gene_map[gene_name]

        new_strategy["exit"].append(new_condition)

    # Copy other strategy properties
    for key, value in strategy.items():
        if key not in ["predefined_sets", "freq", "datapoints", "enter", "exit"]:
            new_strategy[key] = value

    return new_strategy 