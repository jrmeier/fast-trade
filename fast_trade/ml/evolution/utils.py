import json
import os
import math
from typing import Any, Dict, List, Tuple
import requests
from fast_trade.ml.evolution.models import GeneDefinition


def sanitize_for_json(obj: Any) -> Any:
    """Sanitize objects for JSON serialization by replacing inf/nan with null."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    return obj


def evaluate_solution_wrapper(
    solution: Dict[str, Any],
    base_strategy: Dict[str, Any],
    fitness_weights: Dict[str, Any],
    predefined_sets: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    """Standalone wrapper function for parallel evaluation of solutions.
    This must be at module level to be picklable for multiprocessing."""
    from fast_trade.ml.evolution.strategy_modifier import modify_strategy
    from fast_trade import run_backtest

    # Convert solution to list of tuples for modify_strategy
    solution_tuples = [(k, str(v)) for k, v in solution.items()]
    strategy = modify_strategy(base_strategy.copy(), solution_tuples, predefined_sets)
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


def process_genes_from_config(
    input_genes: List[Dict], predefined_sets: Dict[str, Any] = None
) -> List[GeneDefinition]:
    """Process genes from config and return a list of GeneDefinition objects with categories from predefined_sets.

    Args:
        input_genes: List of gene definitions from config
        predefined_sets: Dictionary of predefined sets for categorical genes

    Returns:
        List of GeneDefinition objects
    """
    new_genes = []
    predefined_sets = predefined_sets or {}

    for gene in input_genes:
        gene_type = gene.get("type", "int")
        gene_name = gene["name"]
        values_ref = gene.get("values_ref", "")
        args = gene.get("args", [])

        # Create the GeneDefinition object
        gene_definition = GeneDefinition(
            name=gene_name, type=gene_type, args=args, values_ref=values_ref
        )

        # Add categories for categorical genes
        if gene_type == "categorical" and values_ref and values_ref in predefined_sets:
            gene_definition.categories = predefined_sets[values_ref]

        new_genes.append(gene_definition)

    return new_genes
