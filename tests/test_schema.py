"""Tests for ExperimentDesign schema and YAML loading."""

import tempfile
from pathlib import Path

import pytest
import yaml

from lmbagent.data.schema import (
    ElectrodeDesign,
    ElectrolyteDesign,
    ExperimentDesign,
    SeparatorDesign,
    FormationProtocol,
    TestConditions,
    find_design_file,
    load_experiment_design,
)


def test_experiment_design_defaults():
    design = ExperimentDesign(cell_id="A01", chemistry="LMB-NMC811")
    assert design.cell_id == "A01"
    assert design.chemistry == "LMB-NMC811"
    assert design.form_factor is None
    assert design.positive_electrode.thickness_um is None


def test_experiment_design_full():
    design = ExperimentDesign(
        cell_id="B02",
        chemistry="LMB-LFP",
        form_factor="pouch",
        design_capacity_ah=3.0,
        voltage_range=(2.5, 4.2),
        positive_electrode=ElectrodeDesign(
            thickness_um=70.0,
            porosity=0.35,
            particle_radius_um=5.0,
        ),
        negative_electrode=ElectrodeDesign(type="Li_metal", thickness_um=20.0),
        electrolyte=ElectrolyteDesign(salt="LiPF6", concentration_mol_l=1.0),
        test=TestConditions(c_rates=[0.5, 1.0], temperature_c=25.0),
    )
    assert design.positive_electrode.thickness_um == 70.0
    assert design.test.c_rates == [0.5, 1.0]


def test_to_flat_dict():
    design = ExperimentDesign(
        cell_id="A01",
        chemistry="LMB-NMC811",
        positive_electrode=ElectrodeDesign(thickness_um=70.0),
    )
    flat = design.to_flat_dict()
    assert flat["cell_id"] == "A01"
    assert flat["positive_electrode.thickness_um"] == 70.0
    assert "negative_electrode.thickness_um" not in flat


def test_diff_same():
    d = ExperimentDesign(cell_id="A01", chemistry="LMB-NMC811")
    assert d.diff(d) == {}


def test_diff_different():
    d1 = ExperimentDesign(
        cell_id="A01",
        chemistry="LMB-NMC811",
        positive_electrode=ElectrodeDesign(thickness_um=70.0),
    )
    d2 = ExperimentDesign(
        cell_id="A02",
        chemistry="LMB-NMC811",
        positive_electrode=ElectrodeDesign(thickness_um=85.0),
    )
    diffs = d1.diff(d2)
    assert "positive_electrode.thickness_um" in diffs
    assert diffs["positive_electrode.thickness_um"] == (70.0, 85.0)


def test_load_from_yaml():
    content = {
        "cell_id": "A01",
        "chemistry": "LMB-NMC811",
        "form_factor": "pouch",
        "positive_electrode": {"thickness_um": 70.0},
        "electrolyte": {"salt": "LiPF6", "concentration_mol_l": 1.0},
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        yaml.dump(content, f)
        f.flush()
        design = load_experiment_design(f.name)

    assert design.cell_id == "A01"
    assert design.positive_electrode.thickness_um == 70.0
    assert design.electrolyte.salt == "LiPF6"


def test_find_design_file(tmp_path):
    data_file = tmp_path / "cell_A01.csv"
    data_file.write_text("dummy")

    design_file = tmp_path / "cell_A01_design.yaml"
    design_file.write_text("cell_id: A01\nchemistry: LMB-NMC811")

    found = find_design_file(str(data_file))
    assert found is not None
    assert "cell_A01_design.yaml" in found


def test_find_design_file_not_found(tmp_path):
    data_file = tmp_path / "cell_X01.csv"
    data_file.write_text("dummy")
    assert find_design_file(str(data_file)) is None
