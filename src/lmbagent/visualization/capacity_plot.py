"""Capacity fade plot: capacity vs cycle number."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from lmbagent.data.models import BatteryDataset
from lmbagent.visualization.styles import COLORS, apply_style


def plot_capacity_fade(
    dataset: BatteryDataset,
    normalize: bool = False,
    output_path: str | Path | None = None,
) -> str:
    """Generate capacity fade plot.

    Args:
        dataset: BatteryDataset with cycle_summary populated.
        normalize: If True, normalize to first cycle capacity.
        output_path: Path to save the plot. Auto-generated if None.

    Returns:
        Path to the saved plot file.
    """
    apply_style()
    summary = dataset.cycle_summary

    fig, ax = plt.subplots()

    cycles = summary["cycle_index"]
    charge_cap = summary["charge_capacity"]
    discharge_cap = summary["discharge_capacity"]

    if normalize:
        first_charge = charge_cap.iloc[charge_cap.gt(0).idxmax()] if charge_cap.gt(0).any() else 1
        first_discharge = discharge_cap.iloc[discharge_cap.gt(0).idxmax()] if discharge_cap.gt(0).any() else 1
        charge_cap = charge_cap / first_charge * 100
        discharge_cap = discharge_cap / first_discharge * 100
        ylabel = "Capacity Retention (%)"
    else:
        ylabel = "Capacity (Ah)"

    ax.plot(cycles, charge_cap, "o-", color=COLORS["charge"], label="Charge", markersize=5)
    ax.plot(cycles, discharge_cap, "s-", color=COLORS["discharge"], label="Discharge", markersize=5)

    ax.set_xlabel("Cycle Number")
    ax.set_ylabel(ylabel)
    ax.set_title("Capacity vs Cycle Number")
    ax.legend()

    if output_path is None:
        output_path = Path("output") / f"capacity_fade_{dataset.data_id}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return str(output_path)
