"""Voltage profile plot: voltage vs capacity for selected cycles."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np

from lmbagent.data.models import BatteryDataset
from lmbagent.visualization.styles import apply_style


def plot_voltage_curves(
    dataset: BatteryDataset,
    cycle_numbers: list[int] | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate voltage vs capacity curves for selected cycles.

    Args:
        dataset: BatteryDataset with raw_data.
        cycle_numbers: Cycles to plot. Defaults to all available.
        output_path: Path to save the plot.

    Returns:
        Path to the saved plot file.
    """
    apply_style()
    df = dataset.raw_data

    if cycle_numbers is None:
        cycle_numbers = sorted(df["cycle_index"].unique().tolist())

    fig, ax = plt.subplots()
    cmap = plt.get_cmap("viridis", len(cycle_numbers))

    for i, cycle in enumerate(cycle_numbers):
        cycle_data = df[df["cycle_index"] == cycle]
        if cycle_data.empty:
            continue

        color = cmap(i)

        # Charge: current > 0
        charge = cycle_data[cycle_data["current"] > 0]
        if not charge.empty:
            ax.plot(charge["charge_capacity"], charge["voltage"],
                    color=color, label=f"Cycle {cycle}")

        # Discharge: current < 0
        discharge = cycle_data[cycle_data["current"] < 0]
        if not discharge.empty:
            ax.plot(discharge["discharge_capacity"], discharge["voltage"],
                    color=color, linestyle="--")

    ax.set_xlabel("Capacity (Ah)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("Voltage vs Capacity")

    if output_path is None:
        output_path = Path("output") / f"voltage_curves_{dataset.data_id}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return str(output_path)
