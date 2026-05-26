"""Battery data loading from PEC CSV, Neware, Arbin, and generic CSV files."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from lmbagent.data.models import BatteryDataset

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

UNIT_CONVERSIONS = {
    "voltage": 1e-3,
    "current": 1e-3,
    "charge_capacity": 1e-3,
    "discharge_capacity": 1e-3,
    "charge_energy": 1e-3,
    "discharge_energy": 1e-3,
    "internal_resistance": 1e-3,
}

GENERIC_COLUMN_ALIASES = {
    "time": [
        "time", "time_s", "time [s]", "test_time", "elapsed_time",
        "Time(s)", "t", "Total Time", "test_time_s",
    ],
    "voltage": [
        "voltage", "voltage_v", "v", "V", "potential",
        "Voltage(V)", "Ecell/V", "cell_voltage",
    ],
    "current": [
        "current", "current_a", "i", "I", "I(A)",
        "Current(A)", "A", "current_ma",
    ],
    "temperature": [
        "temperature", "temp", "t_c", "temperature_c",
        "Temperature(℃)", "temp_c", "temperature_ambient",
    ],
    "charge_capacity": [
        "charge_capacity", "Charge Capacity (Ah)", "Q_ch",
    ],
    "discharge_capacity": [
        "discharge_capacity", "Discharge Capacity (Ah)", "Q_dis",
    ],
    "cycle_index": [
        "cycle", "cycle_number", "cycle_index", "Cycle Index",
        "Cycle", "cycle_no",
    ],
    "step_index": [
        "step", "step_number", "step_index", "Step Index",
    ],
}

ARBIN_COLUMN_MAP = {
    "Test Time (s)": "test_time",
    "Potential (V)": "voltage",
    "Current (A)": "current",
    "Temperature (C)": "temperature_ambient",
    "Charge Capacity (Ah)": "charge_capacity",
    "Discharge Capacity (Ah)": "discharge_capacity",
    "Cycle Index": "cycle_index",
    "Step Index": "step_index",
}

NEWARE_XLSX_COLUMN_MAP = {
    "\u6570\u636e\u5e8f\u53f7": "data_point",
    "\u8bb0\u5f55\u5e8f\u53f7": "data_point",
    "\u5faa\u73af\u53f7": "cycle_index",
    "\u5faa\u73af": "cycle_index",
    "\u5de5\u6b65\u53f7": "step_index",
    "\u5de5\u6b65\u7c7b\u578b": "step_type",
    "\u72b6\u6001": "step_type",
    "\u65f6\u95f4": "step_time",
    "\u76f8\u5bf9\u65f6\u95f4": "step_time",
    "\u603b\u65f6\u95f4": "test_time",
    "\u7535\u6d41(A)": "current",
    "\u7535\u538b(V)": "voltage",
    "\u5bb9\u91cf(Ah)": "capacity",
    "\u653e\u7535\u5bb9\u91cf(Ah)": "discharge_capacity",
    "\u5145\u7535\u5bb9\u91cf(Ah)": "charge_capacity",
    "\u80fd\u91cf(Wh)": "energy",
    "\u653e\u7535\u80fd\u91cf(Wh)": "discharge_energy",
    "\u5145\u7535\u80fd\u91cf(Wh)": "charge_energy",
    "\u7edd\u5bf9\u65f6\u95f4": "datetime",
    "\u529f\u7387(W)": "power",
    "Index": "data_point",
    "Cycle Index": "cycle_index",
    "Step Index": "step_index",
    "Time": "test_time",
    "Total Time": "test_time",
    "Current(A)": "current",
    "Voltage(V)": "voltage",
    "Capacity(Ah)": "capacity",
    "Charge Capacity(Ah)": "charge_capacity",
    "Discharge Capacity(Ah)": "discharge_capacity",
    "Energy(Wh)": "energy",
    "Charge Energy(Wh)": "charge_energy",
    "Discharge Energy(Wh)": "discharge_energy",
}


def _find_alias_column(key: str, columns: list[str]) -> str | None:
    aliases = GENERIC_COLUMN_ALIASES.get(key, [])
    for alias in aliases:
        if alias in columns:
            return alias
    return None


def _parse_pec_header(file_path: Path) -> dict:
    metadata = {}
    header_line = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            stripped = line.strip()
            if stripped.startswith("#RESULTS CHECK") or stripped.startswith("#END RESULTS CHECK"):
                continue
            parts = stripped.split(",")
            if len(parts) > 10 and "Voltage" in stripped:
                header_line = i
                break
            if ":" in stripped and len(parts) <= 3:
                key = parts[0].split(":")[0].strip()
                val = stripped.split(":", 1)[1].strip().strip(",")
                if val:
                    metadata[key] = val

    return {"metadata": metadata, "header_line": header_line}


def _parse_neware_time_to_seconds(time_val) -> float:
    if time_val is None:
        return 0.0
    if isinstance(time_val, (int, float)):
        return float(time_val)
    s = str(time_val).strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    try:
        return float(s)
    except ValueError:
        return 0.0


def _try_load_design(data_path: str | Path) -> Optional[object]:
    from lmbagent.data.schema import find_design_file, load_experiment_design

    design_path = find_design_file(str(data_path))
    if design_path:
        return load_experiment_design(design_path)
    return None


def load_pec_csv(file_path: str | Path, data_id: str | None = None) -> BatteryDataset:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    header_info = _parse_pec_header(file_path)
    metadata = header_info["metadata"]
    header_line = header_info["header_line"]

    df = pd.read_csv(file_path, header=header_line, low_memory=False)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    rename_map = {pec_col: std_col for pec_col, std_col in PEC_COLUMN_MAP.items() if pec_col in df.columns}
    df = df.rename(columns=rename_map)
    df.insert(0, "data_point", range(len(df)))

    for col, factor in UNIT_CONVERSIONS.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") * factor

    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    start_dt = None
    if "Start Time" in metadata:
        try:
            start_dt = datetime.strptime(metadata["Start Time"], "%m/%d/%Y %H:%M:%S")
        except ValueError:
            pass

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    design = _try_load_design(file_path)

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        cell_id=metadata.get("Cell ID"),
        test_name=metadata.get("TestRegime Name"),
        start_datetime=start_dt,
        raw_data=df,
        metadata=metadata,
        experiment_design=design,
    )


def load_generic_csv(file_path: str | Path, data_id: str | None = None) -> BatteryDataset:
    """Load a generic CSV by auto-detecting column names from aliases."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_csv(file_path)
    cols = list(df.columns)

    rename_map = {}
    for std_name in (
        "time", "voltage", "current", "temperature",
        "charge_capacity", "discharge_capacity",
        "cycle_index", "step_index",
    ):
        found = _find_alias_column(std_name, cols)
        if found and found != std_name:
            rename_map[found] = std_name

    if rename_map:
        df = df.rename(columns=rename_map)

    if "test_time" not in df.columns and "time" in df.columns:
        df = df.rename(columns={"time": "test_time"})

    if "temperature_ambient" not in df.columns and "temperature" in df.columns:
        df = df.rename(columns={"temperature": "temperature_ambient"})

    df.insert(0, "data_point", range(len(df)))

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    design = _try_load_design(file_path)

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        raw_data=df,
        experiment_design=design,
    )


