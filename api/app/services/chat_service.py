"""Chat service: LLM-powered battery data analysis assistant."""

from __future__ import annotations

import asyncio

from lmbagent.agent import TOOL_REGISTRY
from lmbagent.litellm_backend import run_litellm_agent


class ChatService:
    """Service for LLM chat with tool execution."""

    def __init__(self):
        self.tool_descriptions = [
            {"name": tool["name"], "description": tool["description"]}
            for tool in TOOL_REGISTRY
        ]

    async def stream_response(
        self, message: str, dataset_id: str | None = None, model: str = "grok-4-1-fast-reasoning"
    ):
        """Stream LLM response with tool execution via asyncio.Queue bridge."""
        prompt = message
        if dataset_id:
            prompt = f"The user is working with dataset '{dataset_id}'.\n\nUser query: {message}"

        queue: asyncio.Queue = asyncio.Queue()

        def on_event(event: dict):
            queue.put_nowait(event)

        async def run_agent():
            try:
                result = await run_litellm_agent(
                    prompt=prompt,
                    model=model,
                    provider=None,
                    cwd=None,
                    on_event=on_event,
                )
                await queue.put({"type": "content", "content": result})
            except Exception as e:
                await queue.put({"type": "error", "error": str(e)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_agent())

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

        yield {"type": "done"}
        await task
