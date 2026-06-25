"""Local settings helpers for LitRPG task/UI configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "data" / "litrpg" / "settings.json"
LEGACY_SETTINGS_PATH = PROJECT_ROOT / "settings.local.json"
SETTINGS_PATH_ENV = "LITRPG_SETTINGS_PATH"

API_KEY_FIELDS = {
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
    "geminiapi": ("gemini_api_key", "GEMINI_API_KEY"),
    "geminimulti": ("gemini_api_key", "GEMINI_API_KEY"),
    "elevenlabs": ("elevenlabs_api_key", "ELEVENLABS_API_KEY"),
    "edge": ("edge_api_key", "EDGE_API_KEY"),
}

API_KEY_SETTING_KEYS = tuple(dict.fromkeys(value[0] for value in API_KEY_FIELDS.values()))
DEFAULT_SETTING_KEYS = (
    "default_generation_provider",
    "default_tts_provider",
    "default_model",
    "default_tts_model",
    "default_tts_format",
)
ALLOWED_SETTING_KEYS = {*API_KEY_SETTING_KEYS, *DEFAULT_SETTING_KEYS}
REDACTED_VALUE = "redacted"


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


def resolve_settings_path(settings_path: str | Path | None = None) -> Path:
    """Resolve the local settings path used by the UI and task runner."""
    if settings_path is not None:
        return Path(settings_path)
    env_path = os.getenv(SETTINGS_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_SETTINGS_PATH


def settings_file_exists(settings_path: str | Path | None = None) -> bool:
    """Return whether the active settings file exists, including legacy fallback."""
    return _existing_settings_path(settings_path) is not None


def save_litrpg_settings(
    payload: Mapping[str, Any], settings_path: str | Path | None = None
) -> dict[str, Any]:
    """Persist allowed local settings without echoing secrets."""
    path = resolve_settings_path(settings_path)
    existing = _load_settings_file(path)
    next_settings = {
        key: value for key, value in existing.items() if key in ALLOWED_SETTING_KEYS
    }
    for key, value in payload.items():
        if key not in ALLOWED_SETTING_KEYS:
            continue
        if value is None:
            next_settings.pop(key, None)
            continue
        if value == "":
            if key in API_KEY_SETTING_KEYS:
                continue
            next_settings.pop(key, None)
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Unsupported settings value for {key}")
        next_settings[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as settings_file:
        json.dump(next_settings, settings_file, ensure_ascii=True, indent=2, sort_keys=True)
        settings_file.write("\n")
    return next_settings


def redacted_litrpg_settings_status(
    settings_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return local settings status without returning plaintext API keys."""
    path = resolve_settings_path(settings_path)
    file_settings = _load_settings_file(path)
    api_keys: dict[str, dict[str, Any]] = {}
    for provider, (setting_key, env_key) in sorted(API_KEY_FIELDS.items()):
        if provider in api_keys:
            continue
        file_configured = bool(file_settings.get(setting_key))
        env_configured = bool(os.getenv(env_key))
        api_keys[provider] = {
            "setting_key": setting_key,
            "env_key": env_key,
            "file": file_configured,
            "env": env_configured,
            "configured": file_configured or env_configured,
            "value": REDACTED_VALUE if file_configured or env_configured else "",
        }
    defaults = {
        key: file_settings.get(key, "")
        for key in sorted(DEFAULT_SETTING_KEYS)
    }
    return {
        "settings_path": str(path),
        "exists": path.exists(),
        "api_keys": api_keys,
        "defaults": defaults,
    }


def _load_settings_file(settings_path: str | Path | None) -> dict[str, Any]:
    path = _existing_settings_path(settings_path)
    if path is None:
        return {}
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as settings_file:
        data = json.load(settings_file)
    if not isinstance(data, dict):
        raise ValueError("LitRPG settings file must contain a JSON object")
    return data


def _existing_settings_path(settings_path: str | Path | None) -> Path | None:
    path = resolve_settings_path(settings_path)
    if path.exists():
        return path
    if settings_path is None and not os.getenv(SETTINGS_PATH_ENV) and LEGACY_SETTINGS_PATH.exists():
        return LEGACY_SETTINGS_PATH
    return None
