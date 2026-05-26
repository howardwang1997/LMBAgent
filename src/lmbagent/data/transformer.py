"""Data transformation: compute cycle summaries from raw data."""

from __future__ import annotations

import pandas as pd

from lmbagent.data.models import BatteryDataset


def compute_cycle_summary(dataset: BatteryDataset) -> pd.DataFrame:
    """Compute per-cycle summary metrics from raw data.

    Returns a DataFrame with one row per cycle containing capacity,
    efficiency, and resistance metrics.
    """
    df = dataset.raw_data
    if df.empty or "cycle_index" not in df.columns:
        return pd.DataFrame()

    groups = df.groupby("cycle_index")

    summary_rows = []
    first_discharge_cap = None

    for cycle_idx, group in groups:
        charge_cap = group["charge_capacity"].max() if "charge_capacity" in group else 0
        discharge_cap = group["discharge_capacity"].max() if "discharge_capacity" in group else 0

        # Coulombic efficiency
        ce = (discharge_cap / charge_cap * 100) if charge_cap > 0 else 0.0

        # Energy
        charge_energy = group["charge_energy"].max() if "charge_energy" in group else 0
        discharge_energy = group["discharge_energy"].max() if "discharge_energy" in group else 0
        energy_eff = (discharge_energy / charge_energy * 100) if charge_energy > 0 else 0.0

        # Internal resistance (use mean of non-zero values)
        ir_val = 0.0
        if "internal_resistance" in group:
            ir_nonzero = group["internal_resistance"][group["internal_resistance"] > 0]
            if len(ir_nonzero) > 0:
                ir_val = ir_nonzero.mean()

        # Capacity retention (relative to first cycle with discharge)
        if first_discharge_cap is None and discharge_cap > 0:
            first_discharge_cap = discharge_cap
        retention = (discharge_cap / first_discharge_cap * 100) if first_discharge_cap and first_discharge_cap > 0 else 0.0

        # End voltages: last voltage in charge steps (current > 0) and discharge steps (current < 0)
        charge_mask = group["current"] > 0
        discharge_mask = group["current"] < 0
        end_v_charge = group.loc[charge_mask, "voltage"].iloc[-1] if charge_mask.any() else None
        end_v_discharge = group.loc[discharge_mask, "voltage"].iloc[-1] if discharge_mask.any() else None

        summary_rows.append({
            "cycle_index": cycle_idx,
            "charge_capacity": charge_cap,
            "discharge_capacity": discharge_cap,
            "coulombic_efficiency": ce,
            "charge_energy": charge_energy,
            "discharge_energy": discharge_energy,
            "energy_efficiency": energy_eff,
            "ir_charge": ir_val,
            "ir_discharge": ir_val,
            "capacity_retention": retention,
            "end_voltage_charge": end_v_charge,
            "end_voltage_discharge": end_v_discharge,
        })

    return pd.DataFrame(summary_rows)


def add_cycle_summary(dataset: BatteryDataset) -> BatteryDataset:
    """Compute and attach cycle summary to dataset. Returns the same dataset."""
    dataset.cycle_summary = compute_cycle_summary(dataset)
    return dataset


