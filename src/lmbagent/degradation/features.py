"""Feature extraction from battery cycling data for degradation analysis.

Extracts statistical features from cycle-level data, including dQ/dV peaks,
capacity fade characteristics, CE trends, voltage hysteresis evolution, and
impedance growth. These features serve as inputs for degradation mode
decomposition and similarity search.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lmbagent.data.models import BatteryDataset


def extract_discharge_curves(dataset: BatteryDataset) -> list[dict]:
    """Extract individual discharge V(Q) curves per cycle.

    Returns list of dicts with 'cycle', 'voltage', 'capacity' arrays.
    """
    df = dataset.raw_data
    if df.empty or "cycle_index" not in df.columns:
        return []

    curves = []
    for cycle_idx in sorted(df["cycle_index"].unique()):
        cycle_data = df[df["cycle_index"] == cycle_idx]
        discharge = cycle_data[cycle_data["current"] < 0].copy()

        if len(discharge) < 5:
            continue

        v = discharge["voltage"].values
        q = discharge["discharge_capacity"].values if "discharge_capacity" in discharge.columns else None

        if q is None:
            q = np.zeros(len(v))

        mask = ~(np.isnan(v) | np.isnan(q))
        v, q = v[mask], q[mask]
        if len(v) < 5:
            continue

        curves.append({"cycle": int(cycle_idx), "voltage": v, "capacity": q})

    return curves


def compute_dqdv(voltage: np.ndarray, capacity: np.ndarray,
                 sigma: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Compute dQ/dV with Gaussian smoothing.

    Args:
        voltage: Voltage array.
        capacity: Capacity array.
        sigma: Gaussian smoothing width.

    Returns:
        (voltage_sorted, dqdv) arrays.
    """
    order = np.argsort(voltage)
    v_sorted = voltage[order]
    q_sorted = capacity[order]

    dv = np.diff(v_sorted)
    dq = np.diff(q_sorted)

    valid = np.abs(dv) > 1e-6
    if not valid.any():
        return np.array([]), np.array([])

    v_mid = (v_sorted[:-1][valid] + v_sorted[1:][valid]) / 2
    dqdv = dq[valid] / dv[valid]

    from scipy.ndimage import gaussian_filter1d
    dqdv_smooth = gaussian_filter1d(dqdv, sigma=sigma)

    return v_mid, dqdv_smooth


def compute_cycle_features(dataset: BatteryDataset) -> pd.DataFrame:
    """Compute per-cycle degradation features.

    Returns DataFrame with columns:
      cycle_index, discharge_cap, charge_cap, ce, retention,
      voltage_mean, voltage_std, voltage_min, voltage_max,
      hysteresis, ir_mean, dqdv_peak_v, dqdv_peak_height,
      end_v_discharge, mid_v_discharge
    """
    df = dataset.raw_data
    cs = dataset.cycle_summary
    curves = extract_discharge_curves(dataset)

    rows = []
    for curve in curves:
        cycle = curve["cycle"]
        v = curve["voltage"]
        q = curve["capacity"]
        cycle_raw = df[df["cycle_index"] == cycle]

        row = {"cycle_index": cycle}

        row["discharge_cap"] = q.max() if len(q) > 0 else 0
        row["voltage_mean"] = np.nanmean(v)
        row["voltage_std"] = np.nanstd(v)
        row["voltage_min"] = np.nanmin(v)
        row["voltage_max"] = np.nanmax(v)

        if len(q) > 1:
            row["end_v_discharge"] = v[-1]
            mid_idx = len(v) // 2
            row["mid_v_discharge"] = v[mid_idx]

        charge = cycle_raw[cycle_raw["current"] > 0]
        if not charge.empty and "charge_capacity" in charge.columns:
            row["charge_cap"] = charge["charge_capacity"].max()

        if "charge_cap" in row and row.get("charge_cap", 0) > 0 and row["discharge_cap"] > 0:
            row["ce"] = row["discharge_cap"] / row["charge_cap"] * 100

        if not charge.empty:
            v_charge_mean = charge["voltage"].mean()
            discharge = cycle_raw[cycle_raw["current"] < 0]
            if not discharge.empty:
                v_discharge_mean = discharge["voltage"].mean()
                row["hysteresis"] = v_charge_mean - v_discharge_mean

        if "internal_resistance" in cycle_raw.columns:
            ir = cycle_raw["internal_resistance"]
            ir_nz = ir[ir > 0]
            row["ir_mean"] = ir_nz.mean() if len(ir_nz) > 0 else 0

        if len(v) > 10 and len(q) > 10:
            v_dqdv, dqdv_vals = compute_dqdv(v, q)
            if len(dqdv_vals) > 0:
                peak_idx = np.argmax(np.abs(dqdv_vals))
                row["dqdv_peak_v"] = v_dqdv[peak_idx]
                row["dqdv_peak_height"] = dqdv_vals[peak_idx]

        rows.append(row)

    result = pd.DataFrame(rows)

    if not result.empty and "discharge_cap" in result.columns:
        first_cap = result["discharge_cap"].iloc[0]
        if first_cap > 0:
            result["retention"] = result["discharge_cap"] / first_cap * 100

    return result


