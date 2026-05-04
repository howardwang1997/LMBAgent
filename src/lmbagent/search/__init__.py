"""Search module: vectorize datasets and find similar/contrastive experiments."""

from lmbagent.search.vectorizer import (
    compute_design_vector,
    compute_performance_vector,
    compute_degradation_vector,
    compute_combined_vector,
    vectorize_dataset,
    cosine_similarity,
    euclidean_distance,
)
from lmbagent.search.engine import SearchEngine
