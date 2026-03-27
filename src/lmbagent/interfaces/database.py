"""Abstract interface for database data sources (Phase 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from lmbagent.data.models import BatteryDataset


class DatabaseInterface(ABC):
    """Abstract interface for querying battery data from databases."""

    @abstractmethod
    async def query_data(
        self,
        battery_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        metrics: list[str] | None = None,
    ) -> BatteryDataset:
        """Query battery cycling data from a database.

        Args:
            battery_id: Unique identifier for the battery/cell.
            start_date: Filter data after this date.
            end_date: Filter data before this date.
            metrics: Specific metrics to retrieve (e.g., ["voltage", "current"]).

        Returns:
            BatteryDataset with the queried data.
        """
        ...

    @abstractmethod
    async def list_batteries(self) -> list[dict]:
        """List available batteries in the database."""
        ...
