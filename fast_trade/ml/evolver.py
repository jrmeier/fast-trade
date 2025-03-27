import concurrent.futures
import datetime
import json
import os
import random
import uuid
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import requests

from fast_trade import run_backtest

# Constants
FREQUENCY_MAP = ["1Min", "5Min", "15Min", "30Min", "1h", "4h", "8h", "12h"]
COLUMNS = ["close", "open", "low", "high"]
ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive/ml"))


@dataclass
class GeneDefinition:
    """Definition of a gene in the genetic algorithm."""

    name: str
    type: str  # 'int', 'float', 'categorical', 'boolean'
    min_value: float = 0.0
    max_value: float = 100.0
    categories: List[str] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OptimizationConfig:
    """Configuration for genetic algorithm optimization."""

    num_generations: int = 100
    num_parents_mating: int = 10
    sol_per_pop: int = 20
    parent_selection_type: str = "tournament"
    crossover_type: str = "uniform"
    mutation_type: str = "adaptive"
    mutation_percent_genes: float = 0.1
    parallel_processing: int = 8
    use_parallel: bool = False  # Flag to enable/disable parallel processing
    K_tournament: int = 4
    elitism: int = 2  # Number of best solutions to preserve
    diversity_threshold: float = 0.7
    stagnation_threshold: int = 10
    early_stopping_patience: int = 20
    min_improvement: float = 0.001
    fitness: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    """Results from the optimization process."""

    mapped_genes: List[Tuple[str, str]]
    fitness: float
    best_strategy: Dict[str, Any]
    started_at: datetime.datetime
    completed_at: datetime.datetime
    generation_history: List[Dict[str, Any]]


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


def save_optimization_results(result: OptimizationResult, run_id: str) -> None:
    """Save optimization results to a file."""
    results_dir = f"{ARCHIVE_PATH}/{run_id}"
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


def evaluate_solution_wrapper(solution, base_strategy, fitness_weights):
    """Standalone wrapper function for parallel evaluation of solutions.
    This must be at module level to be picklable for multiprocessing."""
    # Convert solution to list of tuples for modify_strategy
    solution_tuples = [(k, str(v)) for k, v in solution.items()]
    strategy = modify_strategy(base_strategy.copy(), solution_tuples)
    result = run_backtest(strategy)

    # Calculate fitness using multiple metrics
    metrics = result.get("summary", {})
    fitness = 0

    def get_metric_value(metric):
        keys = metric.split(".")
        value = metrics
        for key in keys:
            value = value.get(key, 0)  # Default to 0 if the key is not found
        return value

    for metric, weight in fitness_weights.items():
        metric_value = get_metric_value(metric)
        fitness += metric_value * weight

    return (fitness, metrics)


