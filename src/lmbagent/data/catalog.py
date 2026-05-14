"""File server directory scanning and batch import.

Scans a shared file directory for battery experiment data files,
matches them with design metadata YAML files, and batch-imports
them into the DataStore.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lmbagent.data.loader import detect_format, load_auto
from lmbagent.data.models import BatteryDataset
from lmbagent.data.schema import ExperimentDesign, find_design_file, load_experiment_design
from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".npy", ".txt"}


@dataclass
class ExperimentCandidate:
    """A discovered experiment file pending import."""

    path: Path
    format: str
    design_path: Optional[Path] = None
    design: Optional[ExperimentDesign] = None
    imported: bool = False
    data_id: Optional[str] = None
    error: Optional[str] = None


def scan_directory(
    root: str | Path,
    pattern: str = "**/*",
    extensions: set[str] | None = None,
) -> list[ExperimentCandidate]:
    """Scan a directory tree for experiment data files.

    Args:
        root: Root directory to scan.
        pattern: Glob pattern for file matching.
        extensions: File extensions to include (default: .csv, .xlsx, .npy, .txt).

    Returns:
        List of ExperimentCandidate objects.
    """
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS

    candidates: list[ExperimentCandidate] = []

    for path in sorted(root.glob(pattern)):
        if path.suffix.lower() not in extensions:
            continue
        if path.name.startswith("~"):
            continue
        if path.stat().st_size == 0:
            continue

        try:
            fmt = detect_format(path)
        except Exception:
            continue

        design_path = find_design_file(str(path))
        design = None
        if design_path:
            try:
                design = load_experiment_design(design_path)
            except Exception as e:
                logger.warning(f"Failed to load design for {path}: {e}")

        candidates.append(
            ExperimentCandidate(
                path=path,
                format=fmt,
                design_path=Path(design_path) if design_path else None,
                design=design,
            )
        )

    return candidates


def batch_import(
    candidates: list[ExperimentCandidate],
    store: DataStore | None = None,
    skip_errors: bool = True,
) -> list[ExperimentCandidate]:
    """Import a list of experiment candidates into the DataStore.

    Args:
        candidates: List of ExperimentCandidate from scan_directory.
        store: DataStore instance (uses singleton if None).
        skip_errors: If True, continue on errors. If False, raise on first error.

    Returns:
        Updated candidates with import status.
    """
    if store is None:
        store = DataStore()

    for candidate in candidates:
        if candidate.imported:
            continue
        try:
            ds = load_auto(candidate.path)
            if candidate.design and ds.experiment_design is None:
                ds.experiment_design = candidate.design
            ds = add_cycle_summary(ds)
            store.put(ds)
            candidate.imported = True
            candidate.data_id = ds.data_id
            logger.info(f"Imported {candidate.path.name} as {ds.data_id}")
        except Exception as e:
            candidate.error = str(e)
            logger.error(f"Failed to import {candidate.path}: {e}")
            if not skip_errors:
                raise

    return candidates


def import_directory(
    root: str | Path,
    store: DataStore | None = None,
    skip_errors: bool = True,
) -> list[ExperimentCandidate]:
    """Convenience: scan + import in one call.

    Args:
        root: Root directory containing experiment data.
        store: DataStore instance (uses singleton if None).
        skip_errors: Continue on individual file errors.

    Returns:
        List of all candidates with import status.
    """
    candidates = scan_directory(root)
    return batch_import(candidates, store=store, skip_errors=skip_errors)


def smart_scan_directory(root: str | Path) -> dict:
    """AI-powered directory analysis.

    Scans directory, analyzes naming patterns and structure using LLM,
    groups files by experiment batches, and returns a structured report.

    Args:
        root: Root directory to scan.

    Returns:
        Dict with:
          'candidates': list of ExperimentCandidate
          'summary': AI-generated summary string
          'patterns': list of identified naming patterns
          'groups': dict of group_name -> list of file paths
          'tree': directory tree as string
    """
    root = Path(root)
    candidates = scan_directory(root)
    tree_str = _build_tree_string(root, max_depth=3)

    file_list = [str(c.path.relative_to(root)) for c in candidates]
    format_counts: dict[str, int] = {}
    for c in candidates:
        format_counts[c.format] = format_counts.get(c.format, 0) + 1

    dir_info = (
        f"Directory: {root}\n"
        f"Total data files: {len(candidates)}\n"
        f"Formats: {format_counts}\n\n"
        f"Directory tree:\n{tree_str}\n\n"
        f"Files:\n"
    )
    for f in file_list[:50]:
        dir_info += f"  {f}\n"
    if len(file_list) > 50:
        dir_info += f"  ... and {len(file_list) - 50} more\n"

    prompt = f"""Analyze this battery experiment data directory structure.

{dir_info}

Identify:
1. Naming patterns (batch IDs, cell IDs, dates, etc.)
2. Directory organization logic
3. How files should be grouped

Respond in JSON:
{{
  "summary": "One sentence describing the directory structure",
  "patterns": ["pattern 1", "pattern 2", ...],
  "groups": {{
    "group_name_1": ["relative/path/file1.xlsx", ...],
    "group_name_2": ["relative/path/file2.xlsx", ...]
  }},
  "recommendations": "Brief recommendation for import"
}}

Return ONLY the JSON object."""

    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

    import json
    import litellm
    from lmbagent.config import get_model_config, DEFAULT_MODEL

    config = get_model_config(DEFAULT_MODEL)
    litellm_model = f"openai/{DEFAULT_MODEL}" if config["provider"] == "HKRI" else DEFAULT_MODEL

    completion_kwargs = {
        "model": litellm_model,
        "messages": [
            {"role": "system", "content": "You are a battery experiment data management expert. Analyze directory structures and return valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "api_key": config.get("api_key"),
        "temperature": 0.1,
        "timeout": 30,
    }
    if config.get("base_url"):
        completion_kwargs["api_base"] = config["base_url"]

    try:
        response = litellm.completion(**completion_kwargs)
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
    except Exception as e:
        logger.warning(f"LLM directory analysis failed: {e}")
        result = {
            "summary": f"Found {len(candidates)} data files in {format_counts} formats",
            "patterns": [],
            "groups": {},
            "recommendations": "",
        }

    result["candidates"] = candidates
    result["tree"] = tree_str
    return result


def _build_tree_string(root: Path, max_depth: int = 3, prefix: str = "") -> str:
    """Build a text directory tree for LLM context."""
    lines = []
    try:
        entries = sorted(root.iterdir())
    except PermissionError:
        return prefix + "[permission denied]"

    dirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file() and not e.name.startswith(".")]

    for i, d in enumerate(dirs[:10]):
        connector = "└── " if i == len(dirs) - 1 and not files else "├── "
        lines.append(f"{prefix}{connector}{d.name}/")
        if max_depth > 0:
            extension = "    " if i == len(dirs) - 1 and not files else "│   "
            lines.append(_build_tree_string(d, max_depth - 1, prefix + extension))

    file_display = files[:15]
    for i, f in enumerate(file_display):
        connector = "└── " if i == len(file_display) - 1 else "├── "
        size_kb = f.stat().st_size / 1024
        lines.append(f"{prefix}{connector}{f.name} ({size_kb:.0f} KB)")
    if len(files) > 15:
        lines.append(f"{prefix}└── ... and {len(files) - 15} more files")

    return "\n".join(lines)
