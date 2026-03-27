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
