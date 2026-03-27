"""Abstract interface for real-time data analysis (Phase 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class RealtimeInterface(ABC):
    """Abstract interface for near-real-time battery data ingestion."""

    @abstractmethod
    async def process_realtime_data(self, new_data_chunk: pd.DataFrame) -> dict:
        """Process a new chunk of incoming battery data.

        Args:
            new_data_chunk: DataFrame with new measurement rows.

        Returns:
            Dict with processing results (anomalies detected, updated metrics, etc.).
        """
        ...

    @abstractmethod
    async def start_stream(self, source_config: dict) -> None:
        """Start listening to a real-time data stream."""
        ...

    @abstractmethod
    async def stop_stream(self) -> None:
        """Stop the real-time data stream."""
        ...
