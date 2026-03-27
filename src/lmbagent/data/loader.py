"""Battery data loading from PEC CSV and generic CSV files."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from lmbagent.data.models import BatteryDataset

# PEC CSV column name mapping to our standard names
PEC_COLUMN_MAP = {
    "Cycle": "cycle_index",
    "Step": "step_index",
    "Total Time (Seconds)": "test_time",
    "Step Time (Seconds)": "step_time",
    "Voltage (mV)": "voltage",
    "Current (mA)": "current",
    "Charge Capacity (mAh)": "charge_capacity",
    "Discharge Capacity (mAh)": "discharge_capacity",
    "Charge Capacity (mWh)": "charge_energy",
    "Discharge Capacity (mWh)": "discharge_energy",
    "Internal Resistance 1 (mOhm)": "internal_resistance",
    "Ambient temperature (°C)": "temperature_ambient",
    "Cell surface temperature (°C)": "temperature_cell",
    "Real Time": "datetime",
}

# Unit conversion factors: PEC uses mV, mA, mAh, mWh, mOhm
UNIT_CONVERSIONS = {
    "voltage": 1e-3,       # mV -> V
    "current": 1e-3,       # mA -> A
    "charge_capacity": 1e-3,       # mAh -> Ah
    "discharge_capacity": 1e-3,    # mAh -> Ah
    "charge_energy": 1e-3,         # mWh -> Wh
    "discharge_energy": 1e-3,      # mWh -> Wh
    "internal_resistance": 1e-3,   # mOhm -> Ohm
}


def _parse_pec_header(file_path: Path) -> dict:
    """Parse PEC CSV metadata header (lines before column names)."""
    metadata = {}
    header_line = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            stripped = line.strip()
            if stripped.startswith("#RESULTS CHECK"):
                # Skip the results check block
                continue
            if stripped.startswith("#END RESULTS CHECK"):
                continue
            # Check if this line looks like a data column header
            # (has many comma-separated fields)
            parts = stripped.split(",")
            if len(parts) > 10 and "Voltage" in stripped:
                header_line = i
                break
            # Parse key-value metadata
            if ":" in stripped and len(parts) <= 3:
                key = parts[0].split(":")[0].strip()
                val = stripped.split(":", 1)[1].strip().strip(",")
                if val:
                    metadata[key] = val

    return {"metadata": metadata, "header_line": header_line}


def load_pec_csv(file_path: str | Path, data_id: str | None = None) -> BatteryDataset:
    """Load a PEC CSV file into a BatteryDataset.

    Args:
        file_path: Path to the PEC CSV file.
        data_id: Optional ID; auto-generated if not provided.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Parse header to find metadata and data start line
    header_info = _parse_pec_header(file_path)
    metadata = header_info["metadata"]
    header_line = header_info["header_line"]

    # Read the CSV data
    df = pd.read_csv(
        file_path,
        header=header_line,
        low_memory=False,
    )

    # Remove trailing empty columns (from trailing commas)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    # Rename columns to standard names
    rename_map = {}
    for pec_col, std_col in PEC_COLUMN_MAP.items():
        if pec_col in df.columns:
            rename_map[pec_col] = std_col
    df = df.rename(columns=rename_map)

    # Add data_point index
    df.insert(0, "data_point", range(len(df)))

    # Convert units
    for col, factor in UNIT_CONVERSIONS.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") * factor

    # Parse datetime column
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    # Parse start time from metadata
    start_dt = None
    if "Start Time" in metadata:
        try:
            start_dt = datetime.strptime(metadata["Start Time"], "%m/%d/%Y %H:%M:%S")
        except ValueError:
            pass

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        cell_id=metadata.get("Cell ID"),
        test_name=metadata.get("TestRegime Name"),
        start_datetime=start_dt,
        raw_data=df,
        metadata=metadata,
    )


def load_csv(file_path: str | Path, data_id: str | None = None) -> BatteryDataset:
    """Load a generic CSV file. Auto-detects PEC format."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check if it's a PEC file by looking at the first line
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        first_line = f.readline()

    if "Request Year" in first_line or "Test:" in first_line:
        return load_pec_csv(file_path, data_id)

    # Generic CSV: assume first row is header, standard column names
    df = pd.read_csv(file_path)
    df.insert(0, "data_point", range(len(df)))

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        raw_data=df,
    )
