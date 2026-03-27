"""Coulombic efficiency plot: CE vs cycle number."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from lmbagent.data.models import BatteryDataset
from lmbagent.visualization.styles import COLORS, apply_style


def plot_coulombic_efficiency(
    dataset: BatteryDataset,
    y_range: tuple[float, float] | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate coulombic efficiency plot.

    Args:
        dataset: BatteryDataset with cycle_summary populated.
        y_range: Optional (min, max) for y-axis to zoom in.
        output_path: Path to save the plot.

    Returns:
        Path to the saved plot file.
    """
    apply_style()
    summary = dataset.cycle_summary

    fig, ax = plt.subplots()

    cycles = summary["cycle_index"]
    ce = summary["coulombic_efficiency"]

    ax.plot(cycles, ce, "o-", color=COLORS["efficiency"], markersize=5)

    ax.set_xlabel("Cycle Number")
    ax.set_ylabel("Coulombic Efficiency (%)")
    ax.set_title("Coulombic Efficiency vs Cycle Number")

    if y_range:
        ax.set_ylim(y_range)

    if output_path is None:
        output_path = Path("output") / f"coulombic_efficiency_{dataset.data_id}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return str(output_path)
