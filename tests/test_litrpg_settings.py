import json

from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings


def test_load_litrpg_settings_overlays_environment(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.local.json"
    settings_path.write_text(
        json.dumps({"openai_api_key": "from-file", "default_tts_provider": "openai"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    settings = load_litrpg_settings(settings_path)

    assert settings["openai_api_key"] == "from-env"
    assert settings["default_tts_provider"] == "openai"


def test_get_provider_api_key_uses_settings_or_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-env")

    assert get_provider_api_key("openai", {"openai_api_key": "openai-settings"}) == "openai-settings"
    assert get_provider_api_key("geminiapi", {}) == "gemini-env"
    assert get_provider_api_key("gemini", {}) == "gemini-env"
    assert get_provider_api_key("edge", {}) is None
