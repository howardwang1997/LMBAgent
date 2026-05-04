"""Tests for SQLite-backed DataStore."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from lmbagent.data.models import BatteryDataset
from lmbagent.data.schema import ExperimentDesign, ElectrodeDesign
from lmbagent.data.store import DataStore


@pytest.fixture
def sqlite_store(tmp_path):
    db_path = tmp_path / "test.db"
    DataStore.reset()
    store = DataStore(db_path=db_path)
    yield store
    store._conn.close()
    DataStore.reset()


def _make_dataset(data_id="ds1", cell_id=None, design=None):
    return BatteryDataset(
        data_id=data_id,
        source_file="test.csv",
        cell_id=cell_id,
        raw_data=pd.DataFrame({
            "data_point": range(6),
            "cycle_index": [0, 0, 1, 1, 2, 2],
            "voltage": [3.0, 3.5, 3.6, 3.1, 3.5, 3.0],
            "current": [1.0, 1.0, -1.0, -1.0, 1.0, -1.0],
            "charge_capacity": [0.01, 0.02, 0.02, 0.02, 0.02, 0.02],
            "discharge_capacity": [0.0, 0.0, 0.01, 0.02, 0.0, 0.01],
        }),
        experiment_design=design,
    )


def test_put_and_get(sqlite_store):
    ds = _make_dataset("ds1", cell_id="A01")
    sqlite_store.put(ds)
    retrieved = sqlite_store.get("ds1")
    assert retrieved is not None
    assert retrieved.data_id == "ds1"
    assert retrieved.cell_id == "A01"


def test_list_ids(sqlite_store):
    sqlite_store.put(_make_dataset("a"))
    sqlite_store.put(_make_dataset("b"))
    assert set(sqlite_store.list_ids()) == {"a", "b"}


def test_remove(sqlite_store):
    sqlite_store.put(_make_dataset("x"))
    assert sqlite_store.remove("x")
    assert sqlite_store.get("x") is None


def test_remove_nonexistent(sqlite_store):
    assert not sqlite_store.remove("nope")


def test_clear(sqlite_store):
    sqlite_store.put(_make_dataset("a"))
    sqlite_store.put(_make_dataset("b"))
    sqlite_store.clear()
    assert sqlite_store.list_ids() == []


def test_persistence(sqlite_store, tmp_path):
    db_path = tmp_path / "test.db"
    sqlite_store.put(_make_dataset("persist_test", cell_id="C01"))
    sqlite_store._conn.close()
    DataStore.reset()

    store2 = DataStore(db_path=db_path)
    ds = store2.get("persist_test")
    assert ds is not None
    assert ds.cell_id == "C01"
    store2._conn.close()
    DataStore.reset()


def test_query_by_chemistry(sqlite_store):
    design = ExperimentDesign(cell_id="A01", chemistry="LMB-NMC811")
    sqlite_store.put(_make_dataset("d1", design=design))
    sqlite_store.put(_make_dataset("d2"))

    results = sqlite_store.query(chemistry="NMC811")
    assert len(results) == 1
    assert results[0].data_id == "d1"


def test_query_by_cell_id(sqlite_store):
    sqlite_store.put(_make_dataset("d1", cell_id="A01"))
    sqlite_store.put(_make_dataset("d2", cell_id="B02"))

    results = sqlite_store.query(cell_id="A01")
    assert len(results) == 1
    assert results[0].data_id == "d1"


def test_list_as_table(sqlite_store):
    design = ExperimentDesign(cell_id="A01", chemistry="LMB-NMC811")
    sqlite_store.put(_make_dataset("d1", design=design))
    table = sqlite_store.list_as_table()
    assert len(table) == 1
    assert "data_id" in table.columns
    assert "chemistry" in table.columns


def test_update_overwrites(sqlite_store):
    sqlite_store.put(_make_dataset("d1", cell_id="old"))
    sqlite_store.put(_make_dataset("d1", cell_id="new"))
    ds = sqlite_store.get("d1")
    assert ds.cell_id == "new"


def test_cycle_summary_persistence(sqlite_store, tmp_path):
    db_path = tmp_path / "test.db"
    ds = _make_dataset("d1")
    from lmbagent.data.transformer import add_cycle_summary
    ds = add_cycle_summary(ds)
    sqlite_store.put(ds)

    sqlite_store._conn.close()
    DataStore.reset()

    store2 = DataStore(db_path=db_path)
    ds2 = store2.get("d1")
    assert ds2 is not None
    assert not ds2.cycle_summary.empty
    assert "coulombic_efficiency" in ds2.cycle_summary.columns
    store2._conn.close()
    DataStore.reset()
