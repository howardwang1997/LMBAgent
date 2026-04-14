"""Chat API endpoints with SSE streaming."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])
service = ChatService()


@router.get("/stream")
async def chat_stream(
    message: str = Query(..., description="User message"),
    dataset_id: str | None = Query(None, description="Dataset ID to analyze"),
    model: str = Query("grok-4-1-fast-reasoning", description="LLM model to use"),
):
    """Stream chat response using Server-Sent Events."""

    async def event_generator():
        """Generate SSE events."""
        async for chunk in service.stream_response(message, dataset_id, model):
            # Format as SSE event
            data = json.dumps(chunk)
            yield f"data: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/message")
async def chat_message(request: dict):
    """Non-streaming chat endpoint (alternative)."""
    message = request.get("message", "")
    dataset_id = request.get("dataset_id")
    model = request.get("model", "grok-4-1-fast-reasoning")

    if not message:
        return {"error": "Message is required"}

    # Collect all chunks
    response_text = ""
    tools_used = []

    async for chunk in service.stream_response(message, dataset_id, model):
        if chunk["type"] == "content":
            response_text += chunk.get("content", "")
        elif chunk["type"] == "tool":
            tools_used.append(chunk.get("tool_name"))
        elif chunk["type"] == "error":
            return {"error": chunk.get("error")}

    return {
        "response": response_text,
        "tools_used": tools_used,
        "dataset_id": dataset_id,
    }
