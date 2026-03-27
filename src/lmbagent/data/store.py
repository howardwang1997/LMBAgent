"""In-memory data store for battery datasets."""

from __future__ import annotations

from lmbagent.data.models import BatteryDataset


class DataStore:
    """Singleton store mapping data_id to BatteryDataset."""

    _instance: DataStore | None = None
    _datasets: dict[str, BatteryDataset]

    def __new__(cls) -> DataStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._datasets = {}
        return cls._instance

    def put(self, dataset: BatteryDataset) -> None:
        self._datasets[dataset.data_id] = dataset

    def get(self, data_id: str) -> BatteryDataset | None:
        return self._datasets.get(data_id)

    def list_ids(self) -> list[str]:
        return list(self._datasets.keys())

    def remove(self, data_id: str) -> bool:
        return self._datasets.pop(data_id, None) is not None

    def clear(self) -> None:
        self._datasets.clear()

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
