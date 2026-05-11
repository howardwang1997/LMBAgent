"""LLM-powered smart data loading.

Uses the configured LLM (minimax-m2.7 via HKRI) to analyze file headers
and determine the correct format and column mapping for loading battery data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import litellm

from lmbagent.config import get_model_config, DEFAULT_MODEL


def _read_file_preview(file_path: Path, max_lines: int = 20, max_bytes: int = 4096) -> str:
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
            wb = openpyxl.load_workbook(str(file_path), data_only=True)
            parts = [f"Sheets: {wb.sheetnames}"]
            for sn in wb.sheetnames[:3]:
                ws = wb[sn]
                rows = list(ws.iter_rows(values_only=True, max_row=min(max_lines, 10)))
                if rows:
                    header = [str(v) if v is not None else "" for v in rows[0]]
                    parts.append(f"\nSheet '{sn}' columns: {header}")
                    for i, row in enumerate(rows[1:5]):
                        vals = [str(v) if v is not None else "" for v in row]
                        parts.append(f"  Row {i+1}: {vals[:15]}")
            wb.close()
            return "\n".join(parts)
        except Exception as e:
            return f"Excel read error: {e}"

    elif suffix == ".npy":
        return "Binary numpy array file (.npy)"

    return f"Unknown format: {suffix}"


def llm_analyze_file(file_path: str | Path) -> dict[str, Any]:
    """Use LLM to analyze a data file and determine how to load it.

    Returns a dict with:
      - 'format': suggested format string
      - 'column_map': dict mapping standard names to actual column names
      - 'skip_rows': number of header rows to skip
      - 'separator': CSV separator
      - 'encoding': file encoding
      - 'reasoning': LLM's explanation
    """
    file_path = Path(file_path)
    preview = _read_file_preview(file_path)

    if not preview.strip():
        return {"format": "unknown", "reasoning": "Could not read file preview."}

    prompt = f"""Analyze this battery experiment data file and determine how to load it.

File: {file_path.name} ({file_path.stat().st_size / 1024:.1f} KB)

Preview (first ~20 lines):
```
{preview}
```

Respond in JSON format with these fields:
{{
  "format": "one of: pec, arbin, neware_xlsx, neware_npy, generic_csv",
  "separator": "the CSV separator character (comma, tab, semicolon, etc.)",
  "skip_rows": number of rows to skip before the data header,
  "encoding": "file encoding (utf-8, gbk, etc.)",
  "column_map": {{
    "cycle_index": "actual column name for cycle number",
    "voltage": "actual column name for voltage",
    "current": "actual column name for current",
    "charge_capacity": "actual column name for charge capacity",
    "discharge_capacity": "actual column name for discharge capacity",
    "test_time": "actual column name for test time"
  }},
  "reasoning": "brief explanation of your analysis"
}}

