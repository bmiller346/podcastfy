"""Local settings helpers for LitRPG task/UI configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

API_KEY_FIELDS = {
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
    "geminiapi": ("gemini_api_key", "GEMINI_API_KEY"),
    "geminimulti": ("gemini_api_key", "GEMINI_API_KEY"),
    "elevenlabs": ("elevenlabs_api_key", "ELEVENLABS_API_KEY"),
    "edge": ("edge_api_key", "EDGE_API_KEY"),
}


def load_litrpg_settings(settings_path: str | Path | None = None) -> dict[str, Any]:
    """Load optional local settings and overlay environment API keys."""
    settings = _load_settings_file(settings_path)
    for provider, (setting_key, env_key) in API_KEY_FIELDS.items():
        env_value = os.getenv(env_key)
        if env_value:
            settings[setting_key] = env_value
    return settings


def get_provider_api_key(
    provider: str, settings: Mapping[str, Any] | None = None
) -> str | None:
    """Return the API key for a provider from settings/env, if one is needed."""
    key_info = API_KEY_FIELDS.get(provider.lower())
    if not key_info:
        return None
    setting_key, env_key = key_info
    if settings and settings.get(setting_key):
        return str(settings[setting_key])
    return os.getenv(env_key)


def _load_settings_file(settings_path: str | Path | None) -> dict[str, Any]:
    if settings_path is None:
        path = Path("settings.local.json")
    else:
        path = Path(settings_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as settings_file:
        data = json.load(settings_file)
    if not isinstance(data, dict):
        raise ValueError("LitRPG settings file must contain a JSON object")
    return data
