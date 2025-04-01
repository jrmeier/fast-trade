import json
import os
import random
from typing import Any, Callable, Dict, List, Tuple

from fast_trade.ml.evolution.strategy_modifier import COLUMNS, FREQUENCY_MAP


def save_optimization_results(result: Any, run_id: str) -> None:
    """Save optimization results to a file."""
    archive_path = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive/ml"))
    results_dir = f"{archive_path}/{run_id}"
    os.makedirs(results_dir, exist_ok=True)

    result_dict = {
        "mapped_genes": result.mapped_genes,
        "fitness": result.fitness,
        "best_strategy": result.best_strategy,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "generation_history": result.generation_history,
    }

    filename = f"{results_dir}/winner.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2)


def evaluate_solution_wrapper(
    solution: Dict[str, Any],
    base_strategy: Dict[str, Any],
    fitness_weights: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    """Standalone wrapper function for parallel evaluation of solutions.
    This must be at module level to be picklable for multiprocessing."""
    from fast_trade.ml.evolution.strategy_modifier import modify_strategy
    from fast_trade import run_backtest

    # Convert solution to list of tuples for modify_strategy
    solution_tuples = [(k, str(v)) for k, v in solution.items()]
    strategy = modify_strategy(base_strategy.copy(), solution_tuples)
    result = run_backtest(strategy)

    # Calculate fitness using multiple metrics
    metrics = result.get("summary", {})
    fitness = 0

    def get_metric_value(metric: str) -> float:
        keys = metric.split(".")
        value = metrics
        for key in keys:
            value = value.get(key, 0)  # Default to 0 if the key is not found
        return value

    for metric, weight in fitness_weights.items():
        metric_value = get_metric_value(metric)
        fitness += metric_value * weight

    return (fitness, metrics)


def process_genes_from_config(input_genes: List[Dict]) -> List[Tuple[str, Any]]:
    """Process genes from config by creating appropriate generator functions."""
    new_genes = []

    # Define gene generator functions
    def create_int_generator(min_val: int, max_val: int) -> Callable:
        return lambda: random.randint(min_val, max_val)

    def create_float_generator(min_val: float, max_val: float) -> Callable:
        return lambda: random.uniform(min_val, max_val)

    def create_categorical_generator(values: List[str], gene_name: str) -> Callable:
        if not values:
            raise ValueError(
                f"Cannot create categorical generator for gene '{gene_name}' with empty values list"
            )
        return lambda: random.choice(values)

    for gene in input_genes:
        gene_type = gene.get("type", "int")
        gene_name = gene["name"]
        values_ref = gene.get("values_ref", None)

        if gene_type == "int":
            range_values = gene.get("range", [0, 100])
            new_genes.append(
                (gene_name, create_int_generator(range_values[0], range_values[1]))
            )
        elif gene_type == "float":
            range_values = gene.get("range", [0.0, 100.0])
            new_genes.append(
                (gene_name, create_float_generator(range_values[0], range_values[1]))
            )
        elif gene_type == "categorical":
            if values_ref == "columns":
                values = COLUMNS
            elif values_ref == "operators":
                values = ["<", ">", "=", "!="]  # Default operators if not specified
            elif values_ref == "transformers":
                values = ["ema", "zlema", "sma"]  # Default transformers if not specified
            elif values_ref == "frequencies":
                values = FREQUENCY_MAP
            else:
                values = values_ref if isinstance(values_ref, list) else []

            try:
                new_genes.append(
                    (gene_name, create_categorical_generator(values, gene_name))
                )
            except ValueError as e:
                print(f"Error processing gene {gene_name}: {str(e)}")
                # Fallback to a default value based on the gene name
                if "operator" in gene_name:
                    values = ["<", ">", "=", "!="]
                elif "transformer" in gene_name:
                    values = ["ema", "zlema", "sma"]
                elif "column" in gene_name:
                    values = COLUMNS
                else:
                    values = ["default"]  # Fallback for unknown categorical genes
                new_genes.append(
                    (gene_name, create_categorical_generator(values, gene_name))
                )
        else:
            # Default to int generator if type is unknown
            new_genes.append((gene_name, create_int_generator(0, 100)))

    return new_genes 