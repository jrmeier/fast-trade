import concurrent.futures
import datetime
import json
import os
import random
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests

from fast_trade import run_backtest
from fast_trade.ml.evolution.models import (
    GeneDefinition,
    OptimizationConfig,
    OptimizationResult,
)
from fast_trade.ml.evolution.strategy_modifier import modify_strategy
from fast_trade.ml.evolution.utils import evaluate_solution_wrapper, sanitize_for_json

# Constants
ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", os.path.join(os.getcwd(), "ft_archive/ml"))


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
        config_file: Dict[str, Any] = {},
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
        self.config_file = config_file
        self.elites: List[Dict[str, Any]] = []
        os.makedirs(self.winners_dir, exist_ok=True)

        # Send job started webhook
        if self.api_url:
            payload = self.create_payload(event="job_started", generation=0)
            self.update_progress(payload)

    def create_payload(self, event: str = "job_started", generation: int = 0) -> Dict:
        # For initial payload, use base strategy without modifications
        if not hasattr(self, "best_solution") or self.best_solution is None:
            strat = self.base_strategy
        else:
            best_solution_tuples = [(k, str(v)) for k, v in self.best_solution.items()]
            best_solution_tuples.sort(key=lambda x: x[0])  # Sort by gene name
            strat = modify_strategy(
                self.base_strategy.copy(),
                best_solution_tuples,
                self.config_file.get("predefined_sets"),
            )

        # Calculate duration and time remaining if we have a start time
        duration = None
        estimated_time_remaining = None
        if hasattr(self, "start_time"):
            duration = datetime.datetime.now() - self.start_time
            if generation > 0:
                estimated_time_remaining = (
                    duration * self.config.num_generations
                ) / generation - duration
                estimated_time_remaining = datetime.timedelta(
                    seconds=estimated_time_remaining.total_seconds()
                )
                estimated_time_remaining = str(estimated_time_remaining)
            duration = str(duration)

        # Calculate diversity if we have a population
        diversity = None
        if hasattr(self, "population") and self.population:
            diversity = self.calculate_diversity()

        # Calculate best fitness and stagnation counter if available
        best_fitness = getattr(self, "best_fitness", 0)
        stagnation_counter = getattr(self, "stagnation_counter", 0)

        # Calculate percent complete
        percent_complete = 0
        if generation > 0:
            percent_complete = generation / self.config.num_generations

        return {
            "event": event,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "config": self.config_file,
            "fitness": self.fitness,
            "strategy": strat,
            "fitness_weights": self.fitness,
            "percent_complete": percent_complete,
            "genes": [gene.__dict__ for gene in self.genes],
            "status": (
                "running"
                if event in ["job_started", "job_update"]
                else "completed" if event == "job_completed" else "failed"
            ),
            "elites": self.elites,
            "error": None,
            "best_fitness": best_fitness or 0,
            "current_generation": generation,
            "total_generations": self.config.num_generations,
            "duration": duration,
            "estimated_time_remaining": estimated_time_remaining,
            "diversity": diversity,
            "stagnation_counter": stagnation_counter,
            "generation_history": self.generation_history,
        }

    def update_progress(self, payload: Dict[str, Any]) -> None:
        """Send progress update to API if URL is specified."""
        import time

        payload = {**self.create_payload(), **payload}
        payload = sanitize_for_json(payload)
        payload_str = json.dumps(payload, indent=2)

        with open(f"{self.winners_dir}/payload.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print("-" * 50)
        print(payload_str)
        print("-" * 50)
        if self.api_url:
            try:
                requests.post(self.api_url, json=payload, timeout=10)
            except Exception as e:
                print(f"Error sending payload to api: {e}")
        # time.sleep(1000)

    def create_initial_population(self) -> List[Dict[str, Any]]:
        """Create initial population with diverse solutions."""
        population: List[Dict[str, Any]] = []
        for _ in range(self.config.sol_per_pop):
            solution: Dict[str, Any] = {}
            for gene in self.genes:
                if gene.type == "categorical":
                    # get the values from the predefined sets
                    if gene.categories:
                        solution[gene.name] = random.choice(gene.categories)
                    else:
                        # Fallback to using values_ref directly from config
                        values = self.config_file.get("predefined_sets", {}).get(
                            gene.values_ref, []
                        )
                        if values:
                            solution[gene.name] = random.choice(values)
                        else:
                            # Last resort fallback
                            solution[gene.name] = "default"
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
            tournament_size = min(self.config.K_tournament, len(self.population))
            tournament = random.sample(list(enumerate(self.population)), tournament_size)
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
                if gene.type == "categorical":
                    if gene.categories:
                        mutated[gene.name] = random.choice(gene.categories)
                    else:
                        # Fallback to getting values from predefined_sets
                        values = self.config_file.get("predefined_sets", {}).get(
                            gene.values_ref, []
                        )
                        if values:
                            mutated[gene.name] = random.choice(values)
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
        strategy = modify_strategy(
            self.base_strategy.copy(),
            solution_tuples,
            self.config_file.get("predefined_sets"),
        )
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
        """Save only the top elites across all generations."""
        # Sort winners by fitness score
        sorted_winners = sorted(
            zip(winners, fitness_scores), key=lambda x: x[1], reverse=True
        )

        # Save the best winner of this generation
        best_winner, best_score = sorted_winners[0]

        # Convert solution to list of tuples for modify_strategy
        solution_tuples = [(k, str(v)) for k, v in best_winner.items()]
        strategy = modify_strategy(
            self.base_strategy.copy(),
            solution_tuples,
            self.config_file.get("predefined_sets"),
        )

        # Save the current generation's best to current.json
        winner_data = {
            "strategy": strategy,
            "fitness_score": float(best_score),
            "genes": best_winner,
            "summary": metrics,
            "generation": generation,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        # Sanitize data for JSON serialization
        sanitized_data = sanitize_for_json(winner_data)

        # Save to current.json (best of this generation)
        full_path = os.path.join(self.winners_dir, "current.json")
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(sanitized_data, f, indent=2)

        # Also save the best overall solution if this generation's best is better
        if best_score > self.best_fitness:
            # Update best fitness
            self.best_fitness = best_score

            # Save as the best overall solution
            best_path = os.path.join(self.winners_dir, "best.json")
            with open(best_path, "w", encoding="utf-8") as f:
                json.dump(sanitized_data, f, indent=2)

            # Also save as elite_N.json where N is based on rank
            elite_path = os.path.join(self.winners_dir, f"elite.json")
            with open(elite_path, "w", encoding="utf-8") as f:
                json.dump(sanitized_data, f, indent=2)

    def refresh_population(self) -> None:
        """Refresh the population when stagnation is detected.
        Keeps the best solutions and creates new random solutions for the rest."""
        print("Refreshing population due to stagnation...")

        # Calculate current diversity
        diversity = self.calculate_diversity()

        # Determine percentage of population to refresh based on diversity
        if (
            diversity > 0.7
        ):  # High diversity but stagnation - focus more on exploitation
            refresh_percent = max(0.3, min(0.7, self.config.refresh_percent))
            # Keep more elites in this case
            elite_percent = 1.0 - refresh_percent
        else:  # Low diversity with stagnation - need more exploration
            refresh_percent = min(0.9, max(0.5, self.config.refresh_percent))
            # Keep fewer elites
            elite_percent = 1.0 - refresh_percent

        # Calculate how many solutions to keep vs refresh
        pop_size = len(self.population)
        elite_count = max(
            1, min(int(pop_size * elite_percent), self.config.elitism * 2)
        )

        # Keep the top elites from current population
        elite_indices = np.argsort(self.fitness_scores)[-elite_count:]
        elites = [self.population[i] for i in elite_indices]

        # Generate new solutions
        # For high diversity scenario, create some solutions with small mutations from elites
        new_solutions = []
        if diversity > 0.7:
            # Create some solutions by small mutations from best solutions
            for i in range(min(elite_count, 3)):  # Take top 3 elites at most
                elite = elites[i] if i < len(elites) else elites[0]
                # Create several variants with small mutations
                for _ in range(2):  # Create 2 variants per elite
                    variant = elite.copy()
                    # Apply smaller mutations (25% of normal mutation rate)
                    for gene in self.genes:
                        if random.random() < self.config.mutation_percent_genes * 0.25:
                            if gene.type == "categorical" and gene.categories:
                                variant[gene.name] = random.choice(gene.categories)
                            elif gene.type == "int":
                                # Smaller range mutations
                                current = variant[gene.name]
                                range_size = (gene.max_value - gene.min_value) * 0.2
                                min_val = max(gene.min_value, current - range_size)
                                max_val = min(gene.max_value, current + range_size)
                                variant[gene.name] = random.randint(
                                    int(min_val), int(max_val)
                                )
                            elif gene.type == "float":
                                # Smaller range mutations
                                current = variant[gene.name]
                                range_size = (gene.max_value - gene.min_value) * 0.2
                                min_val = max(gene.min_value, current - range_size)
                                max_val = min(gene.max_value, current + range_size)
                                variant[gene.name] = random.uniform(min_val, max_val)
                            elif gene.type == "boolean":
                                # Lower chance of flipping boolean
                                if random.random() < 0.25:
                                    variant[gene.name] = not variant[gene.name]
                    new_solutions.append(variant)

        # Calculate how many completely new solutions we need
        remaining_count = pop_size - len(elites) - len(new_solutions)
        new_random_solutions = self.create_initial_population()[:remaining_count]

        # Combine all solutions
        self.population = new_random_solutions + new_solutions + elites

        # Ensure we have the right population size
        if len(self.population) > pop_size:
            self.population = self.population[:pop_size]

        # Reset fitness scores as we'll recalculate them
        self.fitness_scores = []

        # Don't reset stagnation counter fully, but reduce it based on refresh percentage
        self.stagnation_counter = int(self.stagnation_counter * (1 - refresh_percent))

        print(
            f"Population refreshed: {len(new_random_solutions)} new random solutions, "
            f"{len(new_solutions)} variants of elites, {len(elites)} elites kept."
        )

    def run(self) -> OptimizationResult:
        """Run the genetic algorithm."""
        try:
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
                            predefined_sets=self.config_file.get("predefined_sets"),
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

                # Refresh population check
                if self.stagnation_counter >= self.config.stagnation_threshold:
                    self.refresh_population()
                    # Skip the rest of this iteration since we've refreshed the population
                    # and need to reevaluate it in the next generation
                    continue

                # Adjust population size based on diversity
                diversity = self.calculate_diversity()
                if diversity < self.config.diversity_threshold:
                    pass
                    # self.config.sol_per_pop = min(self.config.sol_per_pop * 2, 50)
                elif diversity > 0.9:
                    #self.config.sol_per_pop = max(self.config.sol_per_pop // 2, 10)
                    pass
                # Create new population
                new_population: List[Dict[str, Any]] = []

                # Elitism: preserve best solutions
                elite_indices = np.argsort(self.fitness_scores)[-self.config.elitism :]
                new_population.extend([self.population[i] for i in elite_indices])

                self.elites = [self.population[i] for i in elite_indices]

                # Create offspring
                while len(new_population) < self.config.sol_per_pop:
                    parents = self.select_parents()
                    child = self.crossover(parents[0], parents[1])
                    child = self.mutate(child)
                    new_population.append(child)

                self.population = new_population
                print("len self.population: ", len(self.population))
                # Print progress
                os.system("cls" if os.name == "nt" else "clear")
                # load the current strategy
                payload = self.create_payload(event="job_update", generation=generation)

                self.update_progress(payload)

            if self.best_solution is None:
                raise ValueError("No valid solution found during optimization")

            # Convert best solution to list of tuples for modify_strategy
            best_solution_tuples = [(k, str(v)) for k, v in self.best_solution.items()]
            best_solution_tuples.sort(key=lambda x: x[0])  # Sort by gene name

            result = OptimizationResult(
                mapped_genes=best_solution_tuples,
                fitness=self.best_fitness,
                best_strategy=modify_strategy(
                    self.base_strategy.copy(),
                    best_solution_tuples,
                    self.config_file.get("predefined_sets"),
                ),
                started_at=self.started_at,
                completed_at=datetime.datetime.now(),
                generation_history=self.generation_history,
            )

            # Send job completed webhook
            if self.api_url:
                try:
                    payload = self.create_payload(
                        event="job_completed", generation=self.config.num_generations
                    )
                    payload["percent_complete"] = 1
                    payload["estimated_time_remaining"] = "0"
                    payload["WT"] = "heyy"
                    self.update_progress(payload)
                except Exception as e:
                    print(f"Error sending job completed webhook: {e}")

            return result

        except Exception as e:
            # Send job failed webhook
            if self.api_url:
                try:
                    payload = self.create_payload(
                        event="job_failed",
                        generation=generation if "generation" in locals() else 0,
                    )
                    payload["error"] = str(e)
                    payload["estimated_time_remaining"] = None
                    self.update_progress(payload)
                except Exception as webhook_error:
                    print(f"Error sending job failed webhook: {webhook_error}")
            raise e
