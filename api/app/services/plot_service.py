"""Plot service: generates battery data visualizations."""

from __future__ import annotations

import base64
from pathlib import Path

from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.output import get_output_dir
from lmbagent.visualization.capacity_plot import plot_capacity_fade
from lmbagent.visualization.efficiency_plot import plot_coulombic_efficiency
from lmbagent.visualization.impedance_plot import plot_impedance
from lmbagent.visualization.voltage_plot import plot_voltage_curves


class PlotService:
    """Service for generating battery data plots."""

    PLOT_TYPES = {
        "capacity_fade": plot_capacity_fade,
        "coulombic_efficiency": plot_coulombic_efficiency,
        "voltage_curves": plot_voltage_curves,
        "impedance": plot_impedance,
    }

    def __init__(self):
        self._store = DataStore()

    def generate_plot(
        self, data_id: str, plot_type: str, **kwargs
    ) -> dict:
        """Generate a plot and return base64-encoded image."""
        if plot_type not in self.PLOT_TYPES:
            raise ValueError(f"Unknown plot type: {plot_type}")

        dataset = self._store.get(data_id)
        if dataset is None:
            raise ValueError(f"Dataset {data_id} not found")

        # Ensure cycle summary exists
        if dataset.cycle_summary.empty:
            add_cycle_summary(dataset)

        # Get output directory
        output_dir = get_output_dir(data_id)
        plot_dir = output_dir / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)

        plot_path = plot_dir / f"{plot_type}.png"

        # Generate plot
        plot_func = self.PLOT_TYPES[plot_type]

        if plot_type == "capacity_fade":
            normalize = kwargs.get("normalize", False)
            plot_func(dataset, output_path=plot_path, normalize=normalize)
        elif plot_type == "coulombic_efficiency":
            y_range = kwargs.get("y_range")
            if y_range:
                # Parse "min-max" format
                try:
                    y_min, y_max = map(float, y_range.split("-"))
                    plot_func(dataset, output_path=plot_path, y_range=(y_min, y_max))
                except ValueError:
                    plot_func(dataset, output_path=plot_path)
            else:
                plot_func(dataset, output_path=plot_path)
        elif plot_type == "voltage_curves":
            cycles = kwargs.get("cycles")
            if cycles:
                plot_func(dataset, output_path=plot_path, cycle_numbers=cycles)
            else:
                plot_func(dataset, output_path=plot_path)
        else:
            plot_func(dataset, output_path=plot_path)

        # Read and encode as base64
        with open(plot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        return {
            "image": image_data,
            "plot_type": plot_type,
            "data_id": data_id,
        }

    def list_plots(self, data_id: str) -> list[dict]:
        """List available plots for a dataset."""
        dataset = self._store.get(data_id)
        if dataset is None:
            raise ValueError(f"Dataset {data_id} not found")

        output_dir = get_output_dir(data_id)
        plot_dir = output_dir / "plots"

        plots = []
        for plot_type in self.PLOT_TYPES:
            plot_path = plot_dir / f"{plot_type}.png"
            if plot_path.exists():
                plots.append({
                    "type": plot_type,
                    "exists": True,
                    "path": str(plot_path),
                })
            else:
                plots.append({
                    "type": plot_type,
                    "exists": False,
                })

        return plots
