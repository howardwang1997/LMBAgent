"""Impedance plot: internal resistance vs cycle number."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from lmbagent.data.models import BatteryDataset
from lmbagent.visualization.styles import COLORS, apply_style


def plot_impedance(
    dataset: BatteryDataset,
    output_path: str | Path | None = None,
) -> str:
    """Generate internal resistance vs cycle number plot.

    Args:
        dataset: BatteryDataset with cycle_summary populated.
        output_path: Path to save the plot.

    Returns:
        Path to the saved plot file.
    """
    apply_style()
    summary = dataset.cycle_summary

    fig, ax = plt.subplots()

    cycles = summary["cycle_index"]
    ir = summary["ir_charge"]

    ax.plot(cycles, ir, "o-", color=COLORS["impedance"], markersize=5)

    ax.set_xlabel("Cycle Number")
    ax.set_ylabel("Internal Resistance (Ohm)")
    ax.set_title("Internal Resistance vs Cycle Number")

    if output_path is None:
        output_path = Path("output") / f"impedance_{dataset.data_id}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return str(output_path)
