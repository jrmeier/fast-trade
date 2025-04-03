from typing import Any, Dict, List, Tuple
import random

# Constants
FREQUENCY_MAP = ["1Min", "5Min", "15Min", "30Min", "1h", "4h", "8h", "12h"]
COLUMNS = ["close", "open", "low", "high"]
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

        # Position 2 - operator
        if pos1.startswith("#"):
            gene_name = pos1[1:]
            # Check if the value is already a valid column
            if gene_map[gene_name] in predefined_sets["columns"]:
                new_condition[0] = gene_map[gene_name]
            else:
                try:
                    float_value = float(gene_map[gene_name])
                    operator_idx = int(
                        float_value * (len(predefined_sets["operators"]) - 1)
                    )
                    operator_idx = max(
                        0,
                        min(
                            operator_idx,
                            len(predefined_sets["operators"]) - 1,
                        ),
                    )
                    new_condition[1] = predefined_sets["operators"][operator_idx]
                except (ValueError, TypeError):
                    raise ValueError(f"Invalid gene name: {gene_name}")

        if pos2.startswith("#"):
            gene_name = pos2[1:]
            # Check if the value is already a valid column
            if gene_map[gene_name] in predefined_sets["columns"]:
                new_condition[2] = gene_map[gene_name]
            else:
                try:
                    float_value = float(gene_map[gene_name])
                    operator_idx = int(
                        float_value * (len(predefined_sets["columns"]) - 1)
                    )
                    operator_idx = max(
                        0,
                        min(
                            operator_idx,
                            len(predefined_sets["columns"]) - 1,
                        ),
                    )
                    new_condition[2] = predefined_sets["columns"][operator_idx]
                except (ValueError, TypeError):
                    raise ValueError(f"Invalid gene name: {gene_name}")

        if operator.startswith("#"):
            gene_name = operator[1:]
            # Check if the value is already a valid operator
            if gene_map[gene_name] in predefined_sets["operators"]:
                new_condition[1] = gene_map[gene_name]
            else:
                try:
                    operator_idx = int(
                        float(gene_map[gene_name])
                        * (len(predefined_sets["operators"]) - 1)
                    )
                    operator_idx = max(
                        0, min(operator_idx, len(predefined_sets["operators"]) - 1)
                    )
                    new_condition[1] = predefined_sets["operators"][operator_idx]
                except (ValueError, TypeError):
                    raise ValueError(f"Invalid gene name: {gene_name}")

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
        if freq_value in FREQUENCY_MAP:
            new_strategy["freq"] = freq_value
        else:
            # Try to convert to float and use as index
            try:
                freq_idx = int(float(freq_value) * (len(FREQUENCY_MAP) - 1))
                freq_idx = max(0, min(freq_idx, len(FREQUENCY_MAP) - 1))
                new_strategy["freq"] = FREQUENCY_MAP[freq_idx]
            except ValueError:
                # Default to strategy freq or 1h if conversion fails
                new_strategy["freq"] = strategy.get("freq", "1h")
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

    # if there are no enter or exit conditions, skip the process_conditions function
    if len(strategy.get("enter", [])) > 0:
        new_strategy["enter"] = process_conditions(
            strategy.get("enter", []), gene_map, predefined_sets, "enter"
        )
    else:
        # look in the genes for any enter conditions
        if "num_enter" in gene_map:
            # generate the number of enter conditions
            gen_number = gene_map["num_enter"]
            new_strategy["enter"] = [
                generate_random_condition(predefined_sets, "enter")
                for _ in range(int(gen_number))
            ]

    if len(strategy.get("exit", [])) > 0:
        new_strategy["exit"] = process_conditions(
            strategy.get("exit", []), gene_map, predefined_sets, "exit"
        )
    else:
        if "num_exit" in gene_map:
            gen_number = gene_map["num_exit"]
            new_strategy["exit"] = [
                generate_random_condition(predefined_sets, "exit")
                for _ in range(int(gen_number))
            ]

    if len(strategy.get("any_enter", [])) > 0:
        new_strategy["any_enter"] = process_conditions(
            strategy.get("any_enter", []), gene_map, predefined_sets, "any_enter"
        )
    else:
        if "num_any_enter" in gene_map:
            gen_number = gene_map["num_any_enter"]
            new_strategy["any_enter"] = [
                generate_random_condition(predefined_sets, "any_enter")
                for _ in range(int(gen_number))
            ]

    if len(strategy.get("any_exit", [])) > 0:
        new_strategy["any_exit"] = process_conditions(
            strategy.get("any_exit", []), gene_map, predefined_sets, "any_exit"
        )
    else:
        if "num_any_exit" in gene_map:
            gen_number = gene_map["num_any_exit"]
            new_strategy["any_exit"] = [
                generate_random_condition(predefined_sets, "any_exit")
                for _ in range(int(gen_number))
            ]

    # Copy other strategy properties
    new_strategy = {
        **strategy,
        **new_strategy,
    }

    return new_strategy
