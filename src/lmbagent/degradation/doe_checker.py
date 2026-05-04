"""DOE completeness checker and experiment recommendation engine.

Analyzes the design space coverage of existing experiments and recommends
supplementary experiments to fill gaps. Uses design factor variance analysis
to identify which factors have been tested and which combinations are missing.
"""

from __future__ import annotations

from itertools import combinations
from typing import Sequence

import numpy as np
import pandas as pd

from lmbagent.data.models import BatteryDataset
from lmbagent.data.schema import ExperimentDesign
from lmbagent.degradation.decomposition import decompose_degradation_modes


NUMERIC_DESIGN_FIELDS = [
    "positive_electrode.thickness_um",
    "positive_electrode.porosity",
    "positive_electrode.particle_radius_um",
    "positive_electrode.loading_mg_cm2",
    "negative_electrode.thickness_um",
    "electrolyte.concentration_mol_l",
    "separator.thickness_um",
    "formation.temperature_c",
    "test.temperature_c",
]

CATEGORICAL_DESIGN_FIELDS = [
    "chemistry",
    "form_factor",
    "positive_electrode.active_material",
    "negative_electrode.type",
    "electrolyte.salt",
    "electrolyte.solvent",
]


def _collect_design_factors(datasets: Sequence[BatteryDataset]) -> pd.DataFrame:
    """Collect all design factors from datasets into a flat table."""
    rows = []
    for ds in datasets:
        if ds.experiment_design is None:
            rows.append({"data_id": ds.data_id, "cell_id": ds.cell_id or ds.data_id})
            continue
        flat = {"data_id": ds.data_id, "cell_id": ds.cell_id or ds.data_id}
        flat.update(ds.experiment_design.to_flat_dict())
        rows.append(flat)
    return pd.DataFrame(rows)


def check_doe_coverage(datasets: Sequence[BatteryDataset]) -> dict:
    """Analyze DOE completeness.

    Returns dict with:
      'n_experiments': int
      'factors_tested': list of field names with variation
      'factors_constant': list of field names that are constant or missing
      'missing_combinations': list of missing factor combinations
      'coverage_score': float 0-1 (fraction of potential design space explored)
      'recommendations': list of suggested experiments
    """
    table = _collect_design_factors(datasets)
    n = len(datasets)

    if n == 0:
        return {
            "n_experiments": 0, "factors_tested": [], "factors_constant": [],
            "missing_combinations": [], "coverage_score": 0.0, "recommendations": [],
        }

    tested = []
    constant = []

    for field in NUMERIC_DESIGN_FIELDS + CATEGORICAL_DESIGN_FIELDS:
        if field not in table.columns:
            constant.append(field)
            continue
        vals = table[field].dropna()
        if len(vals) == 0:
            constant.append(field)
            continue
        unique = vals.nunique()
        if unique > 1:
            tested.append(field)
        else:
            constant.append(field)

    missing_combos = []
    if len(tested) >= 2:
        for f1, f2 in combinations(tested, 2):
            v1 = table[f1].dropna().unique()
            v2 = table[f2].dropna().unique()
            existing = set(zip(table[f1].fillna("__NA__"), table[f2].fillna("__NA__")))
            for x1 in v1:
                for x2 in v2:
                    if (x1, x2) not in existing:
                        missing_combos.append({f1: x1, f2: x2})

    n_potential = 0
    n_covered = 0
    for field in tested:
        n_unique = table[field].dropna().nunique()
        n_potential += n_unique * 2
        n_covered += n_unique
    coverage = n_covered / max(n_potential, 1)

    recs = _generate_recommendations(table, tested, missing_combos)

    return {
        "n_experiments": n,
        "factors_tested": tested,
        "factors_constant": constant,
        "missing_combinations": missing_combos[:20],
        "coverage_score": round(coverage, 3),
        "recommendations": recs,
    }


