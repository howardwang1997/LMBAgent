"""DOE completeness checker and experiment recommendation engine.

Analyzes the design space coverage of existing experiments and recommends
supplementary experiments to fill gaps.

Two modes:
1. Generic mode: uses ExperimentDesign fields (positive_electrode.thickness_um, etc.)
2. Template mode: uses 电芯挂测表 template fields (电解液, 隔膜, 测试温度, etc.)

Template mode is activated when CellTestRecord data is available.
"""

from __future__ import annotations

from itertools import combinations
from typing import Sequence

import numpy as np
import pandas as pd

from lmbagent.data.models import BatteryDataset
from lmbagent.data.schema import ExperimentDesign


GENERIC_NUMERIC_FIELDS = [
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

GENERIC_CATEGORICAL_FIELDS = [
    "chemistry",
    "form_factor",
    "positive_electrode.active_material",
    "negative_electrode.type",
    "electrolyte.salt",
    "electrolyte.solvent",
]


def _collect_design_factors(datasets: Sequence[BatteryDataset]) -> pd.DataFrame:
    rows = []
    for ds in datasets:
        if ds.experiment_design is None:
            rows.append({"data_id": ds.data_id, "cell_id": ds.cell_id or ds.data_id})
            continue
        flat = {"data_id": ds.data_id, "cell_id": ds.cell_id or ds.data_id}
        flat.update(ds.experiment_design.to_flat_dict())
        rows.append(flat)
    return pd.DataFrame(rows)


def _detect_template_mode(table: pd.DataFrame) -> bool:
    """Check if the table contains template-based design factors."""
    template_indicators = [
        "电解液", "隔膜", "测试温度_C", "充电电流_C", "上限电压_V",
    ]
    return sum(1 for c in template_indicators if c in table.columns) >= 3


def _get_template_factors() -> tuple[list[str], list[str]]:
    from lmbagent.data.cell_test_template import DOE_CATEGORICAL_FACTORS, DOE_NUMERIC_FACTORS
    return DOE_CATEGORICAL_FACTORS, DOE_NUMERIC_FACTORS


def check_doe_coverage(datasets: Sequence[BatteryDataset]) -> dict:
    """Analyze DOE completeness.

    Auto-detects whether to use template-based or generic design factors.

    Returns dict with:
      'n_experiments': int
      'mode': 'template' | 'generic'
      'factors_tested': list of field names with variation
      'factors_constant': list of field names that are constant or missing
      'missing_combinations': list of missing factor combinations
      'coverage_score': float 0-1
      'recommendations': list of suggested experiments
      'factor_summary': dict factor -> {values, n_unique}
    """
    table = _collect_design_factors(datasets)
    n = len(datasets)

    if n == 0:
        return {
            "n_experiments": 0, "mode": "unknown",
            "factors_tested": [], "factors_constant": [],
            "missing_combinations": [], "coverage_score": 0.0,
            "recommendations": [], "factor_summary": {},
        }

    is_template = _detect_template_mode(table)

    if is_template:
        cat_fields, num_fields = _get_template_factors()
        mode = "template"
    else:
        cat_fields = GENERIC_CATEGORICAL_FIELDS
        num_fields = GENERIC_NUMERIC_FIELDS
        mode = "generic"

    all_fields = cat_fields + num_fields

    tested = []
    constant = []
    factor_summary = {}

    for field in all_fields:
        if field not in table.columns:
            constant.append(field)
            continue
        vals = table[field].dropna()
        if len(vals) == 0:
            constant.append(field)
            continue
        unique_vals = vals.unique()
        n_unique = len(unique_vals)
        factor_summary[field] = {
            "n_unique": int(n_unique),
            "values": [str(v) for v in unique_vals[:10]],
        }
        if n_unique > 1:
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

    recs = _generate_recommendations(table, tested, missing_combos, cat_fields, num_fields)

    return {
        "n_experiments": n,
        "mode": mode,
        "factors_tested": tested,
        "factors_constant": constant,
        "missing_combinations": missing_combos[:30],
        "coverage_score": round(coverage, 3),
        "recommendations": recs,
        "factor_summary": factor_summary,
    }


def _generate_recommendations(
    table: pd.DataFrame,
    tested: list[str],
    missing: list[dict],
    cat_fields: list[str],
    num_fields: list[str],
) -> list[dict]:
    recs = []

    for combo in missing[:8]:
        desc_parts = []
        for k, v in combo.items():
            desc_parts.append(f"{k}={v}")
        recs.append({
            "type": "missing_combination",
            "description": f"缺少组合: {', '.join(desc_parts)}",
            "factors": combo,
            "priority": "high",
        })

    for field in tested:
        if field in num_fields:
            vals = table[field].dropna()
            if len(vals) > 0:
                try:
                    numeric_vals = pd.to_numeric(vals, errors="coerce").dropna()
                    if len(numeric_vals) > 0:
                        v_min, v_max = numeric_vals.min(), numeric_vals.max()
                        v_range = v_max - v_min
                        if v_range > 0:
                            mid = (v_min + v_max) / 2
                            has_midpoint = any(abs(v - mid) < v_range * 0.2 for v in numeric_vals)
                            if not has_midpoint:
                                recs.append({
                                    "type": "add_midpoint",
                                    "description": f"补充 {field} 中间点: ~{mid:.3f}",
                                    "priority": "medium",
                                })
                except Exception:
                    pass

    for field in cat_fields:
        if field not in tested and field in table.columns:
            vals = table[field].dropna()
            if len(vals) > 0:
                recs.append({
                    "type": "add_factor_variation",
                    "description": f"变化 {field} (当前固定: {vals.iloc[0]})",
                    "priority": "medium",
                })

    for field in num_fields:
        if field not in tested and field not in table.columns:
            recs.append({
                "type": "add_factor",
                "description": f"加入实验设计因子: {field}",
                "priority": "low",
            })

    return recs[:15]


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
        fade = 0
        if not ds.cycle_summary.empty:
            cs = ds.cycle_summary
            valid = cs[cs["discharge_capacity"] > 0]
            if len(valid) >= 2:
                fade = (1 - valid.iloc[-1]["discharge_capacity"] / valid.iloc[0]["discharge_capacity"]) * 100
        outcomes.append({
            "data_id": ds.data_id,
            "fade_pct": fade,
        })

    outcome_df = pd.DataFrame(outcomes)
    merged = table.merge(outcome_df, on="data_id", how="left")

    is_template = _detect_template_mode(table)
    if is_template:
        cat_fields, num_fields = _get_template_factors()
    else:
        cat_fields = GENERIC_CATEGORICAL_FIELDS
        num_fields = GENERIC_NUMERIC_FIELDS

    factors_to_check = [focus_factor] if focus_factor else [
        f for f in num_fields + cat_fields
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
                valid_mask = numeric_vals.notna() & fade_vals.notna()
                if valid_mask.sum() >= 2:
                    r = np.corrcoef(numeric_vals[valid_mask], fade_vals[valid_mask])[0, 1]
                    factor_result["correlation_with_fade"] = round(float(r), 3)
                    if r > 0.2:
                        factor_result["interpretation"] = f"正相关 (r={r:.2f}): {factor} 越高 → 衰减越快"
                    elif r < -0.2:
                        factor_result["interpretation"] = f"负相关 (r={r:.2f}): {factor} 越高 → 衰减越慢"
                    else:
                        factor_result["interpretation"] = f"弱相关 (r={r:.2f}): {factor} 对衰减影响有限"
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

        results[factor] = factor_result

    return {
        "n_experiments": len(datasets),
        "factors_analyzed": list(results.keys()),
        "factor_analysis": results,
    }


def check_doe_from_template(
    template_records: list,
    datasets: Sequence[BatteryDataset],
) -> dict:
    """DOE analysis using template records directly.

    Merges template design info with loaded datasets and runs DOE check.

    Args:
        template_records: List of CellTestRecord from load_cell_test_template().
        datasets: Loaded BatteryDataset objects.

    Returns:
        DOE coverage result with template-specific factors.
    """
    from lmbagent.data.cell_test_template import CellTestRecord

    record_map = {}
    for rec in template_records:
        record_map[rec.cell_id] = rec

    doe_rows = []
    for ds in datasets:
        cell_id = ds.cell_id or ds.data_id
        row = {"data_id": ds.data_id, "cell_id": cell_id}

        if ds.experiment_design:
            row.update(ds.experiment_design.to_flat_dict())

        matched_rec = record_map.get(cell_id)
        if matched_rec:
            row.update(matched_rec.to_doe_dict())

        doe_rows.append(row)

    if not doe_rows:
        return {
            "n_experiments": 0, "mode": "template",
            "factors_tested": [], "factors_constant": [],
            "missing_combinations": [], "coverage_score": 0.0,
            "recommendations": [], "factor_summary": {},
        }

    table = pd.DataFrame(doe_rows)
    n = len(table)
    cat_fields, num_fields = _get_template_factors()
    all_fields = cat_fields + num_fields

    tested = []
    constant = []
    factor_summary = {}

    for field in all_fields:
        if field not in table.columns:
            constant.append(field)
            continue
        vals = table[field].dropna()
        if len(vals) == 0:
            constant.append(field)
            continue
        unique_vals = vals.unique()
        n_unique = len(unique_vals)
        factor_summary[field] = {
            "n_unique": int(n_unique),
            "values": [str(v) for v in unique_vals[:10]],
        }
        if n_unique > 1:
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

    recs = _generate_recommendations(table, tested, missing_combos, cat_fields, num_fields)

    return {
        "n_experiments": n,
        "mode": "template",
        "factors_tested": tested,
        "factors_constant": constant,
        "missing_combinations": missing_combos[:30],
        "coverage_score": round(coverage, 3),
        "recommendations": recs,
        "factor_summary": factor_summary,
    }
