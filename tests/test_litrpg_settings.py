import json

from podcastfy.litrpg.settings import (
    get_provider_api_key,
    load_litrpg_settings,
    redacted_litrpg_settings_status,
    resolve_settings_path,
    save_litrpg_settings,
)


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


def test_save_litrpg_settings_writes_allowed_fields_to_local_path(tmp_path):
    settings_path = tmp_path / "data" / "litrpg" / "settings.json"

    save_litrpg_settings(
        {
            "openai_api_key": "sk-test",
            "gemini_api_key": "",
            "default_generation_provider": "openai",
            "default_model": "gpt-5.5",
            "default_tts_provider": "geminiapi",
            "default_tts_model": "gemini-3.1-flash-tts-preview",
            "default_tts_format": "wav",
            "unexpected": "ignored",
        },
        settings_path,
    )

    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert stored == {
        "default_generation_provider": "openai",
        "default_model": "gpt-5.5",
        "default_tts_provider": "geminiapi",
        "default_tts_format": "wav",
        "default_tts_model": "gemini-3.1-flash-tts-preview",
        "openai_api_key": "sk-test",
    }


def test_redacted_status_never_returns_plaintext_keys(monkeypatch, tmp_path):
    settings_path = tmp_path / "data" / "litrpg" / "settings.json"
    save_litrpg_settings(
        {
            "openai_api_key": "file-secret",
            "default_model": "gpt-5.5",
        },
        settings_path,
    )
    monkeypatch.setenv("GEMINI_API_KEY", "env-secret")

    status = redacted_litrpg_settings_status(settings_path)
    encoded = json.dumps(status)

    assert status["api_keys"]["openai"]["file"] is True
    assert status["api_keys"]["openai"]["value"] == "redacted"
    assert status["api_keys"]["gemini"]["env"] is True
    assert status["defaults"]["default_model"] == "gpt-5.5"
    assert "file-secret" not in encoded
    assert "env-secret" not in encoded


def test_save_litrpg_settings_keeps_blank_secrets_but_clears_blank_defaults(tmp_path):
    settings_path = tmp_path / "data" / "litrpg" / "settings.json"
    save_litrpg_settings(
        {
            "openai_api_key": "file-secret",
            "default_model": "gpt-5.5",
            "default_tts_format": "mp3",
        },
        settings_path,
    )

    save_litrpg_settings(
        {
            "openai_api_key": "",
            "default_model": "",
            "default_tts_format": "",
        },
        settings_path,
    )

    stored = json.loads(settings_path.read_text(encoding="utf-8"))

    assert stored == {"openai_api_key": "file-secret"}


def test_resolve_settings_path_uses_env_override(monkeypatch, tmp_path):
    settings_path = tmp_path / "custom-settings.json"
    monkeypatch.setenv("LITRPG_SETTINGS_PATH", str(settings_path))

    assert resolve_settings_path() == settings_path
