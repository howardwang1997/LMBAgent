"""LLM-powered smart data loading.

Uses the configured LLM (minimax-m2.7 via HKRI) to analyze file headers
and determine the correct format and column mapping for loading battery data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import re

import requests

from lmbagent.config import get_model_config, DEFAULT_MODEL


_PEC_KEYWORDS = ["Request Year", "Test:", "TestRegime", "Variable names:", "Parameter names:"]
_ARBIN_KEYWORDS = ["Test_Time", "Current", "Potential", "Charge_Capacity", "Discharge_Capacity"]
_NEWARE_SHEET_NAMES = {"unit", "test", "cycle", "step", "record", "log", "idle", "curve"}
_NEWAREA_SHEET_PATTERNS = ["cycle_", "statis_", "detail_", "info"]
_NEWARE_CHINESE_KEYWORDS = ["工步", "总时间", "电压", "电流"]


def _try_local_analysis(file_path: Path, preview: str) -> dict[str, Any] | None:
    suffix = file_path.suffix.lower()
    lines_lower = preview.lower()

    if suffix == ".npy":
        return {
            "format": "neware_npy",
            "separator": "",
            "skip_rows": 0,
            "encoding": "binary",
            "column_map": {},
            "reasoning": "Detected .npy binary numpy file",
            "llm_used": False,
        }

    if suffix in (".xlsx", ".xls"):
        if any(k in preview for k in _NEWARE_CHINESE_KEYWORDS):
            return {
                "format": "neware_xlsx",
                "separator": "",
                "skip_rows": 0,
                "encoding": "binary",
                "column_map": {},
                "reasoning": "Detected Neware-style Excel file (Chinese headers)",
                "llm_used": False,
            }
        m = re.search(r"Sheets:\s*\[([^\]]+)\]", preview)
        if m:
            sheets = [s.strip().strip("'\"") for s in m.group(1).split(",")]
            sheets_lower = [s.lower() for s in sheets]
            if len(sheets) >= 3 and _NEWARE_SHEET_NAMES.issuperset(sheets_lower[:4]):
                return {
                    "format": "neware_xlsx",
                    "separator": "",
                    "skip_rows": 0,
                    "encoding": "binary",
                    "column_map": {},
                    "reasoning": "Detected Neware exported Excel (sheets: unit/test/cycle/step/record)",
                    "llm_used": False,
                }
            if any(any(p in s for p in _NEWAREA_SHEET_PATTERNS) for s in sheets_lower):
                return {
                    "format": "neware_xlsx",
                    "separator": "",
                    "skip_rows": 0,
                    "encoding": "binary",
                    "column_map": {},
                    "reasoning": "Detected NewareA-style Excel (sheets: Cycle/Statis/Detail)",
                    "llm_used": False,
                }
            if "chargecapacity" in lines_lower or "dischargecapacity" in lines_lower or "放电容量" in preview or "充电容量" in preview:
                return {
                    "format": "generic_csv",
                    "separator": "",
                    "skip_rows": 0,
                    "encoding": "utf-8",
                    "column_map": {},
                    "reasoning": "Detected battery summary Excel (has capacity columns)",
                    "llm_used": False,
                }

    if any(k in preview for k in _PEC_KEYWORDS):
        col_map = {}
        for line in preview.split("\n"):
            m = re.match(r'\s*"?(.+?)"?\s*[,\t]\s*(.*)', line)
            if not m:
                continue
            key, val = m.group(1).strip(), m.group(2).strip()
            kl = key.lower()
            if "cycle" in kl or "cyc" in kl:
                col_map["cycle_index"] = key
            elif "voltage" in kl or "volt" in kl:
                col_map["voltage"] = key
            elif "current" in kl or "curr" in kl or "amp" in kl:
                col_map["current"] = key
            elif "charge_cap" in kl or "charge cap" in kl:
                col_map["charge_capacity"] = key
            elif "discharge_cap" in kl or "discharge cap" in kl:
                col_map["discharge_capacity"] = key
            elif "test time" in kl or "test_time" in kl or "time" in kl:
                col_map["test_time"] = key

        sep = "," if "," in preview[:200] else "\t" if "\t" in preview[:200] else ","
        skip = 0
        for i, line in enumerate(preview.split("\n")):
            if "variable names" in line.lower() or "data" in line.lower():
                skip = i + 1
                break

        return {
            "format": "pec",
            "separator": sep,
            "skip_rows": skip,
            "encoding": "utf-8",
            "column_map": col_map,
            "reasoning": "Detected PEC format by header keywords",
            "llm_used": False,
        }

    if any(k.lower() in lines_lower for k in _ARBIN_KEYWORDS):
        col_map = {}
        for k in ["Test_Time", "Current", "Potential", "Charge_Capacity", "Discharge_Capcharge", "Cycle_Index"]:
            if k.lower() in lines_lower:
                col_map[k.lower().replace("_", " ")] = k
        return {
            "format": "arbin",
            "separator": ",",
            "skip_rows": 0,
            "encoding": "utf-8",
            "column_map": col_map,
            "reasoning": "Detected Arbin format by column names",
            "llm_used": False,
        }

    return None


_CAPACITY_KEYWORDS_LO = [
    "charge_cap", "discharge_cap", "chargecapacity", "dischargecapacity",
    "charge capacity", "discharge capacity", "充电容量", "放电容量",
    "充入容量", "放出容量",
]


def _find_column_in_header(target: str, header: list[str]) -> int | None:
    target_l = target.lower().replace(" ", "").replace("_", "")
    for i, h in enumerate(header):
        h_l = h.lower().replace(" ", "").replace("_", "")
        if h_l == target_l:
            return i
    for i, h in enumerate(header):
        h_l = h.lower().replace(" ", "").replace("_", "")
        if target_l in h_l or h_l in target_l:
            return i
    return None


def _read_file_preview(file_path: Path, max_lines: int = 20, max_bytes: int = 8192) -> str:
    suffix = file_path.suffix.lower()

    if suffix in (".csv", ".txt", ".tsv"):
        encodings = ["utf-8", "gbk", "gb2312", "latin-1", "utf-16"]
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc, errors="replace") as f:
                    lines = []
                    total = 0
                    for _ in range(max_lines):
                        line = f.readline()
                        if not line:
                            break
                        lines.append(line.rstrip())
                        total += len(line)
                        if total > max_bytes:
                            break
                    return "\n".join(lines)
            except Exception:
                continue
        return ""

    elif suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            parts = [f"Sheets: {wb.sheetnames}"]
            total_len = len(parts[0])
            for sn in wb.sheetnames:
                ws = wb[sn]
                rows = []
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i >= min(max_lines, 10):
                        break
                    rows.append(row)
                if rows:
                    header = [str(v) if v is not None else "" for v in rows[0]]
                    part = f"\nSheet '{sn}' columns: {header}"
                    for i, row in enumerate(rows[1:5]):
                        vals = [str(v) if v is not None else "" for v in row]
                        part += f"\n  Row {i+1}: {vals[:15]}"
                    if total_len + len(part) > max_bytes:
                        break
                    parts.append(part)
                    total_len += len(part)
            wb.close()
            return "\n".join(parts)
        except Exception as e:
            return f"Excel read error: {e}"

    elif suffix == ".npy":
        return "Binary numpy array file (.npy)"

    return f"Unknown format: {suffix}"


def _quick_xlsx_sniff(file_path: Path) -> list[str] | None:
    try:
        import zipfile
        with zipfile.ZipFile(str(file_path)) as z:
            wb_xml = z.read("xl/workbook.xml").decode("utf-8")
        import re
        return re.findall(r'name="([^"]+)"', wb_xml)
    except Exception:
        return None


def llm_analyze_file(file_path: str | Path) -> dict[str, Any]:
    file_path = Path(file_path)

    quick = _try_quick_analysis(file_path)
    if quick is not None:
        return quick

    preview = _read_file_preview(file_path)

    if not preview.strip():
        return {"format": "unknown", "reasoning": "Could not read file preview."}

    local = _try_local_analysis(file_path, preview)
    if local is not None:
        return local

    return _llm_analyze(file_path, preview)


def _try_quick_analysis(file_path: Path) -> dict[str, Any] | None:
    suffix = file_path.suffix.lower()

    if suffix == ".npy":
        return {
            "format": "neware_npy",
            "separator": "",
            "skip_rows": 0,
            "encoding": "binary",
            "column_map": {},
            "reasoning": "Detected .npy binary numpy file",
            "llm_used": False,
        }

    if suffix in (".xlsx", ".xls"):
        sheets = _quick_xlsx_sniff(file_path)
        if sheets is None:
            return None
        sheets_lower = [s.lower() for s in sheets]
        if len(sheets) >= 3 and _NEWARE_SHEET_NAMES.issuperset(sheets_lower[:4]):
            return {
                "format": "neware_xlsx",
                "separator": "",
                "skip_rows": 0,
                "encoding": "binary",
                "column_map": {},
                "reasoning": "Detected Neware exported Excel (sheets: unit/test/cycle/step/record)",
                "llm_used": False,
            }
        if any(any(p in s for p in _NEWAREA_SHEET_PATTERNS) for s in sheets_lower):
            return {
                "format": "neware_xlsx",
                "separator": "",
                "skip_rows": 0,
                "encoding": "binary",
                "column_map": {},
                "reasoning": "Detected NewareA-style Excel (sheets: Cycle/Statis/Detail)",
                "llm_used": False,
            }

    return None


def _llm_analyze(file_path: Path, preview: str) -> dict[str, Any]:
    prompt = f"""Identify this battery data file format and return JSON.

