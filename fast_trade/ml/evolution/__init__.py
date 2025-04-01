import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fast_trade.ml.evolution.genetic_algorithm import GeneticAlgorithm
from fast_trade.ml.evolution.models import GeneDefinition, OptimizationConfig, OptimizationResult
from fast_trade.ml.evolution.strategy_modifier import FREQUENCY_MAP
from fast_trade.ml.evolution.utils import process_genes_from_config, save_optimization_results


def optimize_strategy(
    base_strategy: Dict[str, Any],
    genes: List[Tuple[str, Any]],
    config: Optional[OptimizationConfig] = None,
    run_id: str = "default",
    config_file: Dict = {},
    api_url: Optional[str] = None,
) -> OptimizationResult:
    """
    Optimizes a trading strategy using a genetic algorithm.

    Args:
        base_strategy: A dictionary representing the base trading strategy.
        genes: A list of tuples containing (gene_name, gene_value).
        config: Optional configuration for the genetic algorithm.
        run_id: Unique identifier for this optimization run.
        config_file: Configuration file contents.
        api_url: Optional URL to send progress updates to.

    Returns:
        OptimizationResult containing the best solution and metadata.
    """
    # save all the inputs to a json file with the run_id
    # make the directory if it doesn't exist
    archive_path = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive/ml"))
    os.makedirs(f"{archive_path}/{run_id}", exist_ok=True)
    with open(f"{archive_path}/{run_id}/inputs.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_id": run_id,
                **config_file,
            },
            f,
            indent=2,
        )
        
    if api_url:
        print("Reporting to: ", api_url)

    config = config or OptimizationConfig()

    genes = process_genes_from_config(genes)
    # Convert gene tuples to GeneDefinition objects
    gene_definitions: List[GeneDefinition] = []
    for gene_name, gene_value in genes:
        if callable(gene_value):
            # For callable genes, determine type and range
            sample_value = gene_value()
            if isinstance(sample_value, int):
                # Special handling for frequency gene
                if gene_name == "freq":
                    gene_definitions.append(
                        GeneDefinition(
                            name=gene_name,
                            type="int",
                            min_value=0.0,
                            max_value=float(len(FREQUENCY_MAP) - 1),
                        )
                    )
                # Special handling for period genes
                elif gene_name.endswith("_period"):
                    gene_definitions.append(
                        GeneDefinition(
                            name=gene_name,
                            type="int",
                            min_value=1.0,  # Ensure minimum period is 1
                            max_value=100.0,
                        )
                    )
                else:
                    gene_definitions.append(
                        GeneDefinition(
                            name=gene_name, type="int", min_value=0.0, max_value=100.0
                        )
                    )
            else:
                # For column selection, use float type to allow continuous values
                if gene_name.endswith("_column"):
                    gene_definitions.append(
                        GeneDefinition(
                            name=gene_name, type="float", min_value=0.0, max_value=1.0
                        )
                    )
                else:
                    gene_definitions.append(
                        GeneDefinition(
                            name=gene_name, type="float", min_value=-1.0, max_value=1.0
                        )
                    )
        else:
            # For static genes, determine type
            if isinstance(gene_value, bool):
                gene_definitions.append(GeneDefinition(name=gene_name, type="boolean"))
            elif isinstance(gene_value, str):
                gene_definitions.append(
                    GeneDefinition(
                        name=gene_name, type="categorical", categories=[gene_value]
                    )
                )
            else:
                gene_definitions.append(
                    GeneDefinition(
                        name=gene_name, type="float", min_value=-1.0, max_value=1.0
                    )
                )

    # Create and run genetic algorithm
    ga = GeneticAlgorithm(
        base_strategy,
        gene_definitions,
        config,
        fitness=config.fitness,
        run_id=run_id,
        api_url=api_url,
    )
    result = ga.run()

    # Save results
    save_optimization_results(result, run_id)

    return result


def run_evolver(evolver_config: Dict) -> None:
    """Run the evolver with the given config"""
    base_strategy = evolver_config["strategy"]
    genes = evolver_config["genes"]

    config = OptimizationConfig(
        **evolver_config["config"], fitness=evolver_config["fitness"]
    )
    run_id = str(uuid.uuid4())

    optimize_strategy(
        base_strategy=base_strategy,
        genes=genes,
        config=config,
        run_id=run_id,
        config_file=evolver_config,
        api_url=evolver_config.get("api_url", None),
    )
