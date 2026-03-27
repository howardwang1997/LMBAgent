"""Abstract interface for local experiment data auto-loading (Phase 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class LocalLoaderInterface(ABC):
    """Abstract interface for monitoring and auto-loading local experiment files."""

    @abstractmethod
    async def monitor_directory(self, path: Path, pattern: str = "*.csv") -> None:
        """Start monitoring a directory for new experiment data files.

        Args:
            path: Directory path to monitor.
            pattern: Glob pattern for matching data files.
        """
        ...

    @abstractmethod
    async def stop_monitoring(self) -> None:
        """Stop directory monitoring."""
        ...

    @abstractmethod
    async def scan_once(self, path: Path, pattern: str = "*.csv") -> list[str]:
        """Scan a directory once and load any new files.

        Returns:
            List of data_ids for newly loaded datasets.
        """
        ...
