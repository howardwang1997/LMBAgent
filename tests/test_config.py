"""Tests for provider router."""

import os
from unittest.mock import patch

from lmbagent.config import get_model_config, DEFAULT_MODEL


def test_default_model_is_grok():
    assert "grok" in DEFAULT_MODEL.lower()


def test_grok_provider_inference():
    config = get_model_config("grok-4-1-fast-reasoning")
    assert config["provider"] == "GROK"
    assert config["model"] == "grok-4-1-fast-reasoning"
    assert config["base_url"] == "https://api.x.ai/v1"


def test_openai_provider_inference():
    config = get_model_config("gpt-4o")
    assert config["provider"] == "OPENAI"


def test_deepseek_provider_inference():
    config = get_model_config("deepseek-chat")
    assert config["provider"] == "DEEPSEEK"
    assert config["base_url"] == "https://api.deepseek.com"


def test_claude_provider_inference():
    config = get_model_config("claude-sonnet")
    assert config["provider"] == "ANTHROPIC"


def test_explicit_provider_override():
    config = get_model_config("my-custom-model", provider="GROK")
    assert config["provider"] == "GROK"


def test_unknown_model_defaults_to_openai():
    config = get_model_config("some-unknown-model")
    assert config["provider"] == "OPENAI"


def test_env_api_key():
    with patch.dict(os.environ, {"GROK_API_KEY": "test-key-123"}):
        config = get_model_config("grok-4-1-fast-reasoning")
        assert config["api_key"] == "test-key-123"


def test_env_base_url_override():
    with patch.dict(os.environ, {"GROK_BASE_URL": "http://localhost:8080"}):
        config = get_model_config("grok-4-1-fast-reasoning")
        assert config["base_url"] == "http://localhost:8080"
