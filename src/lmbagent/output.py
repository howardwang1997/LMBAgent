"""Output directory management and file caching."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

# Session-level mapping: data_id -> output directory
# Ensures all tool calls for the same dataset write to the same subdirectory
_session_dirs: dict[str, Path] = {}


def get_output_dir(data_id: str, base: str | Path = "output") -> Path:
    """Get or create the output directory for a dataset.

    First call for a data_id creates output/<YYYYMMDD_HHMMSS>_<data_id>/.
    Subsequent calls return the same directory.
    """
    if data_id in _session_dirs:
        return _session_dirs[data_id]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(base) / f"{timestamp}_{data_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    _session_dirs[data_id] = output_dir
    return output_dir


def get_plots_dir(data_id: str) -> Path:
    """Get the plots subdirectory for a dataset."""
    plots_dir = get_output_dir(data_id) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    return plots_dir


def get_cached_or_new(output_dir: Path, filename: str) -> tuple[Path, bool]:
    """Check if a file already exists (cached).

    Returns:
        (file_path, is_cached) — is_cached=True means skip regeneration.
    """
    path = output_dir / filename
    return path, path.exists()


def reset_session():
    """Reset session directories (for testing)."""
    _session_dirs.clear()
