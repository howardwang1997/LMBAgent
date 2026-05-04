"""Tests for multi-experiment comparison module."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from lmbagent.data.models import BatteryDataset
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.comparison.overlay import overlay_capacity_fade, overlay_coulombic_efficiency
from lmbagent.comparison.delta import compute_delta_v
from lmbagent.comparison.metrics import build_comparison_table, rank_by_metric, summarize_differences


def _make_dataset(data_id, cell_id=None, n_cycles=5, cap_scale=1.0):
    rows = []
    for c in range(n_cycles):
        for s in range(4):
            rows.append({
                "data_point": c * 4 + s,
                "cycle_index": c,
                "step_index": 0,
                "test_time": c * 100 + s * 10,
                "voltage": 3.0 + (cap_scale * 0.5) * (1 - c / n_cycles) + s * 0.05,
                "current": 1.0 if s < 2 else -1.0,
                "charge_capacity": 0.01 * (s + 1) * cap_scale,
                "discharge_capacity": 0.009 * (s + 1) * cap_scale if s >= 2 else 0,
                "charge_energy": 0.035 * (s + 1) * cap_scale,
                "discharge_energy": 0.030 * (s + 1) * cap_scale if s >= 2 else 0,
                "internal_resistance": 0.05 + c * 0.01,
                "temperature_ambient": 25.0,
            })
    df = pd.DataFrame(rows)
    ds = BatteryDataset(data_id=data_id, source_file="test.csv", cell_id=cell_id, raw_data=df)
    ds = add_cycle_summary(ds)
    return ds


@pytest.fixture
def two_datasets():
    return [_make_dataset("a", "Cell_A"), _make_dataset("b", "Cell_B", cap_scale=0.9)]


@pytest.fixture
def three_datasets():
    return [
        _make_dataset("a", "Cell_A", cap_scale=1.0),
        _make_dataset("b", "Cell_B", cap_scale=0.9),
        _make_dataset("c", "Cell_C", cap_scale=0.8),
    ]


def test_overlay_capacity_fade(two_datasets, tmp_path):
    path = overlay_capacity_fade(two_datasets, output_path=tmp_path / "cap.png")
    assert Path(path).exists()


def test_overlay_capacity_fade_normalized(two_datasets, tmp_path):
    path = overlay_capacity_fade(two_datasets, normalize=True, output_path=tmp_path / "cap_norm.png")
    assert Path(path).exists()


def test_overlay_ce(two_datasets, tmp_path):
    path = overlay_coulombic_efficiency(two_datasets, output_path=tmp_path / "ce.png")
    assert Path(path).exists()


def test_compute_delta_v(two_datasets):
    result = compute_delta_v(two_datasets[0], two_datasets[1], cycle_number=0)
    if len(result["q_grid"]) > 0:
        assert result["rmse_mv"] >= 0


def test_build_comparison_table(three_datasets):
    table = build_comparison_table(three_datasets)
    assert len(table) == 3
    assert "cell_id" in table.columns
    assert "cycles" in table.columns
    assert "fade_pct" in table.columns


def test_rank_by_metric(three_datasets):
    ranked = rank_by_metric(three_datasets, metric="fade_pct", ascending=False)
    assert len(ranked) > 0
    assert ranked[0]["rank"] == 1
    assert "value" in ranked[0]


def test_summarize_differences(three_datasets):
    summary = summarize_differences(three_datasets)
    assert "differing_design_factors" in summary
    assert isinstance(summary["differing_design_factors"], list)


def test_summarize_differences_single():
    ds = _make_dataset("only", "X")
    summary = summarize_differences([ds])
    assert summary["best_retention"] is None