def _generate_recommendations(
    table: pd.DataFrame,
    tested: list[str],
    missing: list[dict],
) -> list[dict]:
    """Generate experiment recommendations to fill DOE gaps."""
    recs = []

    for combo in missing[:5]:
        recs.append({
            "type": "missing_combination",
            "description": f"Test combination: {combo}",
            "priority": "high",
        })

    for field in tested:
        if field in NUMERIC_DESIGN_FIELDS:
            vals = table[field].dropna()
            if len(vals) > 0:
                v_min, v_max = vals.min(), vals.max()
                v_range = v_max - v_min
                if v_range > 0:
                    mid = (v_min + v_max) / 2
                    has_midpoint = any(abs(v - mid) < v_range * 0.2 for v in vals)
                    if not has_midpoint:
                        recs.append({
                            "type": "add_midpoint",
                            "description": f"Add midpoint experiment for {field}: ~{mid:.2f}",
                            "priority": "medium",
                        })

    for field in CATEGORICAL_DESIGN_FIELDS:
        if field not in tested and field in table.columns:
            vals = table[field].dropna()
            if len(vals) > 0:
                recs.append({
                    "type": "add_factor_variation",
                    "description": f"Vary {field} (currently constant: {vals.iloc[0]})",
                    "priority": "medium",
                })

    for field in NUMERIC_DESIGN_FIELDS:
        if field not in tested and field not in table.columns:
            recs.append({
                "type": "add_factor",
                "description": f"Include {field} in experimental design",
                "priority": "low",
            })

    return recs[:10]


def analyze_design_impact(
    datasets: Sequence[BatteryDataset],
    focus_factor: str | None = None,
) -> dict:
    """Analyze how design factors correlate with degradation outcomes.

    Args:
        datasets: Experiments with design metadata.
        focus_factor: Specific design factor to analyze (None = analyze all).

    Returns:
        Dict with factor → degradation correlations.
    """
    table = _collect_design_factors(datasets)
    if len(table) < 2:
        return {"error": "Need at least 2 experiments"}

    outcomes = []
    for ds in datasets:
        result = decompose_degradation_modes(ds)
        dominant = result.get("dominant_mode", "unknown")
        contributions = result.get("mode_contributions", {})
        fade = 0
        if not ds.cycle_summary.empty:
            cs = ds.cycle_summary
            valid = cs[cs["discharge_capacity"] > 0]
            if len(valid) >= 2:
                fade = (1 - valid.iloc[-1]["discharge_capacity"] / valid.iloc[0]["discharge_capacity"]) * 100
        outcomes.append({
            "data_id": ds.data_id,
            "dominant_mode": dominant,
            "fade_pct": fade,
            **contributions,
        })

    outcome_df = pd.DataFrame(outcomes)
    merged = table.merge(outcome_df, on="data_id", how="left")

    factors_to_check = [focus_factor] if focus_factor else [
        f for f in NUMERIC_DESIGN_FIELDS + CATEGORICAL_DESIGN_FIELDS
        if f in merged.columns and merged[f].nunique() > 1
    ]

    results = {}
    for factor in factors_to_check:
        if factor not in merged.columns:
            continue
        vals = merged[factor].dropna()
        if vals.nunique() < 2:
            continue

        factor_result = {"factor": factor}

        try:
            numeric_vals = pd.to_numeric(vals, errors="coerce")
            if numeric_vals.notna().sum() > len(vals) * 0.5:
                fade_vals = merged.loc[numeric_vals.index, "fade_pct"]
                if len(fade_vals.dropna()) >= 2:
                    r = np.corrcoef(numeric_vals.dropna(), fade_vals.dropna())[0, 1]
                    factor_result["correlation_with_fade"] = round(float(r), 3)
                    factor_result["interpretation"] = (
                        f"Positive correlation (r={r:.2f}): higher {factor} → more fade"
                        if r > 0.2 else
                        f"Negative correlation (r={r:.2f}): higher {factor} → less fade"
                        if r < -0.2 else
                        f"Weak correlation (r={r:.2f}): {factor} has limited effect on fade"
                    )
        except Exception:
            pass

        groups = {}
        for val in vals.unique():
            mask = merged[factor] == val
            group_fade = merged.loc[mask, "fade_pct"].dropna()
            if len(group_fade) > 0:
                groups[str(val)] = {"mean_fade": round(float(group_fade.mean()), 2),
                                   "n": int(len(group_fade))}
        factor_result["groups"] = groups

        dominant_modes = merged.loc[merged[factor].isin(vals.unique()), "dominant_mode"].value_counts()
        factor_result["dominant_modes_by_factor"] = dominant_modes.to_dict()

        results[factor] = factor_result

    return {
        "n_experiments": len(datasets),
        "factors_analyzed": list(results.keys()),
        "factor_analysis": results,
    }