class GeneticAlgorithm:
    """Enhanced genetic algorithm implementation."""

    def __init__(
        self,
        base_strategy: Dict[str, Any],
        genes: List[GeneDefinition],
        config: OptimizationConfig,
        fitness: Dict[str, Any],
        run_id: str,
        api_url: Optional[str] = None,
    ):
        self.base_strategy = base_strategy
        self.genes = genes
        self.config = config
        self.population: List[Dict[str, Any]] = []
        self.fitness_scores: List[float] = []
        self.best_solution: Optional[Dict[str, Any]] = None
        self.best_fitness: float = float("-inf")
        self.generation_history: List[Dict[str, Any]] = []
        self.stagnation_counter: int = 0
        self.started_at = datetime.datetime.now()
        self.fitness = fitness
        self.run_id = run_id
        self.api_url = api_url
        winners_dir = os.path.join(ARCHIVE_PATH, self.run_id)
        print(f"Directory: {winners_dir}")
        self.winners_dir = winners_dir

        os.makedirs(self.winners_dir, exist_ok=True)

    def create_initial_population(self) -> List[Dict[str, Any]]:
        """Create initial population with diverse solutions."""
        population: List[Dict[str, Any]] = []
        for _ in range(self.config.sol_per_pop):
            solution: Dict[str, Any] = {}
            for gene in self.genes:
                if gene.type == "categorical" and gene.categories:
                    solution[gene.name] = random.choice(gene.categories)
                elif gene.type == "int":
                    solution[gene.name] = random.randint(
                        int(gene.min_value), int(gene.max_value)
                    )
                elif gene.type == "float":
                    solution[gene.name] = random.uniform(gene.min_value, gene.max_value)
                elif gene.type == "boolean":
                    solution[gene.name] = random.choice([True, False])
            population.append(solution)
        return population

    def calculate_diversity(self) -> float:
        """Calculate population diversity."""
        if not self.population:
            return 1.0

        # Convert solutions to feature vectors
        feature_vectors: List[List[float]] = []
        for solution in self.population:
            vector: List[float] = []
            for gene in self.genes:
                value = solution[gene.name]
                if gene.type == "categorical" and gene.categories:
                    vector.append(float(gene.categories.index(value)))
                else:
                    vector.append(float(value))
            feature_vectors.append(vector)

        # Calculate average pairwise distance
        distances: List[float] = []
        for i in range(len(feature_vectors)):
            for j in range(i + 1, len(feature_vectors)):
                dist = np.linalg.norm(
                    np.array(feature_vectors[i]) - np.array(feature_vectors[j])
                )
                distances.append(float(dist))

        return float(np.mean(distances)) if distances else 0.0

    def select_parents(self) -> List[Dict[str, Any]]:
        """Select parents using tournament selection."""
        parents: List[Dict[str, Any]] = []
        for _ in range(self.config.num_parents_mating):
            tournament = random.sample(
                list(enumerate(self.population)), self.config.K_tournament
            )
            winner_idx = max(tournament, key=lambda x: self.fitness_scores[x[0]])[0]
            parents.append(self.population[winner_idx])
        return parents

    def crossover(
        self, parent1: Dict[str, Any], parent2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform crossover between two parents."""
        child: Dict[str, Any] = {}
        for gene in self.genes:
            if random.random() < 0.5:
                child[gene.name] = parent1[gene.name]
            else:
                child[gene.name] = parent2[gene.name]
        return child

    def mutate(self, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Mutate a solution using adaptive mutation."""
        mutated = solution.copy()
        for gene in self.genes:
            if random.random() < self.config.mutation_percent_genes:
                if gene.type == "categorical" and gene.categories:
                    mutated[gene.name] = random.choice(gene.categories)
                elif gene.type == "int":
                    mutated[gene.name] = random.randint(
                        int(gene.min_value), int(gene.max_value)
                    )
                elif gene.type == "float":
                    mutated[gene.name] = random.uniform(gene.min_value, gene.max_value)
                elif gene.type == "boolean":
                    mutated[gene.name] = not mutated[gene.name]
        return mutated

    def evaluate_solution(
        self, solution: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        """Evaluate a solution using backtesting."""
        # Convert solution to list of tuples for modify_strategy
        solution_tuples = [(k, str(v)) for k, v in solution.items()]
        strategy = modify_strategy(self.base_strategy.copy(), solution_tuples)
        result = run_backtest(strategy)

        # Calculate fitness using multiple metrics
        metrics = result.get("summary", {})

        fitness = 0

        def get_metric_value(metric: str):
            keys = metric.split(".")
            value = metrics
            for key in keys:
                value = value.get(key, 0)  # Default to 0 if the key is not found
            return value

        for metric, weight in self.fitness.items():
            metric_value = get_metric_value(metric)
            fitness += metric_value * weight  # Include negative values directly

        return (fitness, metrics)

    def save_winners(
        self,
        generation: int,
        winners: List[Dict[str, Any]],
        fitness_scores: List[float],
        metrics: Dict[str, Any],
    ) -> None:
        """Save the best winner from a generation to a file."""
        # Sort winners by fitness score
        sorted_winners = sorted(
            zip(winners, fitness_scores), key=lambda x: x[1], reverse=True
        )

        # Save only the best winner
        best_winner, best_score = sorted_winners[0]

        # Convert solution to list of tuples for modify_strategy
        solution_tuples = [(k, str(v)) for k, v in best_winner.items()]
        strategy = modify_strategy(self.base_strategy.copy(), solution_tuples)

        winner_data = {
            "strategy": strategy,
            "fitness_score": float(best_score),
            "genes": best_winner,
            "summary": metrics,
        }

        # Save to file
        full_path = os.path.join(self.winners_dir, "best.json")
        # create the directory if it doesn't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(winner_data, f, indent=2)

    def run(self) -> OptimizationResult:
        """Run the genetic algorithm."""
        # Initialize population
        self.population = self.create_initial_population()
        self.start_time = datetime.datetime.now()

        for generation in range(self.config.num_generations):
            # Evaluate population
            if self.config.use_parallel and self.config.parallel_processing > 1:
                # Use parallel processing if enabled
                with concurrent.futures.ProcessPoolExecutor(
                    max_workers=self.config.parallel_processing
                ) as executor:
                    # Use the standalone wrapper function with partial to bind the other arguments
                    eval_func = partial(
                        evaluate_solution_wrapper,
                        base_strategy=self.base_strategy,
                        fitness_weights=self.fitness,
                    )

                    # Execute in parallel
                    fitness_scores_results = list(
                        executor.map(eval_func, self.population)
                    )
            else:
                # Sequential processing
                fitness_scores_results = [
                    self.evaluate_solution(solution) for solution in self.population
                ]

            self.fitness_scores = [result[0] for result in fitness_scores_results]
            metrics = [result[1] for result in fitness_scores_results]
            # Update best solution
            best_idx = np.argmax(self.fitness_scores)
            if self.fitness_scores[best_idx] > self.best_fitness:
                self.best_solution = self.population[best_idx]
                self.best_fitness = self.fitness_scores[best_idx]
                self.stagnation_counter = 0
            else:
                self.stagnation_counter += 1

            # Save winners from this generation
            self.save_winners(
                generation, self.population, self.fitness_scores, metrics[best_idx]
            )

            # Record generation history
            self.generation_history.append(
                {
                    "generation": generation,
                    "best_fitness": self.best_fitness,
                    "avg_fitness": float(np.mean(self.fitness_scores)),
                    "diversity": self.calculate_diversity(),
                    "stagnation_counter": self.stagnation_counter,
                }
            )

            # Early stopping check
            if self.stagnation_counter >= self.config.early_stopping_patience:
                print(f"Early stopping at generation {generation}")
                break

            # Adjust population size based on diversity
            diversity = self.calculate_diversity()
            if diversity < self.config.diversity_threshold:
                self.config.sol_per_pop = min(self.config.sol_per_pop * 2, 50)
            elif diversity > 0.9:
                self.config.sol_per_pop = max(self.config.sol_per_pop // 2, 10)

            # Create new population
            new_population: List[Dict[str, Any]] = []

            # Elitism: preserve best solutions
            elite_indices = np.argsort(self.fitness_scores)[-self.config.elitism :]
            new_population.extend([self.population[i] for i in elite_indices])

            # Create offspring
            while len(new_population) < self.config.sol_per_pop:
                parents = self.select_parents()
                child = self.crossover(parents[0], parents[1])
                child = self.mutate(child)
                new_population.append(child)

            self.population = new_population

            # Print progress
            # clear the screen
            def update_progress():
                duration = datetime.datetime.now() - self.start_time
                estimated_time_remaining = (duration * self.config.num_generations) / (
                    generation + 1
                )
                # make this json serializable
                estimated_time_remaining = datetime.timedelta(
                    seconds=estimated_time_remaining.total_seconds()
                )
                estimated_time_remaining = str(estimated_time_remaining)
                best_fitness = self.best_fitness
                avg_fitness = float(np.mean(self.fitness_scores))
                diversity = self.calculate_diversity()
                stagnation_counter = self.stagnation_counter
                best_strategy_link = f"{self.winners_dir}/best.json"
                os.system("cls" if os.name == "nt" else "clear")
                # load the best strategy
                with open(best_strategy_link, "r", encoding="utf-8") as f:
                    best_strategy = json.load(f)
                percent_complete = generation / self.config.num_generations
                payload = {
                    "duration": str(duration),
                    "percent_complete": percent_complete,
                    "current_generation": generation,
                    "total_generations": self.config.num_generations,
                    "estimated_time_remaining": str(estimated_time_remaining),
                    "best_fitness": best_fitness,
                    "avg_fitness": avg_fitness,
                    "diversity": diversity,
                    "stagnation_counter": stagnation_counter,
                    "best_strategy_link": best_strategy_link,
                    "run_id": self.run_id,
                }
                # make a pretty payload
                payload_str = json.dumps(payload, indent=2)
                print(payload_str)
                print("-" * 50)
                # send the payload to the api
                payload["best_strategy"] = best_strategy
                if self.api_url:
                    requests.post(self.api_url, json=payload)

            update_progress()

        if self.best_solution is None:
            raise ValueError("No valid solution found during optimization")

        # Convert best solution to list of tuples for modify_strategy
        best_solution_tuples = [(k, str(v)) for k, v in self.best_solution.items()]

        return OptimizationResult(
            mapped_genes=best_solution_tuples,
            fitness=self.best_fitness,
            best_strategy=modify_strategy(
                self.base_strategy.copy(), best_solution_tuples
            ),
            started_at=self.started_at,
            completed_at=datetime.datetime.now(),
            generation_history=self.generation_history,
        )


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

    Returns:
        OptimizationResult containing the best solution and metadata.
    """
    # save all the inputs to a json file with the run_id
    # make the directory if it doesn't exist
    os.makedirs(f"{ARCHIVE_PATH}/{run_id}", exist_ok=True)
    with open(f"{ARCHIVE_PATH}/{run_id}/inputs.json", "w", encoding="utf-8") as f:
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
                values = [
                    "ema",
                    "zlema",
                    "sma",
                ]  # Default transformers if not specified
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


def run_evolver(evolver_config: Dict):
    """ Run the evolver with the given config """
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
