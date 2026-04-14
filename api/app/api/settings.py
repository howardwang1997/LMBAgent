"""Settings API endpoints for LLM provider configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import set_key, dotenv_values
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_PATH = Path(__file__).resolve().parents[3] / ".env"

PROVIDERS = ["GROK", "OPENAI", "DEEPSEEK", "ANTHROPIC"]


class SettingsUpdate(BaseModel):
    model: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 6:
        return "***"
    return key[:3] + "***" + key[-3:]


@router.get("")
async def get_settings():
    env = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    providers = {}
    for p in PROVIDERS:
        providers[p.lower()] = {
            "api_key_set": bool(env.get(f"{p}_API_KEY")),
            "api_key_masked": _mask_key(env.get(f"{p}_API_KEY")),
            "base_url": env.get(f"{p}_BASE_URL", ""),
        }
    return {
        "default_model": env.get("DEFAULT_MODEL", os.getenv("DEFAULT_MODEL", "grok-4-1-fast-reasoning")),
        "providers": providers,
    }


@router.post("")
async def update_settings(body: SettingsUpdate):
    ENV_PATH.touch(exist_ok=True)
    updated = []

    if body.model:
        set_key(str(ENV_PATH), "DEFAULT_MODEL", body.model)
        os.environ["DEFAULT_MODEL"] = body.model
        updated.append("DEFAULT_MODEL")

    provider = (body.provider or "").upper()
    if not provider and body.model:
        from lmbagent.config import MODEL_PROVIDER_MAP
        model_lower = body.model.lower()
        for prefix, prov in MODEL_PROVIDER_MAP.items():
            if model_lower.startswith(prefix):
                provider = prov
                break
        if not provider:
            provider = "OPENAI"

    if provider and body.api_key:
        key_name = f"{provider}_API_KEY"
        set_key(str(ENV_PATH), key_name, body.api_key)
        os.environ[key_name] = body.api_key
        updated.append(key_name)

    if provider and body.base_url:
        url_name = f"{provider}_BASE_URL"
        set_key(str(ENV_PATH), url_name, body.base_url)
        os.environ[url_name] = body.base_url
        updated.append(url_name)

    return {"updated": updated, "message": "Settings saved"}
