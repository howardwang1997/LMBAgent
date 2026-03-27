"""Tests for LiteLLM backend tool calling loop."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lmbagent.litellm_backend import (
    _to_openai_tool,
    _result_to_text,
    run_litellm_agent,
)
from lmbagent.agent import TOOL_REGISTRY, store
from lmbagent.data.loader import load_pec_csv
from lmbagent.data.transformer import add_cycle_summary


def test_to_openai_tool():
    tool_def = TOOL_REGISTRY[0]
    result = _to_openai_tool(tool_def)
    assert result["type"] == "function"
    assert result["function"]["name"] == "load_battery_data"
    assert "parameters" in result["function"]
    assert result["function"]["parameters"]["type"] == "object"


def test_result_to_text():
    result = {"content": [{"type": "text", "text": "Hello world"}]}
    assert _result_to_text(result) == "Hello world"

    error_result = {"content": [{"type": "text", "text": "Error: not found"}], "isError": True}
    assert _result_to_text(error_result) == "Error: not found"


def test_all_tools_have_openai_format():
    for t in TOOL_REGISTRY:
        openai_tool = _to_openai_tool(t)
        assert openai_tool["type"] == "function"
        func = openai_tool["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        assert func["parameters"]["type"] == "object"
        assert "properties" in func["parameters"]


@pytest.mark.asyncio
async def test_run_litellm_agent_no_tool_calls():
    """Test that agent returns directly when model doesn't call tools."""
    mock_msg = MagicMock()
    mock_msg.content = "Analysis complete: the battery looks good."
    mock_msg.tool_calls = None

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_msg)]

    with patch("lmbagent.litellm_backend.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
        result = await run_litellm_agent(
            prompt="Tell me about the battery",
            model="grok-4-1-fast-reasoning",
        )
    assert result == "Analysis complete: the battery looks good."


@pytest.mark.asyncio
async def test_run_litellm_agent_with_tool_call(pec_csv_path):
    """Test agent handles a tool call then returns final response."""
    # First response: model calls load_battery_data
    tool_call = MagicMock()
    tool_call.id = "call_123"
    tool_call.function.name = "load_battery_data"
    tool_call.function.arguments = json.dumps({"file_path": str(pec_csv_path)})

    msg1 = MagicMock()
    msg1.content = ""
    msg1.tool_calls = [tool_call]

    # Second response: model returns final text
    msg2 = MagicMock()
    msg2.content = "Data loaded successfully. The battery has 3 cycles."
    msg2.tool_calls = None

    resp1 = MagicMock()
    resp1.choices = [MagicMock(message=msg1)]
    resp2 = MagicMock()
    resp2.choices = [MagicMock(message=msg2)]

    with patch("lmbagent.litellm_backend.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(side_effect=[resp1, resp2])
        result = await run_litellm_agent(
            prompt="Load the pec data",
            model="gpt-4o",
        )

    assert "Data loaded" in result or "3 cycles" in result
    # Verify the tool was actually called (data should be in store)
    assert len(store.list_ids()) > 0
