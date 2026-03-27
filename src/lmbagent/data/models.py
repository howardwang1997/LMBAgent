"""Data models for battery cycling data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


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
