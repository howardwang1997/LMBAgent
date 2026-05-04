"""File server directory scanning and batch import.

Scans a shared file directory for battery experiment data files,
matches them with design metadata YAML files, and batch-imports
them into the DataStore.
"""

from __future__ import annotations

import logging
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
