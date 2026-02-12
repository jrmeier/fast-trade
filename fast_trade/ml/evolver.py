import datetime
import warnings
import copy
import json
import os
import random
import string

import pygad

from fast_trade import run_backtest
from fast_trade.transformers_map import transformers_map

frequency_map = ["1Min", "5Min", "15Min", "30Min", "1h", "4h", "8h", "12h"]
columns = ["close", "open", "low", "high"]


def _normalize_types(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _normalize_types(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_types(v) for v in obj]
    if isinstance(obj, tuple):
        return [_normalize_types(v) for v in obj]
    try:
        import numpy as np

        if isinstance(obj, (np.ndarray,)):
            return [_normalize_types(v) for v in obj.tolist()]
    except Exception:
        pass
    try:
        import numpy as np

        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
    except Exception:
        pass
    return obj


def modify_strategy(strategy, genes, with_columns=False):
    """
    Modifies a trading strategy by replacing placeholder values with actual values from genes.

    This function supports using lambda functions as gene values, which will be executed
    at runtime to generate the actual values.

    Args:
        strategy: The strategy dictionary to modify
        genes: List of tuples (name, value) where value can be static or a callable function
        with_columns: If True, handle column mapping for column-related genes

    Returns:
        The modified strategy dictionary
    """
    # First, make a deep copy and normalize datetimes to avoid modifying the original
    strategy = _normalize_types(copy.deepcopy(strategy))

    # If with_columns is True, we need to preprocess the genes to handle column mappings
    if with_columns:
        mapped_genes = []
        for gene in genes:
            gene_name = gene[0]
            gene_value = gene[1]

            if callable(gene_value):
                # Call the function to get the actual value
                actual_value = gene_value()

                # Handle column type genes
                if "column" in gene_name:
                    column_idx = int(actual_value) % len(columns)
                    mapped_genes.append((gene_name, columns[column_idx]))
                else:
                    mapped_genes.append((gene_name, actual_value))
            else:
                # Use the static value directly
                if "column" in gene_name and isinstance(gene_value, (int, float)):
                    column_idx = int(gene_value) % len(columns)
                    mapped_genes.append((gene_name, columns[column_idx]))
                else:
                    mapped_genes.append((gene_name, gene_value))
        # Use the mapped genes instead of the original genes
        genes = mapped_genes

    # Build a lookup dictionary for faster gene retrieval
    gene_dict = {gene[0]: gene[1] for gene in genes}

    # Helper function to process any value that might contain placeholders
    def process_value(value):
        if isinstance(value, str) and value.startswith("#"):
            # This is a placeholder, replace with gene value
            gene_name = value.replace("#", "")
            if gene_name in gene_dict:
                gene_value = gene_dict[gene_name]
                if callable(gene_value):
                    # Call the function to get the actual value
                    return gene_value()
                else:
                    return gene_value
        elif isinstance(value, list):
            # Process each item in the list
            return [process_value(item) for item in value]
        elif isinstance(value, dict):
            # Process each value in the dictionary
            return {k: process_value(v) for k, v in value.items()}
        return value

    # Special handling for frequency
    if "freq" in gene_dict:
        freq_value = gene_dict["freq"]
        if callable(freq_value):
            freq_idx = freq_value()
            freq_idx = max(0, min(freq_idx, len(frequency_map) - 1))
            strategy["freq"] = frequency_map[freq_idx]
        else:
            if isinstance(freq_value, str) and freq_value in frequency_map:
                strategy["freq"] = freq_value
            else:
                freq_idx = int(freq_value)
                freq_idx = max(0, min(freq_idx, len(frequency_map) - 1))
                strategy["freq"] = frequency_map[freq_idx]

    # Process all datapoints
    if "datapoints" in strategy:
        for datapoint in strategy["datapoints"]:
            # Process arguments
            if "args" in datapoint:
                datapoint["args"] = process_value(datapoint["args"])
                # coerce numeric args that should be ints
                coerced_args = []
                for arg in datapoint["args"]:
                    if isinstance(arg, float):
                        coerced_args.append(int(round(arg)))
                    else:
                        coerced_args.append(arg)
                datapoint["args"] = coerced_args

            # Process any other fields that might contain placeholders
            for key in datapoint:
                if key != "args":  # Already processed args
                    datapoint[key] = process_value(datapoint[key])
                # if the key is transformer, make sure it's a valid transformer
            if "transformer" in datapoint:
                transformer = datapoint["transformer"]
                if transformer not in transformers_map:
                    raise ValueError(f"Invalid transformer: {transformer}")

    # Process logic arrays
    for logic_key in ["enter", "exit", "any_enter", "any_exit"]:
        if logic_key in strategy:
            strategy[logic_key] = process_value(strategy[logic_key])

    # Process any other top-level keys that might contain placeholders
    for key in strategy:
        if key not in ["datapoints", "enter", "exit", "any_enter", "any_exit", "freq"]:
            strategy[key] = process_value(strategy[key])

    return strategy


def _get_metric(summary: dict, key: str, default=0.0):
    if "." not in key:
        return summary.get(key, default)
    current = summary
    for part in key.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def fitness_func(solution, solution_idx, strategy, genes: list, fitness_config=None, error_callback=None):
    """
    Evaluates the fitness of a solution by running a backtest with the given strategy and genes.

    Args:
        solution: The current solution being evaluated. Can be None if using callable gene functions.
        solution_idx: The index of the solution.
        strategy: The base strategy to be optimized.
        genes: The list of genes representing strategy parameters.

    Returns:
        A float representing the fitness score of the solution.
    """
    # Map the numeric gene values to actual values
    mapped_genes = []

    if solution is None:
        # If solution is None, we're using callable functions directly
        # Use modify_strategy with with_columns=True to handle column mappings
        strategy_copy = modify_strategy(strategy.copy(), genes, with_columns=True)
    else:
        # Standard GA approach with numeric solution
        for i, gene in enumerate(genes):
            gene_name = gene[0]
            if "column" in gene_name:
                # Map numeric value to a column name
                column_idx = int(solution[i]) % len(columns)
                mapped_genes.append((gene_name, columns[column_idx]))
            else:
                # Use the numeric value directly
                mapped_genes.append((gene_name, solution[i]))

        # Modify the strategy based on the mapped genes
        strategy_copy = modify_strategy(strategy.copy(), mapped_genes)

    try:
        result = run_backtest(strategy_copy)
    except Exception as exc:
        if error_callback:
            error_callback(exc)
        return -1e9

    # Use the result to calculate fitness (e.g., total return)
    summary = result.get("summary", {})

    fitness_presets = {
        "aggressive": {
            "weights": {
                "return_perc": 0.5,
                "market_adjusted_return": 0.3,
                "sharpe_ratio": 0.1,
                "drawdown_metrics.max_drawdown_pct": -0.2,
                "num_trades": 0.1,
            },
            "min_trades": 5,
            "low_trades_penalty": -5.0,
        },
        "conservative": {
            "weights": {
                "return_perc": 0.2,
                "market_adjusted_return": 0.2,
                "sharpe_ratio": 0.3,
                "drawdown_metrics.max_drawdown_pct": -0.4,
                "num_trades": 0.1,
                "risk_metrics.sortino_ratio": 0.2,
            },
            "min_trades": 5,
            "low_trades_penalty": -5.0,
        },
    }

    default_fitness = fitness_presets["aggressive"]
    if isinstance(fitness_config, dict) and fitness_config.get("preset"):
        preset_name = fitness_config.get("preset")
        config = fitness_presets.get(preset_name, default_fitness)
    else:
        config = fitness_config or default_fitness
    weights = config.get("weights", default_fitness["weights"])
    min_trades = config.get("min_trades", 0)
    low_trades_penalty = config.get("low_trades_penalty", -5.0)

    fitness = 0.0
    for metric, weight in weights.items():
        val = _get_metric(summary, metric, 0.0)
        if metric.endswith("max_drawdown_pct"):
            val = abs(val)
        fitness += val * weight

    if min_trades:
        trades = _get_metric(summary, "num_trades", 0)
        if trades < min_trades:
            fitness += low_trades_penalty

    return fitness


def fitness_wrapper(ga_instance, solution, solution_idx, base_strategy, genes, fitness_config, error_callback):
    return fitness_func(
        solution,
        solution_idx,
        strategy=base_strategy,
        genes=genes,
        fitness_config=fitness_config,
        error_callback=error_callback,
    )


def save_yaml(strategy, filename):
    if not filename:
        rnd_str = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{date_str}_{rnd_str}.yml"
    # append the archive path to the filename
    # check the env variable ARCHIVE_PATH
    archive_path = os.getenv("ARCHIVE_PATH")
    if not archive_path:
        archive_path = "./ft_archive"

    # check the archive path
    if not os.path.exists(archive_path):
        os.makedirs(archive_path)
    # make sure this archive path is a directory and ends with ml
    if not archive_path.endswith("ml"):
        archive_path = os.path.join(archive_path, "ml")
    if not os.path.exists(archive_path):
        os.makedirs(archive_path)

    filename = os.path.join(archive_path, filename)
    if not filename.endswith((".yml", ".yaml")):
        filename = f"{filename}.yml"
    try:
        import yaml
    except Exception:
        yaml = None
    payload = _normalize_types(strategy)
    def _coerce_for_yaml(obj):
        return _normalize_types(obj)

    with open(filename, "w") as f:
        if yaml is not None:
            yaml.safe_dump(_coerce_for_yaml(payload), f, sort_keys=False)
        else:
            json.dump(payload, f, indent=2)


def optimize_strategy(
    base_strategy: dict,
    genes: list,
    num_generations: int = 100,
    num_parents_mating: int = 10,
    sol_per_pop: int = 10,
    num_genes: int = 6,
    parent_selection_type: str = "sss",
    crossover_type: str = "single_point",
    mutation_type: str = "random",
    mutation_percent_genes: int = 50,
    parallel_processing: int = 8,
    gene_space_provider=None,
    K_tournament=4,
    progress_callback=None,
    fitness_config=None,
):
    """
    Optimizes a trading strategy using a genetic algorithm.

    Args:
        base_strategy: A dictionary representing the base trading strategy.
        genes: A list of tuples containing (gene_name, gene_value).
               gene_value can be a static value, a lambda function, or a callable function.
        gene_space_provider: A function that takes a gene_type and returns its space configuration.
            If None, default ranges will be used based on gene name.

    Returns:
        The best solution and its fitness value
    """
    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Check if the genes contain callable functions (lambdas or regular functions)
    started_at = datetime.datetime.now()
    has_callable_genes = any(callable(gene[1]) for gene in genes)
    # If we have callable genes, we'll use them directly and skip the GA optimization
    if has_callable_genes:
        # print("Using callable gene functions directly for values")
        # Run a specified number of iterations with the callable genes
        best_solution = None
        best_fitness = float("-inf")
        best_modified_strategy = None

        for i in range(num_generations):
            # Each iteration calls the function to get new values
            fitness = fitness_func(None, i, base_strategy, genes, fitness_config=fitness_config)
            if progress_callback:
                progress_callback(
                    {
                        "generation": i + 1,
                        "total_generations": num_generations,
                        "best_fitness": best_fitness,
                        "fitness": fitness,
                    }
                )

            if fitness > best_fitness:
                best_fitness = fitness
                # Capture the current gene values (call the functions to get current values)
                best_solution = [
                    (gene[0], gene[1]() if callable(gene[1]) else gene[1])
                    for gene in genes
                ]
                # Save the best modified strategy
                best_modified_strategy = modify_strategy(
                    base_strategy.copy(), best_solution
                )

        # print(f"Best solution: {best_solution}")
        # print(f"Best fitness: {best_fitness}")

        # Save the best strategy
        fname = f"{date_str}.yml"
        best_modified_strategy["completed_at"] = datetime.datetime.now().isoformat()
        payload_to_save = {
            "strategy": best_modified_strategy,
            "fitness": best_fitness,
        }
        # Save the best strategy to disk
        save_yaml(payload_to_save, fname)

    # If we don't have callable genes, proceed with the normal GA optimization
    # Define the GA parameters
    # Create gene spaces - each gene needs its own range of possible values
    gene_space = []

    # Default gene space provider if none was provided
    if gene_space_provider is None:

        def default_gene_space_provider(gene_name):
            if "period" in gene_name.lower():
                return {"low": 2, "high": 200}
            elif "rsi" in gene_name.lower():
                return {"low": 1, "high": 100}
            elif (
                "ma" in gene_name.lower()
                or "ema" in gene_name.lower()
                or "sma" in gene_name.lower()
            ):
                return {"low": 2, "high": 200}
            else:
                return {"low": 0, "high": 100}

        gene_space_provider = default_gene_space_provider

    for gene in genes:
        gene_name = gene[0]
        if callable(gene[1]):
            gene_space.append(gene[1]())
        elif gene[1] is None:
            gene_space.append(gene_space_provider(gene_name))
        else:
            gene_space.append(gene[1])

    # Create an initial population with random values within the gene space
    initial_population = []
    for _ in range(sol_per_pop):
        solution = []
        for space in gene_space:
            if isinstance(space, list):
                # For discrete values (like column indices)
                solution.append(random.choice(space))
            elif isinstance(space, dict) and "low" in space and "high" in space:
                # For ranges
                solution.append(random.randint(space["low"], space["high"]))
            else:
                # Default
                solution.append(random.randint(1, 100))
        initial_population.append(solution)

    if isinstance(parallel_processing, int):
        parallel_processing = ["thread", parallel_processing]

    def on_generation(ga):
        if progress_callback:
            solution, solution_fitness, _ = ga.best_solution()
            mapped = []
            for i, gene in enumerate(genes):
                gene_name = gene[0]
                if gene_name == "freq":
                    freq_idx = int(solution[i])
                    freq_idx = max(0, min(freq_idx, len(frequency_map) - 1))
                    mapped.append((gene_name, frequency_map[freq_idx]))
                elif "column" in gene_name:
                    mapped.append((gene_name, columns[int(solution[i]) % len(columns)]))
                else:
                    mapped.append((gene_name, _normalize_types(solution[i])))
            progress_callback(
                {
                    "generation": ga.generations_completed,
                    "total_generations": num_generations,
                    "best_fitness": solution_fitness,
                    "best_genes": mapped,
                }
            )

    warnings.filterwarnings("ignore", category=UserWarning, module="pygad.pygad")

    error_state = {"count": 0}

    def error_callback(exc):
        if error_state["count"] < 1:
            error_state["count"] += 1
            print(f"Fitness error: {exc}")

    ga_instance = pygad.GA(
        num_generations=num_generations,
        num_parents_mating=num_parents_mating,
        fitness_func=lambda ga, sol, idx: fitness_wrapper(
            ga, sol, idx, base_strategy, genes, fitness_config, error_callback
        ),
            sol_per_pop=sol_per_pop,
            num_genes=len(
                genes
            ),  # Set number of genes based on the actual gene list length
            gene_space=gene_space,
            initial_population=initial_population,
            parent_selection_type=parent_selection_type,
            crossover_type=crossover_type,
            mutation_type=mutation_type,
            mutation_percent_genes=mutation_percent_genes,
            parallel_processing=parallel_processing,
            random_mutation_min_val=-1.0,
            random_mutation_max_val=1.0,
            save_best_solutions=True,
            K_tournament=K_tournament,
            on_generation=on_generation,
        )
    # Run the GA
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="pygad.pygad")
        ga_instance.run()

    # Get the best solution
    solution, solution_fitness, solution_idx = ga_instance.best_solution()

    # save the best solution
    # best_solution_file = f"./ft_archive/{date_str}_best_solution.yml"
    # print(f"Saving best solution to {best_solution_file}")

    # Ensure the directory exists
    os.makedirs("./ft_archive", exist_ok=True)

    # Save the solution to the file
    # convert the solution to the strategy format
    strategy_solution = []
    for i, gene in enumerate(genes):
        gene_name = gene[0]
        if gene_name == "freq":
            freq_idx = int(solution[i])
            freq_idx = max(0, min(freq_idx, len(frequency_map) - 1))
            strategy_solution.append(frequency_map[freq_idx])
        elif "column" in gene_name:
            strategy_solution.append(columns[int(solution[i]) % len(columns)])
        else:
            strategy_solution.append(solution[i])
    # save the strategy solution to the file
    # with open(best_solution_file, "w") as f:
    #     json.dump(strategy_solution, f, indent=4)

    # # Map numeric values to actual strategy values
    mapped_genes = []
    for i, gene in enumerate(genes):
        gene_name = gene[0]
        if gene_name == "freq":
            freq_idx = int(solution[i])
            freq_idx = max(0, min(freq_idx, len(frequency_map) - 1))
            mapped_genes.append((gene_name, frequency_map[freq_idx]))
        elif "column" in gene_name:
            # Map numeric value to a column name
            column_idx = int(solution[i]) % len(columns)
            mapped_genes.append((gene_name, columns[column_idx]))
        else:
            # Use the numeric value directly
            mapped_genes.append((gene_name, solution[i]))

    # # Create the best strategy using the mapped genes
    best_strategy = modify_strategy(base_strategy.copy(), mapped_genes)

    payload_to_save = {
        "strategy": best_strategy,
        "fitness": solution_fitness,
        "genes": mapped_genes,
        "completed_at": datetime.datetime.now().isoformat(),
        "started_at": started_at.isoformat(),
        "duration_seconds": (datetime.datetime.now() - started_at).total_seconds(),
        "duration_minutes": (datetime.datetime.now() - started_at).total_seconds() / 60,
        "duration_hours": (datetime.datetime.now() - started_at).total_seconds() / 3600,
    }
    save_yaml(payload_to_save, f"{date_str}_winner.yml")

    return mapped_genes, solution_fitness