File: {file_path.name}
Lines:
{preview}

JSON schema:
{{"format":"pec|arbin|neware_xlsx|neware_npy|generic_csv","separator":",","skip_rows":0,"encoding":"utf-8","column_map":{{"cycle_index":"col","voltage":"col","current":"col","charge_capacity":"col","discharge_capacity":"col","test_time":"col"}},"capacity_split_by_current":false,"reasoning":"one sentence"}}

CRITICAL RULES:
1. charge_capacity and discharge_capacity are MANDATORY columns. Always identify them.
2. If there is a single "capacity" column (not split into charge/discharge), set "capacity_split_by_current": true and map it as "charge_capacity" (or as any key with the actual column name).
3. Common capacity column names: Capacity(Ah), 容量(Ah), Charge_Capacity, Discharge_Capacity, 充电容量, 放电容量, Charge Capacity, Discharge Capacity.
4. For xlsx files with multiple sheets, identify which sheet contains the detailed cycling data (usually named "record", "detail", "data", etc.).
5. Return ONLY the JSON, nothing else. Include ALL column_map entries you can identify."""

    config = get_model_config(DEFAULT_MODEL)
    base_url = config.get("base_url", "").rstrip("/")
    api_key = config.get("api_key")

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 512,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()

        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        elif "{" in text:
            text = text[text.index("{"):text.rindex("}") + 1]

        result = json.loads(text)
        result["llm_used"] = True
        return result
    except Exception as e:
        return {
            "format": "unknown",
            "reasoning": f"LLM analysis failed: {e}",
            "llm_used": False,
        }


def corrective_load(
    file_path: str | Path,
    user_feedback: str,
    previous_analysis: dict[str, Any] | None = None,
    data_id: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Use LLM + user natural language feedback to correct data loading.

    Multi-turn: each call receives the user's latest correction and the
    accumulated analysis, producing a new loading attempt.

    Args:
        file_path: Path to the data file.
        user_feedback: Natural language correction from the user.
        previous_analysis: Result dict from a prior llm_analyze_file or
            corrective_load call.  ``None`` means first correction turn.
        data_id: Optional dataset ID.

    Returns:
        (BatteryDataset | None, analysis_dict) — the loaded dataset (may be
        ``None`` if loading still fails) and the updated analysis for the
        next correction round.
    """
    from lmbagent.data.loader import load_auto, load_generic_csv
    from lmbagent.data.models import BatteryDataset
    import pandas as pd

    file_path = Path(file_path)
    preview = _read_file_preview(file_path)

    prev_summary = ""
    if previous_analysis:
        prev_summary = (
            f"Previous analysis:\n"
            f"  format: {previous_analysis.get('format', 'unknown')}\n"
            f"  separator: {previous_analysis.get('separator', ',')}\n"
            f"  skip_rows: {previous_analysis.get('skip_rows', 0)}\n"
            f"  encoding: {previous_analysis.get('encoding', 'utf-8')}\n"
            f"  column_map: {json.dumps(previous_analysis.get('column_map', {}), ensure_ascii=False)}\n"
            f"  reasoning: {previous_analysis.get('reasoning', '')}\n"
        )

    prompt = f"""You are a battery data loading expert. The user is correcting a failed or inaccurate data load.

File: {file_path.name} ({file_path.stat().st_size / 1024:.1f} KB)

File preview:
```
{preview}
```

{prev_summary}

User correction / feedback:
\"\"\"{user_feedback}\"\"\"

Based on the file preview and the user's feedback, produce a corrected loading configuration.
Respond in JSON format:
{{
  "format": "one of: pec, arbin, neware_xlsx, neware_npy, generic_csv",
  "separator": "the CSV separator character",
  "skip_rows": number of rows to skip before the data header,
  "encoding": "file encoding",
  "column_map": {{
    "cycle_index": "actual column name for cycle number",
    "voltage": "actual column name for voltage",
    "current": "actual column name for current",
    "charge_capacity": "actual column name for charge capacity",
    "discharge_capacity": "actual column name for discharge capacity",
    "test_time": "actual column name for test time",
    "step_time": "actual column name for step time",
    "step_index": "actual column name for step index",
    "temperature": "actual column name for temperature"
  }},
  "capacity_split_by_current": true/false,
  "reasoning": "explanation of the correction"
}}

Rules:
- Only include column_map entries for columns you can confidently identify from the preview + user feedback.
- Set "capacity_split_by_current": true if the file has a single "capacity" column that should be split into charge (I>0) / discharge (I<0).
- If the user says a column means something specific, trust the user over any automatic guess.
- Return ONLY the JSON object, no other text."""

    config = get_model_config(DEFAULT_MODEL)
    base_url = config.get("base_url", "").rstrip("/")
    api_key = config.get("api_key")

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a battery data loading expert. You help users correct data loading configurations. Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()

        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        elif "{" in text:
            text = text[text.index("{"):text.rindex("}") + 1]

        analysis = json.loads(text)
    except Exception as e:
        analysis = {
            "format": previous_analysis.get("format", "generic_csv") if previous_analysis else "generic_csv",
            "reasoning": f"LLM call failed: {e}",
            "column_map": previous_analysis.get("column_map", {}) if previous_analysis else {},
            "separator": previous_analysis.get("separator", ",") if previous_analysis else ",",
            "skip_rows": previous_analysis.get("skip_rows", 0) if previous_analysis else 0,
            "encoding": previous_analysis.get("encoding", "utf-8") if previous_analysis else "utf-8",
        }

    analysis["llm_used"] = True

    ds = _attempt_load_with_analysis(file_path, analysis, data_id)

    if ds is not None:
        ds.metadata = ds.metadata or {}
        ds.metadata["llm_analysis"] = analysis
        ds.metadata["user_corrections"] = ds.metadata.get("user_corrections", [])
        ds.metadata["user_corrections"].append(user_feedback)

    return ds, analysis


