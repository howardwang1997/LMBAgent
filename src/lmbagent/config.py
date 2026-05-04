"""Provider router and model configuration.

Routes model names to appropriate API endpoints and keys.
Pattern reused from sciminer/config/agent.py.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Default model: MiniMax M2.7 via HKRI Agent
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "minimax-m2.7")

# Model name prefix -> provider mapping
MODEL_PROVIDER_MAP = {
    "minimax": "HKRI",
    "gpt-": "OPENAI",
    "o1-": "OPENAI",
    "o3-": "OPENAI",
    "o4-": "OPENAI",
    "deepseek-": "DEEPSEEK",
    "deepseek": "DEEPSEEK",
    "grok-": "GROK",
    "grok": "GROK",
    "claude-": "ANTHROPIC",
}

# Provider default base URLs (used when {PROVIDER}_BASE_URL is not set)
PROVIDER_DEFAULT_URLS = {
    "HKRI": "http://10.239.71.11:4000/v1",
    "GROK": "https://api.x.ai/v1",
    "DEEPSEEK": "https://api.deepseek.com",
}

# Provider default API keys (fallback when env var not set)
PROVIDER_DEFAULT_KEYS = {
    "HKRI": "sk-lbyzm4nBObASjSgCLRlspw",
}


def get_model_config(model_name: str, provider: Optional[str] = None) -> dict[str, str | None]:
    """Route model name to API base_url and api_key.

    Provider resolution:
    1. Explicit provider parameter
    2. Infer from model name prefix via MODEL_PROVIDER_MAP
    3. Default to "OPENAI" (most compatible)

    Environment variables: {PROVIDER}_BASE_URL, {PROVIDER}_API_KEY

    Args:
        model_name: Model identifier (e.g., "gpt-4o", "grok-4-1-fast-reasoning")
        provider: Optional provider override (e.g., "OPENAI", "GROK")

    Returns:
        Dict with 'model', 'base_url', 'api_key' keys.
    """
    if provider:
        provider = provider.upper()
    else:
        model_lower = model_name.lower()
        for prefix, prov in MODEL_PROVIDER_MAP.items():
            if model_lower.startswith(prefix):
                provider = prov
                break
        if provider is None:
            provider = "OPENAI"

    base_url = os.getenv(f"{provider}_BASE_URL")
    api_key = os.getenv(f"{provider}_API_KEY")

    # Fall back to provider default URLs
    if not base_url and provider in PROVIDER_DEFAULT_URLS:
        base_url = PROVIDER_DEFAULT_URLS[provider]

    # Fall back to provider default keys
    if not api_key and provider in PROVIDER_DEFAULT_KEYS:
        api_key = PROVIDER_DEFAULT_KEYS[provider]

    return {
        "model": model_name,
        "base_url": base_url,
        "api_key": api_key,
        "provider": provider,
    }


# System prompt shared by all backends
SYSTEM_PROMPT = (
    "You are a lithium metal battery data analysis specialist. "
    "You help researchers analyze battery cycling data, compare experiments, "
    "generate visualizations, and produce analysis reports. "
    "Use the available tools to load data, create plots, compare experiments, "
    "and generate reports. Always explain your analysis findings.\n\n"
    "Available data files:\n"
    "- data/examples/pec.csv (PEC format, SAFT VL43EFe battery, 3 cycles, ~16K data points)\n\n"
    "Single-experiment workflow:\n"
    "1. Load data with load_battery_data\n"
    "2. Use transform_data to compute cycle summaries\n"
    "3. Generate plots (capacity fade, CE, voltage curves)\n"
    "4. Generate a comprehensive report\n\n"
    "Multi-experiment comparison workflow:\n"
    "1. Load multiple datasets with load_battery_data\n"
    "2. Use list_experiments to see what's loaded\n"
    "3. Use compare_experiments to get a side-by-side metrics table\n"
    "4. Use overlay_plot to generate overlay comparison charts\n"
    "5. Use delta_analysis to compute voltage differences between two cells\n\n"
    "When comparing experiments, always highlight which design factors differ "
    "and correlate them with performance differences."
)
