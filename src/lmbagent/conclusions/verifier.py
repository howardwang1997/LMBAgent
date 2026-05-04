"""Conclusion verification engine.

Given new experimental data, checks whether existing conclusions are
supported, challenged, or need refinement by:
  1. Extracting features from the new data
  2. Finding related historical experiments via search
  3. Comparing degradation patterns and performance metrics
  4. Generating a verification verdict
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from lmbagent.conclusions.models import Conclusion, ConclusionStatus
from lmbagent.conclusions.store import ConclusionStore
from lmbagent.data.models import BatteryDataset
from lmbagent.data.store import DataStore
from lmbagent.degradation.features import compute_dataset_feature_vector
from lmbagent.search.engine import SearchEngine
from lmbagent.search.vectorizer import cosine_similarity, compute_performance_vector


@dataclass
class VerificationResult:
    """Result of verifying a conclusion against new data."""
    conclusion_id: str
    verdict: str  # "supported", "challenged", "inconclusive"
    evidence_summary: str
    related_experiments: list[str]
    confidence_change: str  # "unchanged", "increased", "decreased"
    details: str


def verify_conclusion(
    conclusion: Conclusion,
    new_data_id: str,
    store: DataStore | None = None,
) -> VerificationResult:
    """Verify a single conclusion against new experimental data.

    Args:
        conclusion: The conclusion to verify.
        new_data_id: ID of the new dataset to check against.
        store: DataStore instance.

    Returns:
        VerificationResult with verdict and details.
    """
    store = store or DataStore()
    engine = SearchEngine(store)

    new_ds = store.get(new_data_id)
    if new_ds is None:
        return VerificationResult(
            conclusion_id=conclusion.conclusion_id,
            verdict="inconclusive",
            evidence_summary=f"Dataset '{new_data_id}' not found",
            related_experiments=[],
            confidence_change="unchanged",
            details="Cannot verify: dataset not found",
        )

    new_feats = compute_dataset_feature_vector(new_ds)

    evidence_ds_list = []
    for eid in conclusion.evidence_ids:
        ds = store.get(eid)
        if ds is not None:
            evidence_ds_list.append(ds)

    if not evidence_ds_list:
        return _verify_by_keywords(conclusion, new_ds, new_feats, store, engine)

    related_ids = []
    for evidence_ds in evidence_ds_list:
        results = engine.search_similar(
            evidence_ds.data_id, mode="similar", top_k=3, vector_type="performance"
        )
        related_ids.extend(r.data_id for r in results)

    related_ids = list(dict.fromkeys(related_ids))
    if new_data_id in related_ids:
        related_ids.remove(new_data_id)

    new_perf = compute_performance_vector(new_ds)
    perf_sims = []
    for evidence_ds in evidence_ds_list:
        ev_perf = compute_performance_vector(evidence_ds)
        sim = cosine_similarity(new_perf, ev_perf)
        perf_sims.append(sim)

    avg_sim = sum(perf_sims) / len(perf_sims) if perf_sims else 0

    new_fade = new_feats.get("fade_pct", 0)
    new_ce = new_feats.get("ce_mean", 100)

    conclusion_lower = conclusion.statement.lower()

    support_signals = 0
    challenge_signals = 0
    details_parts = []

    if "fade" in conclusion_lower or "衰减" in conclusion_lower:
        if "fade_pct" in conclusion.scope or not conclusion.scope:
            evidence_fades = []
            for evidence_ds in evidence_ds_list:
                ev_feats = compute_dataset_feature_vector(evidence_ds)
                evidence_fades.append(ev_feats.get("fade_pct", 0))
            if evidence_fades:
                avg_ev_fade = sum(evidence_fades) / len(evidence_fades)
                if abs(new_fade - avg_ev_fade) / max(avg_ev_fade, 1) < 0.3:
                    support_signals += 2
                    details_parts.append(f"Fade {new_fade:.1f}% consistent with evidence avg {avg_ev_fade:.1f}%")
                else:
                    challenge_signals += 2
                    details_parts.append(f"Fade {new_fade:.1f}% differs from evidence avg {avg_ev_fade:.1f}%")

    if "coulombic" in conclusion_lower or "ce" in conclusion_lower or "库仑" in conclusion_lower:
        if new_ce > 99.5:
            support_signals += 1
            details_parts.append(f"CE {new_ce:.2f}% supports high efficiency claim")
        elif new_ce < 98:
            challenge_signals += 1
            details_parts.append(f"CE {new_ce:.2f}% challenges high efficiency claim")

    if avg_sim > 0.8:
        support_signals += 1
        details_parts.append(f"Performance similarity to evidence: {avg_sim:.2f}")
    elif avg_sim < 0.5:
        challenge_signals += 1
        details_parts.append(f"Low performance similarity: {avg_sim:.2f}")

    if not details_parts:
        details_parts.append("No specific evidence patterns matched conclusion keywords")

    if support_signals > challenge_signals:
        verdict = "supported"
        confidence_change = "increased"
    elif challenge_signals > support_signals:
        verdict = "challenged"
        confidence_change = "decreased"
    else:
        verdict = "inconclusive"
        confidence_change = "unchanged"

    summary = (
        f"Conclusion '{conclusion.conclusion_id}' {verdict} by data '{new_data_id}'. "
        f"Support: {support_signals}, Challenge: {challenge_signals}. "
        f"Fade: {new_fade:.1f}%, CE: {new_ce:.2f}%"
    )

    return VerificationResult(
        conclusion_id=conclusion.conclusion_id,
        verdict=verdict,
        evidence_summary=summary,
        related_experiments=related_ids[:5],
        confidence_change=confidence_change,
        details="; ".join(details_parts),
    )


def _verify_by_keywords(
    conclusion: Conclusion,
    new_ds: BatteryDataset,
    new_feats: dict,
    store: DataStore,
    engine: SearchEngine,
) -> VerificationResult:
    """Fallback verification when no evidence datasets are found."""
    scope_parts = conclusion.scope.lower() if conclusion.scope else ""

    fade = new_feats.get("fade_pct", 0)
    ce = new_feats.get("ce_mean", 100)
    retention = new_feats.get("retention_final", 100)

    details = f"Fade: {fade:.1f}%, CE: {ce:.2f}%, Retention: {retention:.1f}%"

    verdict = "inconclusive"
    if fade < 20 and ce > 99 and retention > 80:
        verdict = "supported"
    elif fade > 50 or ce < 95 or retention < 50:
        verdict = "challenged"

    return VerificationResult(
        conclusion_id=conclusion.conclusion_id,
        verdict=verdict,
        evidence_summary=f"No linked evidence datasets. Based on metrics: {details}",
        related_experiments=[],
        confidence_change="unchanged",
        details=details,
    )


def verify_all(
    new_data_id: str,
    store: DataStore | None = None,
) -> list[VerificationResult]:
    """Verify all active conclusions against new data."""
    store = store or DataStore()
    cs = ConclusionStore(store)
    active = cs.list_all(status="active")

    results = []
    for c in active:
        result = verify_conclusion(c, new_data_id, store)
        results.append(result)

        if result.verdict == "challenged":
            cs.update(
                c.conclusion_id,
                status="challenged",
                challenged_by=c.challenged_by + [new_data_id],
            )
        elif result.verdict == "supported":
            cs.update(
                c.conclusion_id,
                evidence_ids=c.evidence_ids + [new_data_id],
            )

    return results
