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
