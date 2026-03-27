"""Abstract interface for ML model prediction (Phase 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class MLPredictorInterface(ABC):
    """Abstract interface for ML-based battery cycle life prediction."""

    @abstractmethod
    async def predict_cycle_life(self, battery_features: pd.DataFrame) -> dict[str, Any]:
        """Predict remaining cycle life based on battery features.

        Args:
            battery_features: DataFrame with extracted features
                (e.g., early cycle capacity, CE trends, IR values).

        Returns:
            Dict with predictions: estimated remaining cycles,
            confidence interval, degradation trajectory.
        """
        ...

    @abstractmethod
    async def load_model(self, model_path: str) -> None:
        """Load a pre-trained prediction model."""
        ...
