import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GeneDefinition:
    """Definition of a gene in the genetic algorithm."""

    name: str
    type: str  # 'int', 'float', 'categorical', 'boolean'
    args: List[Any] = field(default_factory=list)
    values_ref: str = ""
    categories: Optional[List[str]] = None
    min_value: float = 0.0
    max_value: float = 100.0

    def __post_init__(self):
        """Set min_value and max_value based on args for int and float types."""
        if self.type in ("int", "float") and len(self.args) >= 2:
            self.min_value = self.args[0]
            self.max_value = self.args[1]


@dataclass
class OptimizationConfig:
    """Configuration for genetic algorithm optimization."""

    num_generations: int = 100
    num_parents_mating: int = 10
    sol_per_pop: int = 20
    parent_selection_type: str = "tournament"
    crossover_type: str = "uniform"
    mutation_type: str = "adaptive"
    mutation_percent_genes: float = field(default=0.1, metadata={"type": float})
    parallel_processing: int = 8
    use_parallel: bool = False  # Flag to enable/disable parallel processing
    K_tournament: int = 4
    elitism: int = 2  # Number of best solutions to preserve
    diversity_threshold: float = 0.7
    stagnation_threshold: int = 10
    early_stopping_patience: int = 20
    min_improvement: float = 0.001
    fitness: Dict[str, Any] = field(default_factory=dict)
    refresh_generations: int = 10
    refresh_percent: float = 0.5

    def __post_init__(self):
        """Normalize mutation_percent_genes to a probability in [0, 1]."""
        try:
            value = float(self.mutation_percent_genes)
        except (TypeError, ValueError):
            value = 0.1
        # If user supplied percentage (e.g., 5 or 10), scale down
        if value > 1.0:
            value = value / 100.0
        # Clamp to [0, 1]
        if value < 0.0:
            value = 0.0
        if value > 1.0:
            value = 1.0
        self.mutation_percent_genes = value


@dataclass
class OptimizationResult:
    """Results from the optimization process."""

    mapped_genes: List[Tuple[str, str]]
    fitness: float
    best_strategy: Dict[str, Any]
    started_at: datetime.datetime
    completed_at: datetime.datetime
    generation_history: List[Dict[str, Any]]
