"""Tests for degradation analysis module."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lmbagent.data.models import BatteryDataset
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.degradation.features import (
    extract_discharge_curves,
    compute_dqdv,
    compute_cycle_features,
    compute_dataset_feature_vector,
)
from lmbagent.degradation.signatures import load_signatures, DEGRADATION_MODES
from lmbagent.degradation.decomposition import (
    decompose_degradation_modes,
    plot_decomposition,
    format_decomposition_summary,
)
from lmbagent.degradation.doe_checker import (
    check_doe_coverage,
    analyze_design_impact,
)


def _make_dataset(data_id, cell_id=None, n_cycles=10, cap_scale=1.0, design=None):
    rows = []
    for c in range(n_cycles):
        fade = c * 0.01 * cap_scale
        base_v = 3.5 - fade * 0.5
        for s in range(20):
            t_frac = s / 20
            if s < 10:
                v = base_v + 0.5 * t_frac
                cur = 0.5 * cap_scale
                ch_cap = 0.005 * (s + 1) * cap_scale
                dis_cap = 0.0
                ch_e = 0.018 * (s + 1) * cap_scale
                dis_e = 0.0
            else:
                v = base_v + 0.5 - 0.5 * (t_frac - 0.5)
                cur = -0.5 * cap_scale
                ch_cap = 0.05 * cap_scale
                dis_cap = 0.005 * (s - 9) * cap_scale * (1 - fade)
                ch_e = 0.18 * cap_scale
                dis_e = 0.016 * (s - 9) * cap_scale * (1 - fade)
            rows.append({
                "data_point": c * 20 + s,
                "cycle_index": c,
                "step_index": 0,
                "test_time": c * 200 + s * 10,
                "voltage": v,
                "current": cur,
                "charge_capacity": ch_cap,
                "discharge_capacity": dis_cap,
                "charge_energy": ch_e,
                "discharge_energy": dis_e,
                "internal_resistance": 0.05 + c * 0.005,
                "temperature_ambient": 25.0,
            })
    df = pd.DataFrame(rows)
    ds = BatteryDataset(data_id=data_id, source_file="test.csv", cell_id=cell_id,
                        raw_data=df, experiment_design=design)
    ds = add_cycle_summary(ds)
    return ds


def _make_design(cell_id, thickness=70.0, temp=25.0):
    from lmbagent.data.schema import ExperimentDesign, ElectrodeDesign, TestConditions
    return ExperimentDesign(
        cell_id=cell_id,
        chemistry="LMB-NMC811",
        positive_electrode=ElectrodeDesign(thickness_um=thickness),
        test=TestConditions(temperature_c=temp),
    )


def test_extract_discharge_curves():
    ds = _make_dataset("t1", n_cycles=5)
    curves = extract_discharge_curves(ds)
    assert len(curves) == 5
    assert "voltage" in curves[0]
    assert "capacity" in curves[0]


def test_compute_dqdv():
    v = np.linspace(3.0, 4.2, 100)
    q = np.linspace(0, 1.0, 100)
    v_out, dqdv = compute_dqdv(v, q)
    assert len(v_out) > 0
    assert len(dqdv) == len(v_out)


def test_compute_cycle_features():
    ds = _make_dataset("t1", n_cycles=5)
    features = compute_cycle_features(ds)
    assert len(features) == 5
    assert "discharge_cap" in features.columns
    assert "voltage_mean" in features.columns


def test_compute_dataset_feature_vector():
    ds = _make_dataset("t1", n_cycles=10)
    vec = compute_dataset_feature_vector(ds)
    assert vec["num_cycles"] == 10
    assert "initial_cap" in vec
    assert "fade_pct" in vec


def test_load_signatures_rule_based():
    sig = load_signatures("rule_based")
    assert sig.signatures.shape == (7, 100)
    assert len(sig.mode_names) == 7
    assert sig.method == "rule_based"


def test_decompose_degradation_modes():
    ds = _make_dataset("t1", n_cycles=10)
    result = decompose_degradation_modes(ds)
    assert "error" not in result
    assert len(result["cycles"]) == 10
    assert result["coefficients"].shape[1] == 7
    assert result["dominant_mode"] in DEGRADATION_MODES


def test_decompose_too_few_cycles():
    ds = _make_dataset("t1", n_cycles=1)
    result = decompose_degradation_modes(ds)
    assert "error" in result


def test_plot_decomposition(tmp_path):
    ds = _make_dataset("t1", n_cycles=10)
    result = decompose_degradation_modes(ds)
    path = plot_decomposition(result, output_path=tmp_path / "decomp.png")
    assert Path(path).exists()


def test_format_decomposition_summary():
    ds = _make_dataset("t1", n_cycles=10)
    result = decompose_degradation_modes(ds)
    text = format_decomposition_summary(result)
    assert "Degradation Mode Decomposition" in text
    assert "Dominant mode:" in text


def test_check_doe_coverage():
    designs = [
        _make_design("A", thickness=70.0, temp=25.0),
        _make_design("B", thickness=85.0, temp=25.0),
        _make_design("C", thickness=70.0, temp=45.0),
    ]
    datasets = [_make_dataset(f"d{i}", cell_id=chr(65+i), design=designs[i]) for i in range(3)]
    result = check_doe_coverage(datasets)
    assert result["n_experiments"] == 3
    assert len(result["factors_tested"]) > 0
    assert result["coverage_score"] > 0


def test_check_doe_empty():
    result = check_doe_coverage([])
    assert result["n_experiments"] == 0
    assert result["coverage_score"] == 0.0


def test_analyze_design_impact():
    designs = [
        _make_design("A", thickness=70.0, temp=25.0),
        _make_design("B", thickness=85.0, temp=25.0),
    ]
    datasets = [_make_dataset(f"d{i}", cell_id=chr(65+i), cap_scale=1.0 - i * 0.15,
                              design=designs[i]) for i in range(2)]
    result = analyze_design_impact(datasets)
    assert result["n_experiments"] == 2
    assert "factors_analyzed" in result