def _find_data_sheets(wb, col_map: dict[str, str], skip_rows: int = 0) -> list[tuple[str, list]]:
    """Find all sheets that contain battery data matching the column map.

    Returns list of (sheet_name, rows_list) sorted by data row count descending.
    """
    priority_names = {"record", "detail", "data", "raw_data", "raw data", "cycling data",
                      "循环数据", "原始数据"}
    results = []

    for sn in wb.sheetnames:
        ws = wb[sn]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < skip_rows + 2:
            continue

        header = [str(v).strip().lower() if v is not None else "" for v in rows[skip_rows]]

        has_voltage = False
        has_current = False
        for std_name, actual_name in col_map.items():
            if not actual_name:
                continue
            actual_l = actual_name.lower().replace(" ", "").replace("_", "")
            for h in header:
                h_l = h.replace(" ", "").replace("_", "")
                if h_l == actual_l or actual_l in h_l or h_l in actual_l:
                    if std_name == "voltage":
                        has_voltage = True
                    elif std_name == "current":
                        has_current = True

        if has_voltage and has_current:
            results.append((sn, rows))

    results.sort(key=lambda x: len(x[1]), reverse=True)
    return results


def _fix_zero_capacity(ds) -> Any:
    """Post-load fix: if charge/discharge capacity is all zero, try to repair.

    Strategies:
    1. If a 'capacity' column exists, split by current direction.
    2. If capacity columns are missing entirely, scan raw columns for candidates.
    """
    if ds is None or ds.raw_data.empty:
        return ds

    df = ds.raw_data

    has_charge = "charge_capacity" in df.columns
    has_discharge = "discharge_capacity" in df.columns

    charge_ok = has_charge and df["charge_capacity"].sum() > 0
    discharge_ok = has_discharge and df["discharge_capacity"].sum() > 0

    if charge_ok and discharge_ok:
        return ds

    if "capacity" in df.columns and "current" in df.columns and df["capacity"].sum() != 0:
        cap = df["capacity"].astype(float)
        cur = df["current"].astype(float)
        df["charge_capacity"] = cap.where(cur > 0, 0.0)
        df["discharge_capacity"] = cap.abs().where(cur < 0, 0.0)
        if "capacity" in df.columns:
            df = df.drop(columns=["capacity"])
        ds.raw_data = df
        return ds

    all_cols = df.columns.tolist()
    charge_candidate = None
    discharge_candidate = None
    for c in all_cols:
        c_l = c.lower().replace(" ", "").replace("_", "").replace("(", "").replace(")", "")
        if c_l in ("chargecapacity", "chargecapah", "充入容量") and not charge_ok:
            charge_candidate = c
        elif c_l in ("dischargecapacity", "dischargecapah", "放出容量") and not discharge_ok:
            discharge_candidate = c
        elif "chargecap" in c_l and not charge_ok:
            charge_candidate = c
        elif "dischargecap" in c_l and not discharge_ok:
            discharge_candidate = c
        elif "充电容量" in c and not charge_ok:
            charge_candidate = c
        elif "放电容量" in c and not discharge_ok:
            discharge_candidate = c

    if charge_candidate and not charge_ok:
        df["charge_capacity"] = pd.to_numeric(df[charge_candidate], errors="coerce").fillna(0)
    if discharge_candidate and not discharge_ok:
        df["discharge_capacity"] = pd.to_numeric(df[discharge_candidate], errors="coerce").fillna(0)
    ds.raw_data = df
    return ds