def load_arbin_csv(file_path: str | Path, data_id: str | None = None) -> BatteryDataset:
    """Load an Arbin battery tester CSV export."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_csv(file_path, encoding="utf-8-sig")

    rename_map = {k: v for k, v in ARBIN_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)
    df.insert(0, "data_point", range(len(df)))

    for col in ("voltage", "current", "charge_capacity", "discharge_capacity", "test_time"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    design = _try_load_design(file_path)

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        raw_data=df,
        experiment_design=design,
    )


def load_neware_xlsx(
    file_path: str | Path,
    sheet_name: str | None = None,
    data_id: str | None = None,
) -> BatteryDataset:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    import pandas as pd

    try:
        engine = "calamine"
        pd.read_excel(str(file_path), sheet_name=0, engine=engine, nrows=1)
    except Exception:
        engine = "openpyxl"

    xls = pd.ExcelFile(str(file_path), engine=engine)
    sheet_names = xls.sheet_names

    tvc_sheets = [s for s in sheet_names if s in ("CD_Capacity_Data", "C&D_Data")]
    if tvc_sheets:
        import openpyxl
        wb = openpyxl.load_workbook(str(file_path), data_only=True)
        result = _load_tvc_report(wb, file_path, data_id)
        wb.close()
        return result

    detail_sheet_name = _find_neware_detail_sheet_name(sheet_names, sheet_name)
    if detail_sheet_name is None:
        data_sheets = _find_all_data_sheet_names(xls, sheet_names, engine)
        if not data_sheets:
            raise ValueError(f"Could not find a data sheet in {file_path.name}. Sheets: {sheet_names}")
        detail_sheet_name = data_sheets[0]
        if len(data_sheets) > 1:
            return _load_multi_sheet_xlsx(xls, data_sheets, file_path, data_id)

    df_raw = pd.read_excel(xls, sheet_name=detail_sheet_name)
    xls.close()

    if len(df_raw) < 1:
        raise ValueError(f"Sheet has insufficient data (< 2 rows)")

    header = [str(v).strip() for v in df_raw.columns]

    col_idx: dict[str, int] = {}
    for col_name, key in NEWARE_XLSX_COLUMN_MAP.items():
        if key in col_idx:
            continue
        try:
            idx = header.index(col_name)
            col_idx[key] = idx
            continue
        except ValueError:
            pass
        for i, h in enumerate(header):
            if col_name in h and key not in col_idx:
                col_idx[key] = i
                break

    if "voltage" not in col_idx or "current" not in col_idx:
        col_idx = _fuzzy_match_columns(header)

    required = ["voltage", "current"]
    for col in required:
        if col not in col_idx:
            raise ValueError(f"Required column '{col}' not found. Header: {header}")

    has_cycle = "cycle_index" in col_idx
    has_step = "step_index" in col_idx
    has_test_time = "test_time" in col_idx
    has_step_time = "step_time" in col_idx
    has_capacity = "capacity" in col_idx
    has_explicit_charge = "charge_capacity" in col_idx
    has_explicit_discharge = "discharge_capacity" in col_idx
    has_energy = "energy" in col_idx
    has_charge_energy = "charge_energy" in col_idx
    has_discharge_energy = "discharge_energy" in col_idx

    raw_vals = df_raw.values
    n_rows = len(raw_vals)

    import numpy as np

    voltage = np.array([float(v) if v is not None else np.nan for v in raw_vals[:, col_idx["voltage"]]])
    current = np.array([float(v) if v is not None else np.nan for v in raw_vals[:, col_idx["current"]]])

    mask = ~(np.isnan(voltage) | np.isnan(current))

    cycle = np.zeros(n_rows, dtype=np.int32)
    if has_cycle:
        cv = raw_vals[:, col_idx["cycle_index"]]
        for i in range(n_rows):
            cycle[i] = int(cv[i]) if cv[i] is not None else 0

    step = np.zeros(n_rows, dtype=np.int32)
    if has_step:
        sv = raw_vals[:, col_idx["step_index"]]
        for i in range(n_rows):
            step[i] = int(sv[i]) if sv[i] is not None else 0

    test_time = np.zeros(n_rows, dtype=np.float64)
    if has_test_time:
        tc = col_idx["test_time"]
        for i in range(n_rows):
            v = raw_vals[i, tc] if tc < raw_vals.shape[1] else None
            if v is not None:
                test_time[i] = _parse_neware_time_to_seconds(v)
    elif has_step_time:
        tc = col_idx["step_time"]
        for i in range(n_rows):
            v = raw_vals[i, tc] if tc < raw_vals.shape[1] else None
            if v is not None:
                test_time[i] = _parse_neware_time_to_seconds(v)

    charge_cap = np.zeros(n_rows, dtype=np.float64)
    discharge_cap = np.zeros(n_rows, dtype=np.float64)
    if has_explicit_charge and has_explicit_discharge:
        for i in range(n_rows):
            ccv = raw_vals[i, col_idx["charge_capacity"]]
            dcv = raw_vals[i, col_idx["discharge_capacity"]]
            charge_cap[i] = float(ccv) if ccv is not None else 0.0
            discharge_cap[i] = float(dcv) if dcv is not None else 0.0
    elif has_capacity:
        for i in range(n_rows):
            cv = raw_vals[i, col_idx["capacity"]]
            cap = float(cv) if cv is not None else 0.0
            charge_cap[i] = cap if current[i] > 0 else 0.0
            discharge_cap[i] = abs(cap) if current[i] < 0 else 0.0

    charge_energy = np.zeros(n_rows, dtype=np.float64)
    discharge_energy = np.zeros(n_rows, dtype=np.float64)
    if has_charge_energy and has_discharge_energy:
        for i in range(n_rows):
            cev = raw_vals[i, col_idx["charge_energy"]]
            dev = raw_vals[i, col_idx["discharge_energy"]]
            charge_energy[i] = abs(float(cev)) if cev is not None else 0.0
            discharge_energy[i] = abs(float(dev)) if dev is not None else 0.0
    elif has_energy:
        for i in range(n_rows):
            ev = raw_vals[i, col_idx["energy"]]
            energy = float(ev) if ev is not None else 0.0
            charge_energy[i] = abs(energy) if current[i] > 0 else 0.0
            discharge_energy[i] = abs(energy) if current[i] < 0 else 0.0

    df = pd.DataFrame({
        "data_point": np.arange(n_rows),
        "voltage": voltage,
        "current": current,
        "cycle_index": cycle,
        "step_index": step,
        "test_time": test_time,
        "charge_capacity": charge_cap,
        "discharge_capacity": discharge_cap,
        "charge_energy": charge_energy,
        "discharge_energy": discharge_energy,
    })[mask]

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    design = _try_load_design(file_path)

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        raw_data=df,
        experiment_design=design,
    )


def _load_multi_sheet_xlsx(
    xls,
    data_sheets: list[str],
    file_path: Path,
    data_id: str | None = None,
) -> BatteryDataset:
    """Load and merge multiple data sheets from a single xlsx file.

    Each sheet is processed independently with NEWARE_XLSX_COLUMN_MAP,
    then concatenated with a sheet_name column.
    """
    import pandas as pd

    all_dfs = []
    for sn in data_sheets:
        df_raw = pd.read_excel(xls, sheet_name=sn)
        if len(df_raw) < 1:
            continue

        header = [str(v).strip() for v in df_raw.columns]

        col_idx: dict[str, int] = {}
        for col_name, key in NEWARE_XLSX_COLUMN_MAP.items():
            if key in col_idx:
                continue
            try:
                idx = header.index(col_name)
                col_idx[key] = idx
                continue
            except ValueError:
                pass
            for i, h in enumerate(header):
                if col_name in h and key not in col_idx:
                    col_idx[key] = i
                    break

        if "voltage" not in col_idx or "current" not in col_idx:
            col_idx = _fuzzy_match_columns(header)

        if "voltage" not in col_idx or "current" not in col_idx:
            continue

        raw_vals = df_raw.values
        n_rows = len(raw_vals)

        voltage = np.array([float(v) if v is not None else np.nan for v in raw_vals[:, col_idx["voltage"]]])
        current = np.array([float(v) if v is not None else np.nan for v in raw_vals[:, col_idx["current"]]])
        mask = ~(np.isnan(voltage) | np.isnan(current))

        cycle = np.zeros(n_rows, dtype=np.int32)
        if "cycle_index" in col_idx:
            cv = raw_vals[:, col_idx["cycle_index"]]
            for i in range(n_rows):
                cycle[i] = int(cv[i]) if cv[i] is not None else 0

        step = np.zeros(n_rows, dtype=np.int32)
        if "step_index" in col_idx:
            sv = raw_vals[:, col_idx["step_index"]]
            for i in range(n_rows):
                step[i] = int(sv[i]) if sv[i] is not None else 0

        test_time = np.zeros(n_rows, dtype=np.float64)
        if "test_time" in col_idx:
            tc = col_idx["test_time"]
            for i in range(n_rows):
                v = raw_vals[i, tc] if tc < raw_vals.shape[1] else None
                if v is not None:
                    test_time[i] = _parse_neware_time_to_seconds(v)

        charge_cap = np.zeros(n_rows, dtype=np.float64)
        discharge_cap = np.zeros(n_rows, dtype=np.float64)
        has_explicit_charge = "charge_capacity" in col_idx
        has_explicit_discharge = "discharge_capacity" in col_idx
        has_capacity = "capacity" in col_idx

        if has_explicit_charge and has_explicit_discharge:
            for i in range(n_rows):
                ccv = raw_vals[i, col_idx["charge_capacity"]]
                dcv = raw_vals[i, col_idx["discharge_capacity"]]
                charge_cap[i] = float(ccv) if ccv is not None else 0.0
                discharge_cap[i] = float(dcv) if dcv is not None else 0.0
        elif has_capacity:
            for i in range(n_rows):
                cv = raw_vals[i, col_idx["capacity"]]
                cap = float(cv) if cv is not None else 0.0
                charge_cap[i] = cap if current[i] > 0 else 0.0
                discharge_cap[i] = abs(cap) if current[i] < 0 else 0.0

        charge_energy = np.zeros(n_rows, dtype=np.float64)
        discharge_energy = np.zeros(n_rows, dtype=np.float64)
        if "charge_energy" in col_idx and "discharge_energy" in col_idx:
            for i in range(n_rows):
                cev = raw_vals[i, col_idx["charge_energy"]]
                dev = raw_vals[i, col_idx["discharge_energy"]]
                charge_energy[i] = abs(float(cev)) if cev is not None else 0.0
                discharge_energy[i] = abs(float(dev)) if dev is not None else 0.0
        elif "energy" in col_idx:
            for i in range(n_rows):
                ev = raw_vals[i, col_idx["energy"]]
                energy = float(ev) if ev is not None else 0.0
                charge_energy[i] = abs(energy) if current[i] > 0 else 0.0
                discharge_energy[i] = abs(energy) if current[i] < 0 else 0.0

        sub_df = pd.DataFrame({
            "voltage": voltage,
            "current": current,
            "cycle_index": cycle,
            "step_index": step,
            "test_time": test_time,
            "charge_capacity": charge_cap,
            "discharge_capacity": discharge_cap,
            "charge_energy": charge_energy,
            "discharge_energy": discharge_energy,
            "sheet_name": sn,
        })[mask]
        all_dfs.append(sub_df)

    xls.close()

    if not all_dfs:
        raise ValueError(f"No valid data found across sheets: {data_sheets}")

    df = pd.concat(all_dfs, ignore_index=True)
    df.insert(0, "data_point", range(len(df)))

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    design = _try_load_design(file_path)

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        raw_data=df,
        experiment_design=design,
    )


def _find_neware_detail_sheet_name(sheet_names: list[str], preferred: str | None = None) -> str | None:
    if preferred and preferred in sheet_names:
        return preferred
    for name in ("record", "Record", "RECORD"):
        if name in sheet_names:
            return name
    for name in sheet_names:
        if name.lower().startswith("detail"):
            return name
    for name in ("data", "Data", "raw_data", "Raw_Data", "cycling", "Cycling"):
        if name in sheet_names:
            return name
    return None


def _find_all_data_sheet_names(
    xls_or_path,
    sheet_names: list[str],
    engine: str = "openpyxl",
) -> list[str]:
    """Find all sheets that contain battery cycling data.

    Uses header inspection to find sheets with voltage + current columns.
    Returns list of sheet names sorted by row count (most data first).
    """
    import pandas as pd

    KNOWN_SKIP = {"unit", "test", "cycle", "step", "log", "idle", "info",
                  "summary", "statistic", "overview", "cycle_summary", "statis",
                  "parameter", "template", "config", "setup"}

    candidates = []
    for sn in sheet_names:
        if sn.lower() in KNOWN_SKIP:
            continue
        try:
            df = pd.read_excel(xls_or_path, sheet_name=sn, nrows=5)
            if len(df) < 2:
                continue
            header = [str(v).strip().lower() if v is not None else "" for v in df.columns]
            has_voltage = any("volt" in h or "电压" in h for h in header)
            has_current = any("curr" in h or "电流" in h or h == "i" for h in header)
            if has_voltage and has_current:
                full_df = pd.read_excel(xls_or_path, sheet_name=sn)
                candidates.append((sn, len(full_df)))
        except Exception:
            continue

    if not candidates:
        return []

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [sn for sn, _ in candidates]


def _load_tvc_report(wb, file_path: Path, data_id: str | None) -> BatteryDataset:
    """Load a TVC-style report xlsx with CD_Capacity_Data / C&D_Data sheets."""
    for sheet_name in ("CD_Capacity_Data", "C&D_Data"):
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 3:
            continue

        header0 = [str(v).strip() if v is not None else "" for v in rows[0]]
        header1 = [str(v).strip() if v is not None else "" for v in rows[1]]

        # Find cycle column
        cycle_col = None
        for i, h in enumerate(header1):
            if "cycle" in h.lower():
                cycle_col = i
                break
        if cycle_col is None:
            continue

        # Build column map: for each column j > cycle_col, determine if charge or discharge
        col_types: dict[int, str] = {}
        for j in range(cycle_col + 1, len(header1)):
            h = header1[j].lower()
            if "charge" in h and "dis" not in h:
                col_types[j] = "charge"
            elif "discharge" in h:
                col_types[j] = "discharge"

        if not col_types:
            continue

        # Use the first sample (first charge + first discharge pair)
        charge_col = None
        discharge_col = None
        for j in sorted(col_types):
            if col_types[j] == "charge" and charge_col is None:
                charge_col = j
            elif col_types[j] == "discharge" and discharge_col is None:
                discharge_col = j

        if charge_col is None or discharge_col is None:
            continue

        cycles = []
        charge_caps = []
        discharge_caps = []

        for row in rows[2:]:
            if row is None:
                continue
            try:
                cv = row[cycle_col]
                if cv is None:
                    continue
                cycle = int(cv)
                cc = row[charge_col]
                dc = row[discharge_col]
                cycles.append(cycle)
                charge_caps.append(float(cc) if cc is not None else 0.0)
                discharge_caps.append(float(dc) if dc is not None else 0.0)
            except (ValueError, TypeError, IndexError):
                continue

        if not cycles:
            continue

        df = pd.DataFrame({
            "cycle_index": cycles,
            "charge_capacity": charge_caps,
            "discharge_capacity": discharge_caps,
        })
        df.insert(0, "data_point", range(len(df)))

        if data_id is None:
            data_id = uuid.uuid4().hex[:8]

        design = _try_load_design(file_path)

        return BatteryDataset(
            data_id=data_id,
            source_file=str(file_path),
            raw_data=df,
            experiment_design=design,
        )

    raise ValueError("Could not parse TVC report format")


def _find_neware_detail_sheet(wb, preferred: str | None) -> object | None:
    """Find the detail/record data sheet in a Neware xlsx."""
    import openpyxl

    # Preferred sheet
    if preferred and preferred in wb.sheetnames:
        ws = wb[preferred]
        if isinstance(ws, openpyxl.worksheet.worksheet.Worksheet):
            return ws

    # Format A: 'record' sheet
    for name in ("record", "Record", "RECORD"):
        if name in wb.sheetnames:
            return wb[name]

    # Format B: Detail_* sheet
    for name in wb.sheetnames:
        if name.startswith("Detail"):
            return wb[name]

    # Fallback: find largest worksheet (not chartsheet)
    best = None
    best_rows = 0
    for name in wb.sheetnames:
        try:
            ws = wb[name]
            if not isinstance(ws, openpyxl.worksheet.worksheet.Worksheet):
                continue
            if ws.max_row and ws.max_row > best_rows:
                best_rows = ws.max_row
                best = ws
        except Exception:
            continue
    return best


def _fuzzy_match_columns(header: list[str]) -> dict[str, int]:
    """Fuzzy match common battery data column names."""
    col_idx: dict[str, int] = {}
    patterns = {
        "voltage": ["电压", "voltage", "v(v)", "potential"],
        "current": ["电流", "current", "i(a)", "i(a)"],
        "test_time": ["总时间", "total time", "时间"],
        "step_time": ["时间", "相对时间", "time", "step time"],
        "capacity": ["容量", "capacity", "cap"],
        "energy": ["能量", "energy", "eng"],
        "cycle_index": ["循环号", "循环序号", "循环", "cycle", "cycle_no"],
        "step_index": ["工步号", "工步序号", "步次", "step", "step_no"],
        "data_point": ["数据序号", "记录序号", "index", "序号"],
    }
    for key, pats in patterns.items():
        for i, h in enumerate(header):
            h_lower = h.lower()
            for pat in pats:
                if pat.lower() in h_lower and key not in col_idx:
                    col_idx[key] = i
                    break
    return col_idx


def load_neware_npy(file_path: str | Path, data_id: str | None = None) -> BatteryDataset:
    """Load a Neware .npy export."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    raw = np.load(str(file_path), allow_pickle=True).item()
    if not isinstance(raw, dict):
        raise ValueError("Expected a dict from .npy file")

    df = pd.DataFrame()
    cols = list(raw.keys())

    for std_name in ("time", "voltage", "current", "temperature", "capacity", "cycle"):
        found = _find_alias_column(std_name, cols)
        if found:
            df[std_name if std_name != "time" else "test_time"] = np.asarray(raw[found], dtype=np.float64)

    if "cycle" in df.columns:
        df = df.rename(columns={"cycle": "cycle_index"})
    df.insert(0, "data_point", range(len(df)))

    if data_id is None:
        data_id = uuid.uuid4().hex[:8]

    design = _try_load_design(file_path)

    return BatteryDataset(
        data_id=data_id,
        source_file=str(file_path),
        raw_data=df,
        experiment_design=design,
    )


