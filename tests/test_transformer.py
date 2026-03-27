"""Tests for data transformer."""

from lmbagent.data.transformer import compute_cycle_summary, add_cycle_summary


def test_compute_cycle_summary(sample_dataset):
    summary = compute_cycle_summary(sample_dataset)
    assert len(summary) == 3  # 3 cycles
    assert "coulombic_efficiency" in summary.columns
    assert "capacity_retention" in summary.columns


def test_add_cycle_summary(sample_dataset):
    assert sample_dataset.cycle_summary.empty
    add_cycle_summary(sample_dataset)
    assert not sample_dataset.cycle_summary.empty
    assert len(sample_dataset.cycle_summary) == 3


def test_cycle_summary_ce(sample_dataset):
    summary = compute_cycle_summary(sample_dataset)
    # Cycle 1: charge=0.04, discharge=0.03 -> CE=75%
    cycle1 = summary[summary["cycle_index"] == 1].iloc[0]
    assert cycle1["charge_capacity"] == 0.04
    assert cycle1["discharge_capacity"] == 0.03
    assert abs(cycle1["coulombic_efficiency"] - 75.0) < 0.1