def _attempt_load_with_analysis(
    file_path: Path,
    analysis: dict[str, Any],
    data_id: str | None = None,
) -> Any:
    """Try to load a file using LLM analysis parameters.

    Returns BatteryDataset or None.
    """
    from lmbagent.data.loader import load_auto
    from lmbagent.data.models import BatteryDataset
    import pandas as pd

    fmt = analysis.get("format", "generic_csv")
    col_map = analysis.get("column_map", {})
    separator = analysis.get("separator", ",")
    skip_rows = analysis.get("skip_rows", 0)
    encoding = analysis.get("encoding", "utf-8")
    split_by_current = analysis.get("capacity_split_by_current", False)

    # Tier 1: Try standard loader with suggested format
    if fmt in ("pec", "arbin", "neware_xlsx", "neware_npy"):
        try:
            ds = load_auto(file_path, data_id=data_id, format=fmt)
            if ds.num_data_points > 0:
                ds = _fix_zero_capacity(ds)
                return ds
        except Exception:
            pass

    # Tier 2: Manual CSV load with LLM column map
    suffix = file_path.suffix.lower()
    if suffix in (".csv", ".txt", ".tsv") and col_map:
        try:
            encodings = [encoding, "utf-8", "gbk", "latin-1"]
            df = None
            for enc in encodings:
                try:
                    df = pd.read_csv(
                        file_path,
                        sep=separator,
                        skiprows=skip_rows,
                        encoding=enc,
                        on_bad_lines="skip",
                    )
                    break
                except Exception:
                    continue

            if df is not None and not df.empty:
                rename_map = _build_rename_map(col_map, df.columns.tolist())
                if rename_map:
                    df = df.rename(columns=rename_map)

                if split_by_current and "capacity" in df.columns and "current" in df.columns:
                    df["charge_capacity"] = df["capacity"].where(df["current"] > 0, 0.0)
                    df["discharge_capacity"] = df["capacity"].abs().where(df["current"] < 0, 0.0)
                    df = df.drop(columns=["capacity"])

                if "test_time" not in df.columns and "time" in df.columns:
                    df = df.rename(columns={"time": "test_time"})

                if "data_point" not in df.columns:
                    df.insert(0, "data_point", range(len(df)))

                if data_id is None:
                    data_id = file_path.stem[:8]

                ds = BatteryDataset(
                    data_id=data_id,
                    source_file=str(file_path),
                    raw_data=df,
                )
                ds = _fix_zero_capacity(ds)
                return ds
        except Exception:
            pass

    # Tier 3: xlsx with LLM column map — multi-sheet merge
    if suffix in (".xlsx", ".xls"):
        ds = _load_xlsx_with_analysis(file_path, analysis, data_id, skip_rows, col_map, split_by_current)
        if ds is not None:
            ds = _fix_zero_capacity(ds)
            return ds

    # Tier 4: last resort generic load
    try:
        ds = load_auto(file_path, data_id=data_id)
        if ds.num_data_points > 0:
            ds = _fix_zero_capacity(ds)
            return ds
    except Exception:
        pass

    return None


