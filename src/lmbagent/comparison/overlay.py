"""Overlay comparison plots for multiple experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import matplotlib.cm as cm

from lmbagent.data.models import BatteryDataset
from lmbagent.visualization.styles import apply_style

PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def _label(ds: BatteryDataset) -> str:
    if ds.cell_id:
        return ds.cell_id
    return ds.data_id


def overlay_capacity_fade(
    datasets: Sequence[BatteryDataset],
    normalize: bool = False,
    output_path: str | Path | None = None,
) -> str:
    apply_style()
    fig, ax = plt.subplots(figsize=(10, 6))

    for i, ds in enumerate(datasets):
        cs = ds.cycle_summary
        if cs.empty:
            continue
        color = PALETTE[i % len(PALETTE)]
        label = _label(ds)
        cycles = cs["cycle_index"]
        discharge = cs["discharge_capacity"]
        if normalize:
            first = discharge.iloc[discharge.gt(0).idxmax()] if discharge.gt(0).any() else 1
            discharge = discharge / first * 100
        ax.plot(cycles, discharge, "o-", color=color, label=label, markersize=4, linewidth=1.5)

    ax.set_xlabel("Cycle Number")
    ax.set_ylabel("Capacity Retention (%)" if normalize else "Discharge Capacity (Ah)")
    ax.set_title("Capacity Fade Comparison")
    ax.legend()
    fig.tight_layout()

    if output_path is None:
        output_path = Path("output") / "overlay_capacity.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def overlay_coulombic_efficiency(
    datasets: Sequence[BatteryDataset],
    y_range: tuple[float, float] | None = None,
    output_path: str | Path | None = None,
) -> str:
    apply_style()
    fig, ax = plt.subplots(figsize=(10, 6))

    for i, ds in enumerate(datasets):
        cs = ds.cycle_summary
        if cs.empty:
            continue
        color = PALETTE[i % len(PALETTE)]
        label = _label(ds)
        valid = cs[cs["coulombic_efficiency"] > 0]
        ax.plot(valid["cycle_index"], valid["coulombic_efficiency"],
                "o-", color=color, label=label, markersize=4, linewidth=1.5)

    ax.set_xlabel("Cycle Number")
    ax.set_ylabel("Coulombic Efficiency (%)")
    ax.set_title("Coulombic Efficiency Comparison")
    if y_range:
        ax.set_ylim(y_range)
    ax.legend()
    fig.tight_layout()

    if output_path is None:
        output_path = Path("output") / "overlay_ce.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def overlay_voltage_curves(
    datasets: Sequence[BatteryDataset],
    cycle_number: int = 0,
    output_path: str | Path | None = None,
) -> str:
    apply_style()
    fig, ax = plt.subplots(figsize=(10, 6))

    for i, ds in enumerate(datasets):
        df = ds.raw_data
        cycle_data = df[df["cycle_index"] == cycle_number]
        if cycle_data.empty:
            continue
        color = PALETTE[i % len(PALETTE)]
        label = _label(ds)

        discharge = cycle_data[cycle_data["current"] < 0]
        if not discharge.empty and "discharge_capacity" in discharge.columns:
            ax.plot(discharge["discharge_capacity"], discharge["voltage"],
                    color=color, label=label, linewidth=1.5)

    ax.set_xlabel("Discharge Capacity (Ah)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title(f"Voltage Curves — Cycle {cycle_number}")
    ax.legend()
    fig.tight_layout()

    if output_path is None:
        output_path = Path("output") / f"overlay_voltage_c{cycle_number}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)
