from fast_trade.ml.evolution.models import OptimizationConfig


def test_mutation_percent_genes_normalization_basic():
    cfg = OptimizationConfig(mutation_percent_genes=0.1)
    assert cfg.mutation_percent_genes == 0.1


def test_mutation_percent_genes_normalization_percentage():
    cfg = OptimizationConfig(mutation_percent_genes=5)
    assert cfg.mutation_percent_genes == 0.05


def test_mutation_percent_genes_clamped_upper():
    cfg = OptimizationConfig(mutation_percent_genes=120)
    assert cfg.mutation_percent_genes == 1.0


def test_mutation_percent_genes_clamped_lower():
    cfg = OptimizationConfig(mutation_percent_genes=-2)
    assert cfg.mutation_percent_genes == 0.0


def test_mutation_percent_genes_str_coercion():
    cfg = OptimizationConfig(mutation_percent_genes="0.5")
    assert cfg.mutation_percent_genes == 0.5
    cfg2 = OptimizationConfig(mutation_percent_genes="10")
    assert cfg2.mutation_percent_genes == 0.1