def _build_rename_map(col_map: dict[str, str], actual_columns: list[str]) -> dict[str, str]:
    rename_map = {}
    for standard_name, actual_name in col_map.items():
        if not actual_name:
            continue
        actual_l = actual_name.lower().replace(" ", "").replace("_", "")
        for col in actual_columns:
            col_l = col.lower().replace(" ", "").replace("_", "")
            if col_l == actual_l or actual_l in col_l or col_l in actual_l:
                rename_map[col] = standard_name
                break
    return rename_map


def _load_xlsx_with_analysis(
    file_path: Path,
    analysis: dict[str, Any],
    data_id: str | None,
    skip_rows: int,
    col_map: dict[str, str],
    split_by_current: bool,
) -> Any:
    """Load xlsx using LLM analysis — supports multi-sheet merge."""
    from lmbagent.data.models import BatteryDataset
    import pandas as pd

    if not col_map:
        col_map = _auto_detect_column_map_xlsx(file_path, skip_rows)
        if not col_map:
            return None

    try:
        import pandas as pd
        try:
            engine = "calamine"
            pd.read_excel(str(file_path), sheet_name=0, engine=engine, nrows=1)
        except Exception:
            engine = "openpyxl"

        xls = pd.ExcelFile(str(file_path), engine=engine)
        sheet_names = xls.sheet_names

        data_sheets = _select_data_sheets(sheet_names, col_map, skip_rows)

        all_dfs = []
        for sn in data_sheets:
            try:
                df_raw = pd.read_excel(xls, sheet_name=sn)
                if len(df_raw) < 1:
                    continue

                if skip_rows > 0 and skip_rows < len(df_raw):
                    df_raw = df_raw.iloc[skip_rows:].reset_index(drop=True)

                header = [str(v).strip() if v is not None else "" for v in df_raw.columns]
                rename_map = _build_rename_map(col_map, header)
                if rename_map:
                    df_raw = df_raw.rename(columns=rename_map)

                if split_by_current and "capacity" in df_raw.columns and "current" in df_raw.columns:
                    df_raw["charge_capacity"] = df_raw["capacity"].where(df_raw["current"] > 0, 0.0)
                    df_raw["discharge_capacity"] = df_raw["capacity"].abs().where(df_raw["current"] < 0, 0.0)
                    df_raw = df_raw.drop(columns=["capacity"])

                df_raw["sheet_name"] = sn
                all_dfs.append(df_raw)
            except Exception:
                continue

        xls.close()

        if not all_dfs:
            return None

        df = pd.concat(all_dfs, ignore_index=True)

        if "data_point" not in df.columns:
            df.insert(0, "data_point", range(len(df)))

        for col in ("voltage", "current", "charge_capacity", "discharge_capacity", "test_time", "cycle_index"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        if "voltage" not in df.columns or "current" not in df.columns:
            return None

        if data_id is None:
            data_id = file_path.stem[:8]

        if len(df) > 0:
            return BatteryDataset(
                data_id=data_id,
                source_file=str(file_path),
                raw_data=df,
            )
    except Exception:
        pass

    return None


def _select_data_sheets(
    sheet_names: list[str],
    col_map: dict[str, str],
    skip_rows: int,
) -> list[str]:
    """Select sheets that likely contain battery cycling data.

    Priority:
    1. Known detail sheet names (record, Detail*, data)
    2. Sheets whose headers match the column_map
    """
    KNOWN_DATA_NAMES = {"record", "detail", "data", "raw_data", "raw data",
                         "循环数据", "原始数据", "test data"}

    priority = []
    candidates = []

    for sn in sheet_names:
        sn_l = sn.lower().strip()
        if sn_l in KNOWN_DATA_NAMES or sn_l.startswith("detail"):
            priority.append(sn)
        elif sn_l not in ("unit", "test", "cycle", "step", "log", "idle",
                          "info", "summary", "statistic", "overview",
                          "cycle_summary", "statis", "parameter"):
            candidates.append(sn)

    if priority:
        return priority

    return candidates if candidates else sheet_names


def _auto_detect_column_map_xlsx(file_path: Path, skip_rows: int) -> dict[str, str]:
    """Try to build a column_map by scanning sheet headers for known patterns."""
    try:
        import pandas as pd
        try:
            engine = "calamine"
            pd.read_excel(str(file_path), sheet_name=0, engine=engine, nrows=1)
        except Exception:
            engine = "openpyxl"

        xls = pd.ExcelFile(str(file_path), engine=engine)
        for sn in xls.sheet_names:
            try:
                df_raw = pd.read_excel(xls, sheet_name=sn, nrows=1)
                if skip_rows > 0 and len(df_raw) > 0:
                    df_raw = pd.read_excel(xls, sheet_name=sn, skiprows=range(1, skip_rows + 1), nrows=1)
                header = [str(v).strip() if v is not None else "" for v in df_raw.columns]
                col_map = _match_header_to_standard(header)
                if col_map and "voltage" in col_map and "current" in col_map:
                    xls.close()
                    return col_map
            except Exception:
                continue
        xls.close()
    except Exception:
        pass
    return {}


def _match_header_to_standard(header: list[str]) -> dict[str, str]:
    """Match a header row to standard column names using fuzzy matching."""
    from lmbagent.data.loader import NEWARE_XLSX_COLUMN_MAP

    EXACT_PATTERNS = {
        "cycle_index": ["cycle", "cycle_index", "cyc", "循环号", "循环", "cyclenumber", "cycle_no"],
        "voltage": ["voltage", "voltage(v)", "volt", "v", "potential(v)", "电压(v)", "电压", "ecell/v"],
        "current": ["current", "current(a)", "curr", "i(a)", "电流(a)", "电流"],
        "test_time": ["testtime", "test_time", "totaltime", "total_time", "时间", "总时间", "time(s)"],
        "step_index": ["step", "step_index", "工步号"],
        "step_time": ["steptime", "step_time", "相对时间"],
        "charge_capacity": [
            "chargecapacity", "chargecapacity(ah)", "chargecapacity(ah)",
            "充电容量", "充入容量", "充电容量(ah)", "chargecapacity(ah)",
            "chargecapacity(ah)", "charge_cap",
        ],
        "discharge_capacity": [
            "dischargecapacity", "dischargecapacity(ah)", "dischargecapacity(ah)",
            "放电容量", "放出容量", "放电容量(ah)", "dischargecapacity(ah)",
            "dischargecapacity(ah)", "discharge_cap",
        ],
        "capacity": [
            "capacity(ah)", "容量(ah)", "容量", "capacity", "capah",
        ],
        "charge_energy": ["chargeenergy", "充电能量", "chargeenergy(wh)", "charge_energy"],
        "discharge_energy": ["dischargeenergy", "放电能量", "dischargeenergy(wh)", "discharge_energy"],
    }

    col_map = {}
    header_l = [h.lower().replace(" ", "").replace("_", "") for h in header]
    used_indices = set()

    for std_name in ("charge_capacity", "discharge_capacity"):
        patterns = EXACT_PATTERNS.get(std_name, [])
        for pat in patterns:
            for i, h_l in enumerate(header_l):
                if i in used_indices:
                    continue
                if h_l == pat:
                    col_map[std_name] = header[i]
                    used_indices.add(i)
                    break
            if std_name in col_map:
                break

    for std_name, patterns in EXACT_PATTERNS.items():
        if std_name in col_map:
            continue
        for pat in patterns:
            for i, h_l in enumerate(header_l):
                if i in used_indices:
                    continue
                if h_l == pat or pat in h_l:
                    col_map[std_name] = header[i]
                    used_indices.add(i)
                    break
            if std_name in col_map:
                break

    reverse_map = {v: k for k, v in NEWARE_XLSX_COLUMN_MAP.items()}
    for std_name, actual_col in reverse_map.items():
        if std_name in col_map:
            continue
        actual_l = actual_col.lower().replace(" ", "").replace("_", "")
        for i, h_l in enumerate(header_l):
            if i in used_indices:
                continue
            if h_l == actual_l or actual_l in h_l or h_l in actual_l:
                col_map[std_name] = header[i]
                used_indices.add(i)
                break

    return col_map


def llm_smart_load(
    file_path: str | Path,
    data_id: str | None = None,
    analysis: dict[str, Any] | None = None,
) -> Any:
    """Use LLM to determine how to load a file, then load it.

    Args:
        file_path: Path to data file.
        data_id: Optional dataset ID.
        analysis: Pre-computed analysis from llm_analyze_file (avoids duplicate LLM call).

    Returns:
        BatteryDataset or raises an exception if loading fails.
    """
    from lmbagent.data.loader import load_auto, load_generic_csv
    from lmbagent.data.models import BatteryDataset
    import pandas as pd

    file_path = Path(file_path)
    if analysis is None:
        analysis = llm_analyze_file(file_path)

    return _attempt_load_with_analysis(file_path, analysis, data_id)
