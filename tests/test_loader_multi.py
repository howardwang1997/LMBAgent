"""Tests for multi-format data loader."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from lmbagent.data.loader import (
    detect_format,
    load_arbin_csv,
    load_auto,
    load_generic_csv,
    load_neware_npy,
    load_pec_csv,
)


def test_detect_pec(pec_csv_path):
    assert detect_format(pec_csv_path) == "pec"


def test_detect_generic_csv(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("time,voltage,current\n1,3.0,0.5\n")
    assert detect_format(f) == "generic_csv"


def test_detect_arbin(tmp_path):
    f = tmp_path / "arbin.csv"
    f.write_text("Test Time (s),Potential (V),Current (A)\n1.0,3.5,0.1\n")
    assert detect_format(f) == "arbin"


def test_detect_neware_xlsx(tmp_path):
    f = tmp_path / "data.xlsx"
    assert detect_format(f) == "neware_xlsx"


def test_detect_neware_npy(tmp_path):
    f = tmp_path / "data.npy"
    assert detect_format(f) == "neware_npy"


def test_load_generic_csv(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("time,voltage,current,cycle_index\n0,3.5,1.0,1\n10,3.8,1.0,1\n")
    ds = load_generic_csv(f, data_id="gen1")
    assert ds.data_id == "gen1"
    assert "test_time" in ds.raw_data.columns
    assert "voltage" in ds.raw_data.columns
    assert len(ds.raw_data) == 2


def test_load_arbin_csv(tmp_path):
    f = tmp_path / "arbin.csv"
    f.write_text(
        "Test Time (s),Potential (V),Current (A),Charge Capacity (Ah),"
        "Discharge Capacity (Ah),Cycle Index\n"
        "0.0,3.5,0.1,0.0,0.0,1\n"
        "100.0,3.8,0.1,0.01,0.0,1\n"
    )
    ds = load_arbin_csv(f, data_id="arb1")
    assert ds.data_id == "arb1"
    assert "test_time" in ds.raw_data.columns
    assert len(ds.raw_data) == 2


def test_load_auto_pec(pec_csv_path):
    ds = load_auto(pec_csv_path, data_id="autopec")
    assert ds.data_id == "autopec"
    assert ds.num_data_points > 16000


def test_load_auto_generic(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("time,voltage,current\n0,3.5,1.0\n")
    ds = load_auto(f, data_id="autogen")
    assert ds.data_id == "autogen"


def test_load_auto_explicit_format(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("time,voltage,current\n0,3.5,1.0\n")
    ds = load_auto(f, data_id="forced", format="generic_csv")
    assert ds.data_id == "forced"


def test_load_auto_unknown_format():
    with pytest.raises(ValueError, match="Unknown format"):
        load_auto("test.csv", format="nonexistent_format")


def test_load_with_design_yaml(tmp_path):
    data_file = tmp_path / "cell_A01.csv"
    data_file.write_text("time,voltage,current,cycle_index\n0,3.5,1.0,1\n10,3.8,1.0,1\n")

    design_file = tmp_path / "cell_A01_design.yaml"
    design_file.write_text("cell_id: A01\nchemistry: LMB-NMC811\n")

    ds = load_auto(data_file, data_id="with_design")
    assert ds.experiment_design is not None
    assert ds.experiment_design.cell_id == "A01"
    assert ds.chemistry == "LMB-NMC811"


def test_load_nonexistent():
    with pytest.raises(FileNotFoundError):
        load_auto("/nonexistent/file.csv")
