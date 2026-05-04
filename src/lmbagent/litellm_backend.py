"""LiteLLM backend: tool calling loop for non-Claude models."""

from __future__ import annotations

import json
import sys
from typing import Any, Optional

import litellm

from lmbagent.agent import TOOL_REGISTRY, HANDLER_MAP
from lmbagent.config import SYSTEM_PROMPT, get_model_config


def _to_openai_tool(tool_def: dict) -> dict:
    """Convert a TOOL_REGISTRY entry to OpenAI function calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool_def["name"],
            "description": tool_def["description"],
            "parameters": tool_def["parameters"],
        },
    }


def _result_to_text(result: dict[str, Any]) -> str:
    """Extract text from handler result dict."""
    parts = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
    return "\n".join(parts) if parts else str(result)


async def run_litellm_agent(
    prompt: str,
    model: str,
    provider: Optional[str] = None,
    cwd: Optional[str] = None,
    max_turns: int = 20,
) -> str:
    """Run the LMB agent using LiteLLM with tool calling.

    Args:
        prompt: User prompt.
        model: Model name (e.g., "grok-4-1-fast-reasoning", "gpt-4o").
        provider: Optional provider override.
        cwd: Working directory (unused for now, reserved).
        max_turns: Maximum tool calling iterations to prevent infinite loops.

    Returns:
        Final assistant response text.
    """
    config = get_model_config(model, provider)

    # LiteLLM model format: for providers with custom base_url,
    # use "openai/<model>" prefix to route through OpenAI-compatible endpoint
    litellm_model = model
    if config["provider"] in ("GROK", "DEEPSEEK", "HKRI") and config.get("base_url"):
        litellm_model = f"openai/{model}"

    tools = [_to_openai_tool(t) for t in TOOL_REGISTRY]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    completion_kwargs: dict[str, Any] = {
        "model": litellm_model,
        "messages": messages,
        "tools": tools,
        "api_key": config.get("api_key"),
    }
    if config.get("base_url"):
        completion_kwargs["api_base"] = config["base_url"]

    for turn in range(max_turns):
        response = await litellm.acompletion(**completion_kwargs)
        msg = response.choices[0].message

        # Append assistant message to history
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        # No tool calls = agent is done
        if not msg.tool_calls:
            if msg.content:
                print(msg.content)
            return msg.content or ""

        # Execute each tool call
        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            handler = HANDLER_MAP.get(func_name)
            if handler is None:
                tool_result = f"Error: Unknown tool '{func_name}'"
            else:
                print(f"  [Tool] {func_name}({json.dumps(func_args, ensure_ascii=False)[:100]})")
                result = await handler(func_args)
                tool_result = _result_to_text(result)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

        # Update messages in completion kwargs
        completion_kwargs["messages"] = messages

    print("Warning: max_turns reached, stopping agent loop.", file=sys.stderr)
    return messages[-1].get("content", "") if messages else ""
