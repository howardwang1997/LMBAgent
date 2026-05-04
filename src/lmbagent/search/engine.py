"""Search engine for finding similar and contrastive experiments.

Supports two search modes:
  - 'similar': find experiments with high cosine similarity in combined vectors
  - 'contrast': find experiments with similar design but different degradation patterns
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from lmbagent.data.models import BatteryDataset
from lmbagent.data.store import DataStore
from lmbagent.search.vectorizer import (
    compute_combined_vector,
    compute_degradation_vector,
    compute_design_vector,
    compute_performance_vector,
    cosine_similarity,
    euclidean_distance,
)


@dataclass
class SearchResult:
    """A single search result."""
    data_id: str
    score: float
    reason: str
    design_similarity: float = 0.0
    degradation_similarity: float = 0.0
    performance_similarity: float = 0.0


class SearchEngine:
    """Search engine over stored datasets."""

    def __init__(self, store: DataStore | None = None):
        self.store = store or DataStore()

    def search_similar(
        self,
        query_id: str,
        mode: str = "similar",
        top_k: int = 5,
        vector_type: str = "combined",
    ) -> list[SearchResult]:
        """Search for similar or contrastive experiments.

        Args:
            query_id: Dataset ID to search against.
            mode: 'similar' (cosine similarity on combined) or
                  'contrast' (similar design, different degradation).
            top_k: Number of results to return.
            vector_type: Which vector to use for 'similar' mode.

        Returns:
            List of SearchResult sorted by relevance.
        """
        query_ds = self.store.get(query_id)
        if query_ds is None:
            return []

        if mode == "similar":
            return self._search_similar(query_ds, top_k, vector_type)
        elif mode == "contrast":
            return self._search_contrast(query_ds, top_k)
        else:
            return []

    def _search_similar(
        self,
        query_ds: BatteryDataset,
        top_k: int,
        vector_type: str,
    ) -> list[SearchResult]:
        """Find datasets most similar to query by cosine similarity."""
        vec_fn = {
            "combined": compute_combined_vector,
            "design": compute_design_vector,
            "performance": compute_performance_vector,
            "degradation": compute_degradation_vector,
        }.get(vector_type, compute_combined_vector)

        query_vec = vec_fn(query_ds)

        results = []
        for data_id in self.store.list_ids():
            if data_id == query_ds.data_id:
                continue
            ds = self.store.get(data_id)
            if ds is None:
                continue

            ds_vec = vec_fn(ds)
            sim = cosine_similarity(query_vec, ds_vec)

            results.append(SearchResult(
                data_id=data_id,
                score=sim,
                reason=f"Cosine similarity ({vector_type}): {sim:.3f}",
                design_similarity=cosine_similarity(
                    compute_design_vector(query_ds), compute_design_vector(ds)
                ),
                degradation_similarity=cosine_similarity(
                    compute_degradation_vector(query_ds), compute_degradation_vector(ds)
                ),
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _search_contrast(
        self,
        query_ds: BatteryDataset,
        top_k: int,
    ) -> list[SearchResult]:
        """Find datasets with similar design but different degradation.

        Score = design_similarity * (1 - degradation_similarity)
        High score means: similar design but different failure modes.
        """
        q_design = compute_design_vector(query_ds)
        q_degrad = compute_degradation_vector(query_ds)

        results = []
        for data_id in self.store.list_ids():
            if data_id == query_ds.data_id:
                continue
            ds = self.store.get(data_id)
            if ds is None:
                continue

            d_sim = cosine_similarity(q_design, compute_design_vector(ds))
            g_sim = cosine_similarity(q_degrad, compute_degradation_vector(ds))

            contrast_score = d_sim * (1.0 - g_sim)

            diff_desc = self._describe_degradation_diff(query_ds, ds)

            results.append(SearchResult(
                data_id=data_id,
                score=contrast_score,
                reason=f"Design sim={d_sim:.2f}, Degradation sim={g_sim:.2f}. {diff_desc}",
                design_similarity=d_sim,
                degradation_similarity=g_sim,
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _describe_degradation_diff(
        self,
        ds_a: BatteryDataset,
        ds_b: BatteryDataset,
    ) -> str:
        """Describe key degradation differences between two datasets."""
        diffs = []

        try:
            from lmbagent.degradation.decomposition import decompose_degradation_modes
            res_a = decompose_degradation_modes(ds_a)
            res_b = decompose_degradation_modes(ds_b)

            if "error" in res_a or "error" in res_b:
                return ""

            contribs_a = res_a.get("mode_contributions", {})
            contribs_b = res_b.get("mode_contributions", {})

            all_modes = set(contribs_a) | set(contribs_b)
            for mode in sorted(all_modes):
                va = contribs_a.get(mode, 0)
                vb = contribs_b.get(mode, 0)
                delta = abs(va - vb)
                if delta > 10:
                    diffs.append(f"{mode}: {va:.0f}% vs {vb:.0f}%")
        except Exception:
            pass

        if diffs:
            return "Key differences: " + "; ".join(diffs[:5])
        return ""

    def search_by_description(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Simple keyword-based search over dataset metadata.

        Searches cell_id, chemistry, source_file, and design notes.
        """
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        results = []
        for data_id in self.store.list_ids():
            ds = self.store.get(data_id)
            if ds is None:
                continue

            searchable = " ".join([
                ds.cell_id or "",
                ds.chemistry or "",
                ds.test_name or "",
                ds.source_file or "",
            ]).lower()

            if ds.experiment_design:
                flat = ds.experiment_design.to_flat_dict()
                searchable += " " + " ".join(str(v) for v in flat.values() if v is not None)

            terms = set(searchable.split())
            overlap = len(query_terms & terms)
            if overlap > 0:
                score = overlap / max(len(query_terms), 1)
                results.append(SearchResult(
                    data_id=data_id,
                    score=score,
                    reason=f"Keyword match: {overlap}/{len(query_terms)} terms",
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
