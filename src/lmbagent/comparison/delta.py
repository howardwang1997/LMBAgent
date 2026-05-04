"""Delta analysis: difference curves between experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np

from lmbagent.data.models import BatteryDataset
from lmbagent.visualization.styles import apply_style


def _interp_discharge_curve(
    ds: BatteryDataset,
    cycle_number: int,
    n_points: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract discharge V(Q) curve interpolated to uniform capacity grid."""
    df = ds.raw_data
    cycle_data = df[df["cycle_index"] == cycle_number]
    discharge = cycle_data[cycle_data["current"] < 0]
    if discharge.empty or "discharge_capacity" not in discharge.columns:
        return np.array([]), np.array([])

    q = discharge["discharge_capacity"].values
    v = discharge["voltage"].values
    if len(q) < 2:
        return np.array([]), np.array([])

    q_grid = np.linspace(q.min(), q.max(), n_points)
    v_interp = np.interp(q_grid, q, v)
    return q_grid, v_interp


def compute_delta_v(
    ds_a: BatteryDataset,
    ds_b: BatteryDataset,
    cycle_number: int = 0,
    n_points: int = 200,
) -> dict:
    """Compute voltage difference between two experiments at a given cycle.

    Returns dict with 'q_grid', 'v_a', 'v_b', 'delta_v' arrays.
    """
    q_a, v_a = _interp_discharge_curve(ds_a, cycle_number, n_points)
    q_b, v_b = _interp_discharge_curve(ds_b, cycle_number, n_points)

    if len(q_a) == 0 or len(q_b) == 0:
        return {"q_grid": np.array([]), "delta_v": np.array([]),
                "v_a": v_a, "v_b": v_b, "rmse_mv": float("nan")}

    q_min = max(q_a.min(), q_b.min())
    q_max = min(q_a.max(), q_b.max())
    if q_max <= q_min:
        return {"q_grid": np.array([]), "delta_v": np.array([]),
                "v_a": v_a, "v_b": v_b, "rmse_mv": float("nan")}

    q_grid = np.linspace(q_min, q_max, n_points)
    v_a_interp = np.interp(q_grid, q_a, v_a)
    v_b_interp = np.interp(q_grid, q_b, v_b)
    delta_v = v_a_interp - v_b_interp
    rmse = np.sqrt(np.mean(delta_v ** 2)) * 1000

    return {"q_grid": q_grid, "v_a": v_a_interp, "v_b": v_b_interp,
            "delta_v": delta_v, "rmse_mv": rmse}


def plot_delta_v(
    ds_a: BatteryDataset,
    ds_b: BatteryDataset,
    cycle_number: int = 0,
    output_path: str | Path | None = None,
) -> str:
    """Plot voltage difference between two experiments."""
    apply_style()
    result = compute_delta_v(ds_a, ds_b, cycle_number)

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    label_a = ds_a.cell_id or ds_a.data_id
    label_b = ds_b.cell_id or ds_b.data_id

    if len(result["q_grid"]) > 0:
        axes[0].plot(result["q_grid"], result["v_a"], label=label_a)
        axes[0].plot(result["q_grid"], result["v_b"], label=label_b)
        axes[0].set_ylabel("Voltage (V)")
        axes[0].set_title(f"Discharge Curves — Cycle {cycle_number}")
        axes[0].legend()

        axes[1].plot(result["q_grid"], result["delta_v"] * 1000)
        axes[1].axhline(0, color="gray", linestyle="--", alpha=0.5)
        axes[1].set_xlabel("Discharge Capacity (Ah)")
        axes[1].set_ylabel("ΔV (mV)")
        rmse = result["rmse_mv"]
        axes[1].set_title(f"Voltage Difference (RMSE: {rmse:.1f} mV)")

    fig.tight_layout()

    if output_path is None:
        output_path = Path("output") / f"delta_v_c{cycle_number}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def compute_capacity_heatmap(
    datasets: Sequence[BatteryDataset],
) -> tuple[np.ndarray, list[str], list[int]]:
    """Compute capacity difference matrix across datasets.

    Returns (matrix, labels, common_cycles).
    Each cell is the capacity difference at the maximum common cycle.
    """
    if not datasets:
        return np.array([]), [], []

    labels = [ds.cell_id or ds.data_id for ds in datasets]
    n = len(datasets)

    max_common = min(ds.num_cycles for ds in datasets)
    if max_common == 0:
        return np.array([]), labels, []

    matrix = np.full((n, n), np.nan)
    for i in range(n):
        cs_i = datasets[i].cycle_summary
        cap_i = cs_i[cs_i["cycle_index"] < max_common]["discharge_capacity"].mean()
        for j in range(n):
            cs_j = datasets[j].cycle_summary
            cap_j = cs_j[cs_j["cycle_index"] < max_common]["discharge_capacity"].mean()
            if cap_j > 0:
                matrix[i, j] = (cap_i - cap_j) / cap_j * 100

    return matrix, labels, list(range(max_common))
