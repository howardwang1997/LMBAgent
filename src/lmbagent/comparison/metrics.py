"""Cross-experiment metrics: comparison table and ranking."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from lmbagent.data.models import BatteryDataset
from lmbagent.data.transformer import compute_insights


def build_comparison_table(datasets: Sequence[BatteryDataset]) -> pd.DataFrame:
    """Build a summary table comparing key metrics across experiments.

    Columns: data_id, cell_id, chemistry, cycles, initial_cap, final_cap,
             fade_pct, mean_ce, mean_ir, avg_hysteresis, retention_pct,
             plus design factor columns if available.
    """
    rows = []
    for ds in datasets:
        insights = compute_insights(ds)
        row = {
            "data_id": ds.data_id,
            "cell_id": ds.cell_id or ds.data_id,
            "chemistry": ds.chemistry,
            "cycles": ds.num_cycles,
            "initial_cap_Ah": insights.get("initial_discharge_cap"),
            "final_cap_Ah": insights.get("final_discharge_cap"),
            "fade_pct": insights.get("capacity_fade_pct"),
            "mean_ce_pct": insights.get("ce_mean"),
            "mean_ir": insights.get("ir_mean"),
            "avg_hysteresis_V": insights.get("avg_hysteresis"),
            "retention_pct": insights.get("final_retention_pct"),
        }
        if ds.experiment_design:
            flat = ds.experiment_design.to_flat_dict()
            for k in ("positive_electrode.thickness_um", "positive_electrode.porosity",
                       "negative_electrode.type", "electrolyte.salt",
                       "test.temperature_c", "test.c_rates"):
                if k in flat:
                    row[f"design.{k}"] = flat[k]
        rows.append(row)

    return pd.DataFrame(rows)


def rank_by_metric(
    datasets: Sequence[BatteryDataset],
    metric: str = "retention_pct",
    ascending: bool = True,
) -> list[dict]:
    """Rank experiments by a specific metric.

    Args:
        datasets: List of BatteryDataset.
        metric: One of 'retention_pct', 'fade_pct', 'mean_ce_pct', 'initial_cap_Ah', 'mean_ir'.
        ascending: Sort order.

    Returns:
        List of dicts with rank, cell_id, metric_value.
    """
    table = build_comparison_table(datasets)
    if metric not in table.columns:
        return []

    ranked = table.dropna(subset=[metric]).sort_values(metric, ascending=ascending)
    results = []
    for rank_idx, (_, row) in enumerate(ranked.iterrows(), 1):
        results.append({
            "rank": rank_idx,
            "cell_id": row["cell_id"],
            "data_id": row["data_id"],
            "metric": metric,
            "value": row[metric],
        })
    return results


def summarize_differences(datasets: Sequence[BatteryDataset]) -> dict:
    """Analyze key differences between experiments.

    Returns dict with:
      - differing_design_factors: list of factors that vary across experiments
      - best_retention: data_id of best retention
      - worst_fade: data_id of worst fade
    """
    if len(datasets) < 2:
        return {"differing_design_factors": [], "best_retention": None, "worst_fade": None}

    designs = [ds.experiment_design for ds in datasets if ds.experiment_design]
    differing = []
    if len(designs) >= 2:
        flat_0 = designs[0].to_flat_dict()
        for d in designs[1:]:
            diff = flat_0.keys() - set(d.to_flat_dict().keys())
            for k in set(flat_0) & set(d.to_flat_dict()):
                if flat_0[k] != d.to_flat_dict()[k]:
                    if k not in differing:
                        differing.append(k)

    table = build_comparison_table(datasets)
    best_ret = None
    worst_fade = None
    if "retention_pct" in table.columns:
        valid = table.dropna(subset=["retention_pct"])
        if not valid.empty:
            best_ret = valid.loc[valid["retention_pct"].idxmax(), "data_id"]
    if "fade_pct" in table.columns:
        valid = table.dropna(subset=["fade_pct"])
        if not valid.empty:
            worst_fade = valid.loc[valid["fade_pct"].idxmax(), "data_id"]

    return {
        "differing_design_factors": sorted(differing),
        "best_retention": best_ret,
        "worst_fade": worst_fade,
    }
