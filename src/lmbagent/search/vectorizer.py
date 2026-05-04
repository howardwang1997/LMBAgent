"""Dataset vectorizer for similarity and contrast search.

Converts a BatteryDataset into fixed-dimension numeric vectors:
  - Design vector: one-hot/encoded design factors
  - Performance vector: statistical features from cycling data
  - Degradation vector: NNLS decomposition weights

These vectors are used by the search engine for cosine-similarity-based
retrieval and contrast discovery.
"""

from __future__ import annotations

import numpy as np

from lmbagent.data.models import BatteryDataset
from lmbagent.degradation.features import compute_dataset_feature_vector


def compute_design_vector(dataset: BatteryDataset) -> np.ndarray:
    """Encode design factors into a numeric vector.

    Uses ExperimentDesign.to_flat_dict(), mapping categorical fields to
    hash-based numeric encodings and keeping numerical fields as-is.
    Returns a fixed-size vector (first 20 design fields, zero-padded).
    """
    if dataset.experiment_design is None:
        return np.zeros(20)

    flat = dataset.experiment_design.to_flat_dict()
    vec = []
    for key in sorted(flat.keys())[:20]:
        val = flat[key]
        if isinstance(val, (int, float)):
            vec.append(float(val))
        elif isinstance(val, (list, tuple)):
            vec.append(float(len(val)))
        elif isinstance(val, str):
            vec.append(float(hash(val) % 10000) / 10000.0)
        elif val is None:
            vec.append(0.0)
        else:
            vec.append(0.0)

    while len(vec) < 20:
        vec.append(0.0)
    return np.array(vec[:20], dtype=np.float64)


def compute_performance_vector(dataset: BatteryDataset) -> np.ndarray:
    """Compute performance feature vector from cycling statistics.

    Uses the existing compute_dataset_feature_vector and normalizes
    into a fixed-size numpy array.
    """
    feat_dict = compute_dataset_feature_vector(dataset)

    keys = [
        "num_cycles", "initial_cap", "final_cap", "max_cap", "min_cap",
        "fade_pct", "fade_rate", "ce_mean", "ce_std", "ce_trend",
        "hyst_mean", "hyst_trend", "ir_mean", "ir_trend",
        "dqdv_peak_shift", "dqdv_peak_decay", "retention_final",
    ]
    vec = []
    for k in keys:
        v = feat_dict.get(k, 0.0)
        vec.append(float(v) if v is not None else 0.0)

    while len(vec) < len(keys):
        vec.append(0.0)
    return np.array(vec, dtype=np.float64)


def compute_degradation_vector(dataset: BatteryDataset) -> np.ndarray:
    """Compute degradation mode weights vector.

    Runs NNLS decomposition and returns the mode contribution percentages
    as a fixed-size vector.
    """
    try:
        from lmbagent.degradation.decomposition import decompose_degradation_modes
        result = decompose_degradation_modes(dataset)
        if "error" in result:
            return np.zeros(7)
        mode_names = [
            "LLI", "LAM_pos", "LAM_neg", "ORI_pos", "ORI_neg", "conductivity", "dry_out",
        ]
        contribs = result.get("mode_contributions", {})
        vec = [contribs.get(m, 0.0) for m in mode_names]
        return np.array(vec, dtype=np.float64)
    except Exception:
        return np.zeros(7)


def compute_combined_vector(dataset: BatteryDataset) -> np.ndarray:
    """Compute the full combined vector: design + performance + degradation."""
    d = compute_design_vector(dataset)
    p = compute_performance_vector(dataset)
    g = compute_degradation_vector(dataset)
    return np.concatenate([d, p, g])


def vectorize_dataset(dataset: BatteryDataset) -> dict[str, np.ndarray]:
    """Return all vector types for a dataset."""
    return {
        "design": compute_design_vector(dataset),
        "performance": compute_performance_vector(dataset),
        "degradation": compute_degradation_vector(dataset),
        "combined": compute_combined_vector(dataset),
    }


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Compute euclidean distance between two vectors."""
    return float(np.linalg.norm(a - b))