Only include column_map entries for columns you can identify. If unsure about a column, omit it.
Return ONLY the JSON object, no other text."""

    config = get_model_config(DEFAULT_MODEL)

    litellm_model = DEFAULT_MODEL
    if config["provider"] == "HKRI" and config.get("base_url"):
        litellm_model = f"openai/{DEFAULT_MODEL}"

    completion_kwargs = {
        "model": litellm_model,
        "messages": [
            {"role": "system", "content": "You are a battery data analysis expert. Analyze data file formats and return valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "api_key": config.get("api_key"),
        "temperature": 0.1,
    }
    if config.get("base_url"):
        completion_kwargs["api_base"] = config["base_url"]

    try:
        response = litellm.completion(**completion_kwargs)
        text = response.choices[0].message.content.strip()

        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

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
    litellm_model = DEFAULT_MODEL
    if config["provider"] == "HKRI" and config.get("base_url"):
        litellm_model = f"openai/{DEFAULT_MODEL}"

    completion_kwargs = {
        "model": litellm_model,
        "messages": [
            {"role": "system", "content": "You are a battery data loading expert. You help users correct data loading configurations. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "api_key": config.get("api_key"),
        "temperature": 0.1,
    }
    if config.get("base_url"):
        completion_kwargs["api_base"] = config["base_url"]

    try:
        response = litellm.completion(**completion_kwargs)
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
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
                rename_map = {}
                for standard_name, actual_name in col_map.items():
                    if actual_name and actual_name in df.columns:
                        rename_map[actual_name] = standard_name
                if rename_map:
                    df = df.rename(columns=rename_map)

                # Capacity split by current direction
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

                return BatteryDataset(
                    data_id=data_id,
                    source_file=str(file_path),
                    raw_data=df,
                )
        except Exception:
            pass

    # Tier 3: xlsx with LLM column map
    if suffix in (".xlsx", ".xls") and col_map:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(file_path), data_only=True)

            # Find best sheet
            target_sheet = None
            for sn in wb.sheetnames:
                if sn.startswith("Detail") or sn == "record" or sn == "Record":
                    target_sheet = wb[sn]
                    break
            if target_sheet is None:
                target_sheet = wb[wb.sheetnames[0]]

            rows = list(target_sheet.iter_rows(values_only=True))
            wb.close()
            if len(rows) < skip_rows + 2:
                return None

            header = [str(v).strip() if v is not None else "" for v in rows[skip_rows]]

            # Build column index from LLM map
            col_idx = {}
            for std_name, actual_name in col_map.items():
                if not actual_name:
                    continue
                for i, h in enumerate(header):
                    if actual_name in h or h in actual_name:
                        col_idx[std_name] = i
                        break

            if "voltage" not in col_idx or "current" not in col_idx:
                return None

            data_lists: dict[str, list] = {
                "voltage": [], "current": [], "cycle_index": [],
                "test_time": [], "charge_capacity": [], "discharge_capacity": [],
            }

            for row in rows[skip_rows + 1:]:
                if row is None:
                    continue
                try:
                    voltage = float(row[col_idx["voltage"]])
                    current = float(row[col_idx["current"]])

                    cycle = 0
                    if "cycle_index" in col_idx and col_idx["cycle_index"] < len(row):
                        cv = row[col_idx["cycle_index"]]
                        cycle = int(cv) if cv is not None else 0

                    time_val = 0.0
                    if "test_time" in col_idx and col_idx["test_time"] < len(row):
                        tv = row[col_idx["test_time"]]
                        if tv is not None:
                            time_val = float(tv) if isinstance(tv, (int, float)) else 0.0

                    if split_by_current and "capacity" in col_idx and col_idx["capacity"] < len(row):
                        cap = float(row[col_idx["capacity"]]) if row[col_idx["capacity"]] is not None else 0.0
                        charge_cap = cap if current > 0 else 0.0
                        discharge_cap = abs(cap) if current < 0 else 0.0
                    else:
                        charge_cap = 0.0
                        discharge_cap = 0.0
                        if "charge_capacity" in col_idx and col_idx["charge_capacity"] < len(row):
                            ccv = row[col_idx["charge_capacity"]]
                            charge_cap = float(ccv) if ccv is not None else 0.0
                        if "discharge_capacity" in col_idx and col_idx["discharge_capacity"] < len(row):
                            dcv = row[col_idx["discharge_capacity"]]
                            discharge_cap = float(dcv) if dcv is not None else 0.0

                    data_lists["voltage"].append(voltage)
                    data_lists["current"].append(current)
                    data_lists["cycle_index"].append(cycle)
                    data_lists["test_time"].append(time_val)
                    data_lists["charge_capacity"].append(charge_cap)
                    data_lists["discharge_capacity"].append(discharge_cap)
                except (ValueError, TypeError, IndexError):
                    continue

            df = pd.DataFrame(data_lists)
            df.insert(0, "data_point", range(len(df)))

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

    # Tier 4: last resort generic load
    try:
        ds = load_auto(file_path, data_id=data_id)
        if ds.num_data_points > 0:
            return ds
    except Exception:
        pass

    return None


def llm_smart_load(file_path: str | Path, data_id: str | None = None) -> Any:
    """Use LLM to determine how to load a file, then load it.

    Returns a BatteryDataset or raises an exception if loading fails.
    """
    from lmbagent.data.loader import load_auto, load_generic_csv
    from lmbagent.data.models import BatteryDataset
    import pandas as pd

    file_path = Path(file_path)
    analysis = llm_analyze_file(file_path)

    fmt = analysis.get("format", "generic_csv")
    reasoning = analysis.get("reasoning", "")

    # Try the suggested format first
    if fmt in ("pec", "arbin", "neware_xlsx", "neware_npy"):
        try:
            ds = load_auto(file_path, data_id=data_id, format=fmt)
            ds.metadata = ds.metadata or {}
            ds.metadata["llm_analysis"] = analysis
            return ds
        except Exception:
            pass

    # Fall back to generic CSV with LLM-suggested column mapping
    col_map = analysis.get("column_map", {})
    separator = analysis.get("separator", ",")
    skip_rows = analysis.get("skip_rows", 0)
    encoding = analysis.get("encoding", "utf-8")

    if col_map:
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
                rename_map = {}
                for standard_name, actual_name in col_map.items():
                    if actual_name and actual_name in df.columns:
                        rename_map[actual_name] = standard_name
                if rename_map:
                    df = df.rename(columns=rename_map)

                if "data_point" not in df.columns:
                    df.insert(0, "data_point", range(len(df)))

                if data_id is None:
                    data_id = file_path.stem[:8]

                ds = BatteryDataset(
                    data_id=data_id,
                    source_file=str(file_path),
                    raw_data=df,
                )
                ds.metadata = ds.metadata or {}
                ds.metadata["llm_analysis"] = analysis
                return ds
        except Exception:
            pass

    # Last resort: try auto
    ds = load_auto(file_path, data_id=data_id)
    ds.metadata = ds.metadata or {}
    ds.metadata["llm_analysis"] = analysis
    return ds
