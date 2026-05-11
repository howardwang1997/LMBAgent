"""Tests for corrective_load in llm_loader."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from lmbagent.data.models import BatteryDataset


def _make_csv(path: Path, rows: list[dict], columns: list[str] | None = None):
    df = pd.DataFrame(rows, columns=columns)
    df.to_csv(path, index=False)
    return path


def _mock_llm_response(analysis_dict: dict):
    """Create a mock litellm.completion that returns the given analysis dict."""
    msg = MagicMock()
    msg.content = json.dumps(analysis_dict, ensure_ascii=False)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_corrective_load_csv_with_user_feedback(tmp_path):
    csv_path = _make_csv(
        tmp_path / "test.csv",
        rows=[
            {"Cyc": 1, "Volt": 3.5, "Curr": 0.5, "Cap": 0.15},
            {"Cyc": 1, "Volt": 3.4, "Curr": -0.5, "Cap": 0.14},
            {"Cyc": 2, "Volt": 3.5, "Curr": 0.5, "Cap": 0.14},
            {"Cyc": 2, "Volt": 3.3, "Curr": -0.5, "Cap": 0.13},
        ],
    )

    analysis = {
        "format": "generic_csv",
        "separator": ",",
        "skip_rows": 0,
        "encoding": "utf-8",
        "column_map": {
            "cycle_index": "Cyc",
            "voltage": "Volt",
            "current": "Curr",
            "capacity": "Cap",
        },
        "capacity_split_by_current": True,
        "reasoning": "User corrected column names",
    }

    with patch("lmbagent.data.llm_loader.litellm") as mock_litellm:
        mock_litellm.completion.return_value = _mock_llm_response(analysis)
        from lmbagent.data.llm_loader import corrective_load

        ds, result_analysis = corrective_load(
            csv_path,
            user_feedback="Cyc is cycle, Volt is voltage, Curr is current, Cap is capacity and should split by current",
        )

    assert ds is not None
    assert ds.num_data_points == 4
    assert "voltage" in ds.raw_data.columns
    assert "current" in ds.raw_data.columns
    assert "cycle_index" in ds.raw_data.columns
    assert result_analysis["llm_used"] is True
    assert ds.metadata["user_corrections"] == [
        "Cyc is cycle, Volt is voltage, Curr is current, Cap is capacity and should split by current"
    ]


def test_corrective_load_multiturn(tmp_path):
    csv_path = _make_csv(
        tmp_path / "test2.csv",
        rows=[
            {"X": 1, "Y": 3.5, "Z": 0.5, "W": 0.15},
            {"X": 1, "Y": 3.4, "Z": -0.5, "W": 0.14},
        ],
    )

    # First turn: wrong analysis
    analysis_1 = {
        "format": "generic_csv",
        "separator": ",",
        "skip_rows": 0,
        "encoding": "utf-8",
        "column_map": {},
        "capacity_split_by_current": False,
        "reasoning": "Could not identify columns",
    }

    with patch("lmbagent.data.llm_loader.litellm") as mock_litellm:
        mock_litellm.completion.return_value = _mock_llm_response(analysis_1)
        from lmbagent.data.llm_loader import corrective_load

        ds1, analysis_result_1 = corrective_load(
            csv_path,
            user_feedback="First attempt",
        )

    # Second turn: user corrects
    analysis_2 = {
        "format": "generic_csv",
        "separator": ",",
        "skip_rows": 0,
        "encoding": "utf-8",
        "column_map": {
            "cycle_index": "X",
            "voltage": "Y",
            "current": "Z",
            "capacity": "W",
        },
        "capacity_split_by_current": True,
        "reasoning": "User corrected: X=cycle, Y=voltage, Z=current, W=capacity",
    }

    with patch("lmbagent.data.llm_loader.litellm") as mock_litellm:
        mock_litellm.completion.return_value = _mock_llm_response(analysis_2)
        from lmbagent.data.llm_loader import corrective_load

        ds2, analysis_result_2 = corrective_load(
            csv_path,
            user_feedback="X is cycle, Y is voltage, Z is current, W is capacity",
            previous_analysis=analysis_result_1,
        )

    assert ds2 is not None
    assert ds2.num_data_points == 2
    assert "voltage" in ds2.raw_data.columns
    assert "charge_capacity" in ds2.raw_data.columns
    assert "discharge_capacity" in ds2.raw_data.columns


def test_corrective_load_with_previous_analysis(tmp_path):
    csv_path = _make_csv(
        tmp_path / "test3.csv",
        rows=[
            {"cycle": 1, "v": 3.5, "i": 0.5, "cap": 0.15},
            {"cycle": 1, "v": 3.4, "i": -0.5, "cap": 0.14},
        ],
    )

    prev = {
        "format": "generic_csv",
        "separator": ",",
        "skip_rows": 0,
        "encoding": "utf-8",
        "column_map": {"voltage": "v"},
        "reasoning": "Partial match",
    }

    analysis = {
        "format": "generic_csv",
        "separator": ",",
        "skip_rows": 0,
        "encoding": "utf-8",
        "column_map": {
            "cycle_index": "cycle",
            "voltage": "v",
            "current": "i",
            "capacity": "cap",
        },
        "capacity_split_by_current": True,
        "reasoning": "Full correction based on user feedback",
    }

    with patch("lmbagent.data.llm_loader.litellm") as mock_litellm:
        mock_litellm.completion.return_value = _mock_llm_response(analysis)
        from lmbagent.data.llm_loader import corrective_load

        ds, result = corrective_load(
            csv_path,
            user_feedback="cycle is cycle_index, i is current, cap is capacity",
            previous_analysis=prev,
        )

    assert ds is not None
    assert ds.num_data_points == 2


def test_corrective_load_llm_failure_falls_back(tmp_path):
    csv_path = _make_csv(
        tmp_path / "test4.csv",
        rows=[
            {"Cycle Index": 1, "Voltage(V)": 3.5, "Current(A)": 0.5,
             "Charge Capacity(Ah)": 0.15, "Discharge Capacity(Ah)": 0.14},
        ],
    )

    with patch("lmbagent.data.llm_loader.litellm") as mock_litellm:
        mock_litellm.completion.side_effect = Exception("LLM unavailable")
        from lmbagent.data.llm_loader import corrective_load

        ds, result = corrective_load(
            csv_path,
            user_feedback="standard arbin format",
        )

    # LLM failed but should still produce an analysis dict
    assert result is not None
    assert "reasoning" in result
