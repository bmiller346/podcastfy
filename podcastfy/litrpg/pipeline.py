"""High-level local LitRPG episode generation pipeline."""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
from typing import Any

from podcastfy.litrpg.config import LitRPGConfig, load_litrpg_config
from podcastfy.litrpg.effect_log import append_effect_log_entry
from podcastfy.litrpg.effect_log import build_effect_log_entry
from podcastfy.litrpg.effect_log import effect_log_path
from podcastfy.litrpg.engine import LitRPGEngine
from podcastfy.litrpg.episode_store import EpisodeStore
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.state_delta import apply_delta_to_state, extract_state_delta
from podcastfy.litrpg.state_store import load_series_state, next_episode_number
from podcastfy.litrpg.state_store import save_series_state


def generate_litrpg_audio_episode(
    *,
    premise: str,
    llm: Any,
    storage_dir: str | Path = "data/litrpg",
    series_id: str = "default-series",
    episode_number: int | None = None,
    render_audio: bool = True,
    tts: Any | None = None,
    tts_model: str | None = None,
    tts_api_key: str | None = None,
    tts_options: dict[str, Any] | None = None,
    conversation_config: dict[str, Any] | None = None,
    litrpg_config: LitRPGConfig | None = None,
    replay_existing: bool = True,
    settings_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate or replay one local LitRPG audio episode.

    The LLM and TTS objects are injectable so this can run in tests without
    external API calls.
    """
    config = litrpg_config or load_litrpg_config()
    settings = load_litrpg_settings(settings_path)
    provider_options = dict(tts_options or {})
    provider = str(
        provider_options.get("provider")
        or tts_model
        or settings.get("default_tts_provider")
        or "edge"
    )
    provider_model = str(
        provider_options.get("model")
        or settings.get("default_tts_model")
        or provider
    )
    audio_format = str(
        provider_options.get("format")
        or settings.get("default_tts_format")
        or "mp3"
    )
    storage_path = Path(storage_dir)
    series_dir = storage_path / "series" / series_id
    state = load_series_state(series_dir)
    state_payload = asdict(state)
    episode_store = EpisodeStore(storage_path)
    resolved_episode_number = episode_number or _resolve_episode_number(
        episode_store=episode_store,
        premise=premise,
        series_id=series_id,
        state_payload=state_payload,
        config=config,
        replay_existing=replay_existing,
        fallback_episode_number=next_episode_number(state),
    )
    replayable_bundle = _find_replayable_bundle(
        episode_store=episode_store,
        premise=premise,
        series_id=series_id,
        state_payload=state_payload,
        config=config,
        replay_existing=replay_existing,
        require_audio=render_audio,
    )
    renderer = None
    if render_audio and replayable_bundle is None:
        from podcastfy.litrpg.renderer import RoleScriptRenderer
        from podcastfy.text_to_speech import TextToSpeech

        renderer_tts = tts or TextToSpeech(
            model=provider,
            api_key=tts_api_key or get_provider_api_key(provider, settings),
            conversation_config=_conversation_config_with_tts_options(
                conversation_config,
                provider=provider,
                model=provider_model,
                audio_format=audio_format,
                provider_options=provider_options,
            ),
        )
        renderer = RoleScriptRenderer(tts=renderer_tts)

    engine = LitRPGEngine(
        llm=llm,
        state_store=lambda episode_number: state_payload,
        episode_store=episode_store,
        tts_renderer=renderer,
        config=config,
    )
    result = engine.generate_episode(
        premise=premise,
        series_id=series_id,
        episode_number=resolved_episode_number,
        replay_existing=replay_existing,
        require_audio_for_replay=render_audio,
    )

    if not result.get("replayed"):
        state = apply_delta_to_state(
            state,
            extract_state_delta(result, mechanics_context=_mechanics_context_from_state(state)),
        )
        state.episode_number = max(state.episode_number, resolved_episode_number)
        save_series_state(series_dir, state)
        if render_audio and result.get("audio_metadata"):
            _append_audio_render_effect(
                storage_path=storage_path,
                series_id=series_id,
                episode_number=resolved_episode_number,
                provider=provider,
                model=provider_model,
                input_payload={
                    "premise": premise,
                    "episode_number": resolved_episode_number,
                    "provider": provider,
                    "model": provider_model,
                },
                output_payload=result.get("audio_metadata"),
            )

    return result


def _mechanics_context_from_state(state: Any) -> dict[str, Any]:
    character = state.character
    return {
        "inventory": list(character.inventory),
        "skills": list(character.skills),
        "class": character.character_class,
        "level": character.level,
        "xp": dict(character.stats).get("xp"),
        "stats": dict(character.stats),
        "cooldowns": dict(state.mechanics.get("cooldowns") or {}),
    }


def _resolve_episode_number(
    *,
    episode_store: EpisodeStore,
    premise: str,
    series_id: str,
    state_payload: dict[str, Any],
    config: LitRPGConfig,
    replay_existing: bool,
    fallback_episode_number: int,
) -> int:
    if not replay_existing:
        return fallback_episode_number
    existing = episode_store.find_existing_bundle(
        {
            "series_id": series_id,
            "premise": premise,
            "state": state_payload,
            "config": _config_payload(config),
        }
    )
    if existing and existing.get("episode_number"):
        return int(existing["episode_number"])
    return fallback_episode_number


def _find_replayable_bundle(
    *,
    episode_store: EpisodeStore,
    premise: str,
    series_id: str,
    state_payload: dict[str, Any],
    config: LitRPGConfig,
    replay_existing: bool,
    require_audio: bool,
) -> dict[str, Any] | None:
    if not replay_existing:
        return None
    return episode_store.find_existing_bundle(
        {
            "series_id": series_id,
            "premise": premise,
            "state": state_payload,
            "config": _config_payload(config),
            "require_audio": require_audio,
        }
    )


def _config_payload(config: LitRPGConfig) -> dict[str, Any]:
    return {
        "minutes": config.minutes,
        "tone": config.tone,
        "episode_structure": config.episode_structure,
        "cast_roles": config.cast_roles,
        "voices": config.voices,
        "effects": config.effects,
    }


def _conversation_config_with_tts_options(
    conversation_config: dict[str, Any] | None,
    *,
    provider: str,
    model: str,
    audio_format: str,
    provider_options: dict[str, Any],
) -> dict[str, Any]:
    config = dict(conversation_config or {})
    tts_config = dict(config.get("text_to_speech") or {})
    tts_config["default_tts_model"] = provider
    tts_config["audio_format"] = audio_format
    provider_config = dict(tts_config.get(provider) or {})
    provider_config["model"] = model
    if provider_options.get("voices"):
        provider_config["default_voices"] = provider_options["voices"]
    tts_config[provider] = provider_config
    config["text_to_speech"] = tts_config
    return config


def _append_audio_render_effect(
    *,
    storage_path: Path,
    series_id: str,
    episode_number: int,
    provider: str,
    model: str,
    input_payload: Any,
    output_payload: Any,
) -> None:
    entry = build_effect_log_entry(
        series_id=series_id,
        book_number=1,
        chapter_number=episode_number,
        stage="audio_render",
        input_payload=input_payload,
        output_payload=output_payload,
        provider=provider,
        model=model,
        status="committed",
    )
    append_effect_log_entry(effect_log_path(storage_path, series_id), entry)
