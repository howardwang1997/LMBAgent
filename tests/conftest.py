"""Shared test fixtures."""

from pathlib import Path

import pandas as pd
import pytest

from lmbagent.data.models import BatteryDataset
from lmbagent.data.store import DataStore
from lmbagent.output import reset_session

PEC_CSV_PATH = Path(__file__).parent.parent / "data" / "examples" / "pec.csv"


@pytest.fixture
def pec_csv_path():
    return PEC_CSV_PATH


@pytest.fixture
def sample_raw_df():
    """Small DataFrame with known values for deterministic testing."""
    return pd.DataFrame({
        "data_point": range(10),
        "cycle_index": [0, 0, 0, 1, 1, 1, 1, 2, 2, 2],
        "step_index": [0, 0, 1, 1, 1, 2, 2, 1, 1, 2],
        "test_time": [1, 5, 10, 15, 20, 25, 30, 35, 40, 45],
        "step_time": [1, 5, 1, 1, 5, 1, 5, 1, 5, 1],
        "voltage": [3.2, 3.3, 3.5, 3.6, 3.8, 3.5, 3.0, 3.6, 3.8, 3.5],
        "current": [0.0, 0.0, 1.0, 1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0],
        "charge_capacity": [0, 0, 0.01, 0.02, 0.04, 0.04, 0.04, 0.02, 0.04, 0.04],
        "discharge_capacity": [0, 0, 0, 0, 0, 0.01, 0.03, 0, 0, 0.01],
        "charge_energy": [0, 0, 0.035, 0.072, 0.152, 0.152, 0.152, 0.072, 0.152, 0.152],
        "discharge_energy": [0, 0, 0, 0, 0, 0.035, 0.09, 0, 0, 0.035],
        "internal_resistance": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "temperature_ambient": [25.0] * 10,
        "temperature_cell": [25.0] * 10,
        "datetime": pd.date_range("2019-02-22", periods=10, freq="5s"),
    })


@pytest.fixture
def sample_dataset(sample_raw_df):
    return BatteryDataset(
        data_id="test001",
        source_file="test.csv",
        test_name="Test Battery",
        raw_data=sample_raw_df,
    )


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the DataStore singleton and output session before each test."""
    DataStore.reset()
    reset_session()
    yield
    DataStore.reset()
    reset_session()


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "output"
