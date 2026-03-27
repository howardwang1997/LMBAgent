"""Tests for data models and store."""

import pandas as pd

from lmbagent.data.models import BatteryDataset
from lmbagent.data.store import DataStore


def test_battery_dataset_creation():
    ds = BatteryDataset(data_id="t1", source_file="test.csv")
    assert ds.data_id == "t1"
    assert ds.num_data_points == 0
    assert ds.num_cycles == 0


def test_battery_dataset_with_data(sample_dataset):
    assert sample_dataset.num_data_points == 10
    assert sample_dataset.num_cycles == 3


def test_data_store():
    store = DataStore()
    ds = BatteryDataset(data_id="s1", source_file="test.csv")
    store.put(ds)
    assert store.get("s1") is ds
    assert "s1" in store.list_ids()
    store.remove("s1")
    assert store.get("s1") is None