def split_by_cycles(
    dataset: BatteryDataset,
    max_cycles_per_dataset: int = 1,
) -> list[BatteryDataset]:
    """Split a BatteryDataset into multiple datasets by independent cycle groups.

    Args:
        dataset: Source dataset with all cycles.
        max_cycles_per_dataset: Max cycles per split dataset.
            1 = each cycle becomes its own dataset.
            N = groups of N cycles per dataset.
            0 or negative = no splitting (returns [dataset]).

    Returns:
        List of BatteryDataset, one per cycle group.
    """
    if max_cycles_per_dataset <= 0:
        return [dataset]

    df = dataset.raw_data
    if df.empty or "cycle_index" not in df.columns:
        return [dataset]

    unique_cycles = sorted(df["cycle_index"].unique())
    if len(unique_cycles) <= max_cycles_per_dataset:
        return [dataset]

    import math
    n_groups = math.ceil(len(unique_cycles) / max_cycles_per_dataset)
    results = []

    for g in range(n_groups):
        start = g * max_cycles_per_dataset
        end = min(start + max_cycles_per_dataset, len(unique_cycles))
        group_cycles = unique_cycles[start:end]

        mask = df["cycle_index"].isin(group_cycles)
        sub_df = df[mask].copy()

        if sub_df.empty:
            continue

        sub_df["data_point"] = range(len(sub_df))

        suffix = f"_c{group_cycles[0]}-{group_cycles[-1]}" if len(group_cycles) > 1 else f"_c{group_cycles[0]}"
        sub_id = dataset.data_id + suffix

        sub_ds = BatteryDataset(
            data_id=sub_id,
            source_file=dataset.source_file,
            cell_id=dataset.cell_id,
            test_name=dataset.test_name,
            start_datetime=dataset.start_datetime,
            raw_data=sub_df,
            metadata={
                **(dataset.metadata or {}),
                "split_from": dataset.data_id,
                "cycle_range": [int(group_cycles[0]), int(group_cycles[-1])],
                "num_cycles_in_group": len(group_cycles),
            },
            experiment_design=dataset.experiment_design,
        )
        sub_ds = add_cycle_summary(sub_ds)
        results.append(sub_ds)

    return results


