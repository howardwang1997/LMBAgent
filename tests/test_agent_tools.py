"""Tests for agent tool handlers."""

import pytest
import matplotlib
matplotlib.use("Agg")

from lmbagent.agent import (
    _handle_load_battery_data,
    _handle_transform_data,
    _handle_plot_capacity_fade,
    _handle_plot_coulombic_efficiency,
    _handle_plot_voltage_curves,
    _handle_generate_report,
    store,
)
from lmbagent.data.loader import load_pec_csv
from lmbagent.data.transformer import add_cycle_summary


@pytest.fixture
def loaded_data_id(pec_csv_path):
    ds = load_pec_csv(pec_csv_path, data_id="test_pec")
    ds = add_cycle_summary(ds)
    store.put(ds)
    return "test_pec"


@pytest.mark.asyncio
async def test_load_battery_data(pec_csv_path):
    result = await _handle_load_battery_data({"file_path": str(pec_csv_path)})
    assert not result.get("isError")
    text = result["content"][0]["text"]
    assert "data_id" in text
    assert "Data points: 16255" in text


@pytest.mark.asyncio
async def test_load_battery_data_missing_file():
    result = await _handle_load_battery_data({"file_path": "/nonexistent.csv"})
    assert result.get("isError")


@pytest.mark.asyncio
async def test_transform_data(loaded_data_id):
    result = await _handle_transform_data({"data_id": loaded_data_id})
    assert not result.get("isError")
    assert "cycle_index" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plot_capacity_fade(loaded_data_id, tmp_output):
    result = await _handle_plot_capacity_fade({
        "data_id": loaded_data_id,
        "output_path": str(tmp_output / "cap.png"),
    })
    assert not result.get("isError")
    assert "saved to" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plot_ce(loaded_data_id, tmp_output):
    result = await _handle_plot_coulombic_efficiency({
        "data_id": loaded_data_id,
        "output_path": str(tmp_output / "ce.png"),
    })
    assert not result.get("isError")


@pytest.mark.asyncio
async def test_plot_voltage(loaded_data_id, tmp_output):
    result = await _handle_plot_voltage_curves({
        "data_id": loaded_data_id,
        "cycle_numbers": "0,1",
        "output_path": str(tmp_output / "volt.png"),
    })
    assert not result.get("isError")


@pytest.mark.asyncio
async def test_generate_report(loaded_data_id, tmp_output):
    result = await _handle_generate_report({
        "data_id": loaded_data_id,
        "output_format": "markdown",
        "output_dir": str(tmp_output),
    })
    assert not result.get("isError")
    assert "Report generated" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_tool_not_found():
    result = await _handle_plot_capacity_fade({"data_id": "nonexistent"})
    assert result.get("isError")