def detect_format(file_path: str | Path) -> str:
    """Auto-detect the data format from file extension and content.

    Returns: 'pec', 'arbin', 'neware_xlsx', 'neware_npy', 'generic_csv'
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".xlsx":
        return "neware_xlsx"
    if suffix == ".npy":
        return "neware_npy"

    if suffix in (".csv", ".txt"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
            second_line = "" if suffix == ".csv" else ""

        if "Request Year" in first_line or "Test:" in first_line:
            return "pec"

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            head = "".join(f.readline() for _ in range(3))
        arbin_markers = ["Test Time (s)", "Potential (V)", "Current (A)"]
        if all(m in head for m in arbin_markers):
            return "arbin"

    return "generic_csv"


def load_auto(file_path: str | Path, data_id: str | None = None, format: str | None = None) -> BatteryDataset:
    """Auto-detect format and load data.

    Args:
        file_path: Path to data file.
        data_id: Optional custom ID.
        format: Override format detection. One of: 'pec', 'arbin', 'neware_xlsx',
                'neware_npy', 'generic_csv', 'auto'.
    """
    file_path = Path(file_path)
    original_path = file_path

    # Persist tmp files for debugging (but keep original path for design lookup)
    if str(file_path).startswith("/tmp"):
        _backup = Path.home() / ".lmbagent" / "uploads" / file_path.name
        _backup.parent.mkdir(parents=True, exist_ok=True)
        if not _backup.exists():
            import shutil
            shutil.copy2(str(file_path), str(_backup))

    if format and format != "auto":
        fmt = format
    else:
        fmt = detect_format(file_path)

    loaders = {
        "pec": load_pec_csv,
        "arbin": load_arbin_csv,
        "neware_xlsx": load_neware_xlsx,
        "neware_npy": load_neware_npy,
        "generic_csv": load_generic_csv,
    }

    loader = loaders.get(fmt)
    if loader is None:
        raise ValueError(f"Unknown format '{fmt}'. Supported: {list(loaders.keys())}")

    return loader(file_path, data_id=data_id)


def load_csv(file_path: str | Path, data_id: str | None = None) -> BatteryDataset:
    """Load a CSV file with auto-detection. Backward-compatible entry point."""
    return load_auto(file_path, data_id=data_id)
