"""Data models for battery cycling data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from lmbagent.data.schema import ExperimentDesign


class BatteryDataset(BaseModel):
    """Container for a loaded battery dataset."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data_id: str
    source_file: str
    cell_id: Optional[str] = None
    test_name: Optional[str] = None
    start_datetime: Optional[datetime] = None
    raw_data: pd.DataFrame = Field(default_factory=pd.DataFrame)
    cycle_summary: pd.DataFrame = Field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = Field(default_factory=dict)
    experiment_design: Optional[ExperimentDesign] = None

    @property
    def num_cycles(self) -> int:
        if self.cycle_summary.empty:
            if self.raw_data.empty:
                return 0
            return int(self.raw_data["cycle_index"].nunique())
        return len(self.cycle_summary)

    @property
    def num_data_points(self) -> int:
        return len(self.raw_data)

    @property
    def chemistry(self) -> str | None:
        if self.experiment_design:
            return self.experiment_design.chemistry
        return self.metadata.get("chemistry")

    def ensure_raw_data(self) -> BatteryDataset:
        """Reload raw_data from source_file if empty.

        Returns self (with raw_data populated) or self unchanged if already loaded
        or source_file is unavailable.
        """
        if not self.raw_data.empty:
            return self
        if not self.source_file:
            return self
        try:
            from pathlib import Path
            if not Path(self.source_file).exists():
                return self
            from lmbagent.data.loader import load_auto
            fresh = load_auto(self.source_file, data_id=self.data_id)
            self.raw_data = fresh.raw_data
            if not self.cycle_summary.empty and fresh.cycle_summary.empty:
                pass
            elif fresh.cycle_summary.empty and not self.cycle_summary.empty:
                pass
            else:
                self.cycle_summary = fresh.cycle_summary
        except Exception:
            pass
        return self


# Standard column names for raw data (after normalization)
RAW_COLUMNS = [
    "data_point",
    "cycle_index",
    "step_index",
    "test_time",
    "step_time",
    "voltage",
    "current",
    "charge_capacity",
    "discharge_capacity",
    "charge_energy",
    "discharge_energy",
    "internal_resistance",
    "temperature_ambient",
    "temperature_cell",
    "datetime",
]

# Standard column names for cycle summary
SUMMARY_COLUMNS = [
    "cycle_index",
    "charge_capacity",
    "discharge_capacity",
    "coulombic_efficiency",
    "charge_energy",
    "discharge_energy",
    "energy_efficiency",
    "ir_charge",
    "ir_discharge",
    "capacity_retention",
    "end_voltage_charge",
    "end_voltage_discharge",
]