def compute_insights(dataset: BatteryDataset) -> dict:
    """Compute cross-cycle analytical insights from dataset.

    Returns a dict of computed metrics for report generation.
    """
    insights: dict = {}
    df = dataset.raw_data
    cs = dataset.cycle_summary

    if cs.empty:
        return insights

    # --- Basic stats ---
    insights["total_cycles"] = len(cs)
    insights["total_data_points"] = len(df)
    if "test_time" in df.columns:
        total_time_s = df["test_time"].max() - df["test_time"].min()
        insights["total_test_time_h"] = round(total_time_s / 3600, 2)

    # --- Capacity Analysis ---
    valid = cs[cs["discharge_capacity"] > 0]
    if len(valid) >= 1:
        insights["initial_charge_cap"] = round(valid.iloc[0]["charge_capacity"], 6)
        insights["initial_discharge_cap"] = round(valid.iloc[0]["discharge_capacity"], 6)
        insights["final_discharge_cap"] = round(valid.iloc[-1]["discharge_capacity"], 6)
        insights["max_discharge_cap"] = round(valid["discharge_capacity"].max(), 6)
        insights["max_cap_cycle"] = int(valid.loc[valid["discharge_capacity"].idxmax(), "cycle_index"])
        insights["min_discharge_cap"] = round(valid["discharge_capacity"].min(), 6)
        insights["min_cap_cycle"] = int(valid.loc[valid["discharge_capacity"].idxmin(), "cycle_index"])

        if len(valid) >= 2:
            cap_first = valid.iloc[0]["discharge_capacity"]
            cap_last = valid.iloc[-1]["discharge_capacity"]
            n_cycles = valid.iloc[-1]["cycle_index"] - valid.iloc[0]["cycle_index"]
            if cap_first > 0 and n_cycles > 0:
                insights["capacity_fade_pct"] = round((1 - cap_last / cap_first) * 100, 2)
                insights["fade_rate_per_cycle"] = round(
                    (cap_first - cap_last) / n_cycles * 1000, 4  # mAh/cycle
                )
            insights["final_retention_pct"] = round(cap_last / cap_first * 100, 2) if cap_first > 0 else 0

    # --- Coulombic Efficiency Analysis ---
    ce_valid = cs[(cs["coulombic_efficiency"] > 0) & (cs["coulombic_efficiency"] <= 200)]
    if len(ce_valid) >= 1:
        insights["ce_mean"] = round(ce_valid["coulombic_efficiency"].mean(), 2)
        insights["ce_std"] = round(ce_valid["coulombic_efficiency"].std(), 2) if len(ce_valid) > 1 else 0.0
        insights["ce_min"] = round(ce_valid["coulombic_efficiency"].min(), 2)
        insights["ce_min_cycle"] = int(ce_valid.loc[ce_valid["coulombic_efficiency"].idxmin(), "cycle_index"])
        insights["ce_max"] = round(ce_valid["coulombic_efficiency"].max(), 2)
        insights["ce_max_cycle"] = int(ce_valid.loc[ce_valid["coulombic_efficiency"].idxmax(), "cycle_index"])

    # --- Energy Efficiency ---
    ee_valid = cs[(cs["energy_efficiency"] > 0) & (cs["energy_efficiency"] <= 200)]
    if len(ee_valid) >= 1:
        insights["ee_mean"] = round(ee_valid["energy_efficiency"].mean(), 2)
        insights["ee_min"] = round(ee_valid["energy_efficiency"].min(), 2)
        insights["ee_max"] = round(ee_valid["energy_efficiency"].max(), 2)

    # --- Voltage Analysis ---
    if "voltage" in df.columns:
        insights["voltage_min"] = round(df["voltage"].min(), 4)
        insights["voltage_max"] = round(df["voltage"].max(), 4)
        insights["voltage_range"] = round(df["voltage"].max() - df["voltage"].min(), 4)

        # Voltage hysteresis per cycle (avg charge voltage - avg discharge voltage)
        hysteresis_list = []
        for cycle_idx, group in df.groupby("cycle_index"):
            charge_v = group.loc[group["current"] > 0, "voltage"]
            discharge_v = group.loc[group["current"] < 0, "voltage"]
            if len(charge_v) > 0 and len(discharge_v) > 0:
                hysteresis_list.append({
                    "cycle": int(cycle_idx),
                    "hysteresis": round(charge_v.mean() - discharge_v.mean(), 4),
                })
        if hysteresis_list:
            insights["voltage_hysteresis"] = hysteresis_list
            insights["avg_hysteresis"] = round(
                sum(h["hysteresis"] for h in hysteresis_list) / len(hysteresis_list), 4
            )

    # --- End Voltage Analysis ---
    ev_charge = cs["end_voltage_charge"].dropna()
    ev_discharge = cs["end_voltage_discharge"].dropna()
    if len(ev_charge) > 0:
        insights["avg_end_v_charge"] = round(ev_charge.mean(), 4)
    if len(ev_discharge) > 0:
        insights["avg_end_v_discharge"] = round(ev_discharge.mean(), 4)

    # --- Internal Resistance ---
    ir_valid = cs[cs["ir_charge"] > 0]
    if len(ir_valid) >= 1:
        insights["ir_mean"] = round(ir_valid["ir_charge"].mean(), 4)
        insights["ir_trend"] = "increasing" if len(ir_valid) >= 2 and ir_valid["ir_charge"].iloc[-1] > ir_valid["ir_charge"].iloc[0] else "stable"

    # --- Health Assessment ---
    assessments = []
    if "capacity_fade_pct" in insights:
        fade = insights["capacity_fade_pct"]
        if fade < 5:
            assessments.append("Excellent capacity retention — minimal degradation observed.")
        elif fade < 15:
            assessments.append("Moderate capacity fade — cell is aging within normal parameters.")
        else:
            assessments.append("Significant capacity fade — cell may be approaching end of life.")

    if "ce_mean" in insights:
        ce = insights["ce_mean"]
        if ce > 99.5:
            assessments.append("Coulombic efficiency is excellent, indicating minimal side reactions.")
        elif ce > 98:
            assessments.append("Coulombic efficiency is good but some irreversible capacity loss per cycle.")
        else:
            assessments.append("Low coulombic efficiency suggests significant parasitic reactions or lithium loss.")

    if "avg_hysteresis" in insights:
        h = insights["avg_hysteresis"]
        if h < 0.1:
            assessments.append("Low voltage hysteresis indicates good kinetics and low polarization.")
        elif h < 0.3:
            assessments.append("Moderate voltage hysteresis — some polarization losses present.")
        else:
            assessments.append("High voltage hysteresis suggests significant internal resistance or slow kinetics.")

    insights["health_assessments"] = assessments

    return insights