if __name__ == "__main__":
    test_base_strategy = {
        "freq": "#freq",
        "enter": [
            ["rsi_lower", "<", "#rsi_lower"],  # Evolve RSI lower threshold
            ["zlema_short", ">", "#zlema_short_column"],
            ["zlema_long", "<", "#zlema_long_column"],
        ],
        "exit": [
            ["rsi_upper", ">", "#rsi_upper"],  # Evolve RSI upper threshold
            ["zlema_short", "<", "#zlema_short_column"],
            ["zlema_long", ">", "#zlema_long_column"],
        ],
        "datapoints": [
            {"name": "rsi_upper", "transformer": "rsi", "args": ["#rsi_upper_period"]},
            {"name": "rsi_lower", "transformer": "rsi", "args": ["#rsi_lower_period"]},
            {
                "name": "zlema_short",
                "transformer": "#long_transformer",
                "args": ["#zlema_short"],
            },
            {
                "name": "zlema_long",
                "transformer": "#short_transformer",
                "args": ["#zlema_long"],
            },
        ],
        "base_balance": 1000.0,
        "exit_on_end": False,
        "comission": 0.01,
        "trailing_stop_loss": 0.0,
        "lot_size_perc": 1.0,
        "max_lot_size": 0.0,
        "start_date": datetime.datetime(2024, 1, 1, 0, 0).isoformat(),
        "end_date": datetime.datetime(2025, 3, 4, 0, 0).isoformat(),
        "rules": None,
        "symbol": "BTCUSDT",
        "exchange": "binanceus",
        "completed_at": datetime.datetime.now().isoformat(),
    }

    lambda_genes = [
        ("zlema_short", lambda: random.randint(5, 50)),  # Using a lambda function
        ("zlema_short_column", lambda: random.randint(0, len(columns) - 1)),
        ("zlema_long", lambda: random.randint(50, 300)),  # Using a regular function
        ("zlema_long_column", lambda: random.randint(0, len(columns) - 1)),
        (
            "freq",
            lambda: random.randint(0, len(frequency_map) - 1),
        ),  # Using a lambda for frequency
        ("rsi_lower", lambda: random.randint(10, 40)),  # Dynamic RSI lower threshold
        ("rsi_upper", lambda: random.randint(60, 90)),  # Dynamic RSI upper threshold
        ("rsi_lower_period", lambda: random.randint(1, 100)),
        ("rsi_upper_period", lambda: random.randint(1, 100)),
        ("long_transformer", lambda: random.choice(["zlema", "sma", "ema"])),
        ("short_transformer", lambda: random.choice(["zlema", "sma", "ema"])),
    ]

    # Call optimize_strategy with lambda genes
    # res = modify_strategy(test_base_strategy, lambda_genes, with_columns=True)
    # print(res)
    res = optimize_strategy(
        base_strategy=test_base_strategy,
        genes=lambda_genes,
        num_generations=1,
        parallel_processing=["thread", 6],
        sol_per_pop=3,
        num_parents_mating=2,
        mutation_percent_genes=[
            50,
            10,
        ],  # 30% mutation for poor strategies, 10% for good ones
        crossover_type="uniform",
        mutation_type="adaptive",
        parent_selection_type="tournament",
        K_tournament=4,
    )
