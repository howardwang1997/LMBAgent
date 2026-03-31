"""Dataset service: wraps loader, store, and transformer."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from lmbagent.data.loader import load_csv
from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary, compute_insights


class DatasetService:
    """Service for dataset CRUD operations."""

    def __init__(self):
        self._store = DataStore()

    def list_datasets(self) -> list[dict]:
        """Return list of all dataset summaries."""
        datasets = []
        for data_id in self._store.list_ids():
            dataset = self._store.get(data_id)
            if dataset is None:
                continue

            raw = dataset.raw_data
            summary = {
                "data_id": dataset.data_id,
                "source_file": dataset.source_file,
                "test_name": dataset.test_name,
                "num_cycles": dataset.num_cycles,
                "num_data_points": dataset.num_data_points,
                "voltage_min": float(raw["voltage"].min()) if "voltage" in raw else 0.0,
                "voltage_max": float(raw["voltage"].max()) if "voltage" in raw else 0.0,
                "current_min": float(raw["current"].min()) if "current" in raw else 0.0,
                "current_max": float(raw["current"].max()) if "current" in raw else 0.0,
                "created_at": datetime.now().isoformat(),
            }
            datasets.append(summary)

        return datasets

    def load_from_file(
        self, file_path: str, data_id: str | None = None
    ) -> dict:
        """Load CSV from file path and return dataset info."""
        dataset = load_csv(file_path, data_id=data_id)
        self._store.put(dataset)

        return {
            "data_id": dataset.data_id,
            "test_name": dataset.test_name,
            "metadata": dataset.metadata,
            "num_data_points": dataset.num_data_points,
            "message": f"Dataset {dataset.data_id} loaded successfully",
        }

    def load_from_upload(
        self, file_content: bytes, filename: str, data_id: str | None = None
    ) -> dict:
        """Load CSV from uploaded file content."""
        # Write to temp file
        suffix = Path(filename).suffix if Path(filename).suffix else ".csv"
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as f:
            f.write(file_content)
            temp_path = f.name

        try:
            return self.load_from_file(temp_path, data_id)
        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

    def get_dataset(self, data_id: str) -> dict:
        """Get full dataset details including cycle summary and insights."""
        dataset = self._store.get(data_id)
        if dataset is None:
            raise ValueError(f"Dataset {data_id} not found")

        # Ensure cycle summary exists
        if dataset.cycle_summary.empty:
            add_cycle_summary(dataset)

        # Compute insights
        insights = compute_insights(dataset)

        raw = dataset.raw_data
        return {
            "data_id": dataset.data_id,
            "source_file": dataset.source_file,
            "test_name": dataset.test_name,
            "cell_id": dataset.cell_id,
            "start_datetime": str(dataset.start_datetime) if dataset.start_datetime else None,
            "num_cycles": dataset.num_cycles,
            "num_data_points": dataset.num_data_points,
            "voltage_min": float(raw["voltage"].min()) if "voltage" in raw else 0.0,
            "voltage_max": float(raw["voltage"].max()) if "voltage" in raw else 0.0,
            "current_min": float(raw["current"].min()) if "current" in raw else 0.0,
            "current_max": float(raw["current"].max()) if "current" in raw else 0.0,
            "cycle_summary": dataset.cycle_summary.to_dict("records"),
            "insights": insights,
        }

    def delete_dataset(self, data_id: str) -> None:
        """Delete a dataset from the store."""
        self._store.remove(data_id)
