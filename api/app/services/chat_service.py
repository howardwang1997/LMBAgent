"""Chat service: LLM-powered battery data analysis assistant."""

from __future__ import annotations

import asyncio
import json

from lmbagent.agent import TOOL_REGISTRY
from lmbagent.litellm_backend import run_litellm_agent


class ChatService:
    """Service for LLM chat with tool execution."""

    def __init__(self):
        # Get tool descriptions for system prompt context
        self.tool_descriptions = [
            {"name": tool["name"], "description": tool["description"]}
            for tool in TOOL_REGISTRY
        ]

    async def stream_response(
        self, message: str, dataset_id: str | None = None, model: str = "grok-4-1-fast-reasoning"
    ):
        """Stream LLM response with tool execution."""
        # Build prompt with dataset context
        prompt = message
        if dataset_id:
            prompt = f"The user is working with dataset '{dataset_id}'.\n\nUser query: {message}"

        try:
            # Run the agent and stream results
            # Note: run_litellm_agent returns the final result text
            # We need to capture intermediate tool calls for streaming
            result = await run_litellm_agent(
                prompt=prompt,
                model=model,
                provider=None,
                cwd=None,
            )

            # For now, yield the final result
            # TODO: Enhance litellm_backend to support streaming callbacks
            yield {
                "type": "content",
                "content": result,
            }
            yield {"type": "done"}

        except Exception as e:
            yield {
                "type": "error",
                "error": str(e),
            }