def compute_dataset_feature_vector(dataset: BatteryDataset) -> dict[str, float]:
    """Compute a fixed-dimension feature vector for an entire dataset.

    Used for similarity/contrast search and clustering.
    """
    cs = dataset.cycle_summary
    feats = compute_cycle_features(dataset)

    vec: dict[str, float] = {}
    vec["num_cycles"] = float(len(feats))

    if feats.empty:
        return vec

    cap = feats["discharge_cap"]
    vec["initial_cap"] = cap.iloc[0] if len(cap) > 0 else 0
    vec["final_cap"] = cap.iloc[-1] if len(cap) > 0 else 0
    vec["max_cap"] = cap.max()
    vec["min_cap"] = cap.min()

    if vec["initial_cap"] > 0 and len(cap) >= 2:
        fade = (1 - vec["final_cap"] / vec["initial_cap"]) * 100
        vec["fade_pct"] = fade
        n = len(cap) - 1
        vec["fade_rate"] = (cap.iloc[0] - cap.iloc[-1]) / n * 1000 if n > 0 else 0
    else:
        vec["fade_pct"] = 0
        vec["fade_rate"] = 0

    if "ce" in feats.columns:
        ce = feats["ce"].dropna()
        if len(ce) > 0:
            vec["ce_mean"] = ce.mean()
            vec["ce_std"] = ce.std() if len(ce) > 1 else 0
            vec["ce_trend"] = ce.iloc[-1] - ce.iloc[0] if len(ce) >= 2 else 0

    if "hysteresis" in feats.columns:
        hyst = feats["hysteresis"].dropna()
        if len(hyst) > 0:
            vec["hyst_mean"] = hyst.mean()
            vec["hyst_trend"] = hyst.iloc[-1] - hyst.iloc[0] if len(hyst) >= 2 else 0

    if "ir_mean" in feats.columns:
        ir = feats["ir_mean"].dropna()
        if len(ir) > 0:
            vec["ir_mean"] = ir.mean()
            vec["ir_trend"] = ir.iloc[-1] - ir.iloc[0] if len(ir) >= 2 else 0

    if "dqdv_peak_v" in feats.columns:
        peaks = feats["dqdv_peak_v"].dropna()
        if len(peaks) >= 2:
            vec["dqdv_peak_shift"] = peaks.iloc[-1] - peaks.iloc[0]

    if "dqdv_peak_height" in feats.columns:
        heights = feats["dqdv_peak_height"].dropna()
        if len(heights) >= 2:
            vec["dqdv_peak_decay"] = heights.iloc[-1] / (heights.iloc[0] + 1e-12)

    vec["retention_final"] = feats["retention"].iloc[-1] if "retention" in feats.columns and len(feats) > 0 else 0

    return vec
