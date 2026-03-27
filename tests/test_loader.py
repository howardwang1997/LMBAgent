"""Tests for data loader."""

from lmbagent.data.loader import load_pec_csv, load_csv


def test_load_pec_csv(pec_csv_path):
    ds = load_pec_csv(pec_csv_path)
    assert ds.num_data_points > 16000
    assert ds.num_cycles == 3
    assert ds.test_name == "SAFT VL43EFe dQdV C/25"
    assert ds.start_datetime is not None
    assert "voltage" in ds.raw_data.columns
    assert "current" in ds.raw_data.columns
    # Check units were converted (voltage should be in V, not mV)
    assert ds.raw_data["voltage"].max() < 5.0  # V, not mV


def test_load_csv_auto_detects_pec(pec_csv_path):
    ds = load_csv(pec_csv_path)
    assert ds.num_data_points > 16000
    assert ds.test_name is not None


def test_load_pec_csv_custom_id(pec_csv_path):
    ds = load_pec_csv(pec_csv_path, data_id="my_test")
    assert ds.data_id == "my_test"
