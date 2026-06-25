"""Dependency-injected orchestration skeleton for LitRPG audio episodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Callable, Mapping

from .config import LitRPGConfig, load_litrpg_config
from .prompts import build_audio_script_prompt, build_episode_outline_prompt


@dataclass
class LitRPGEpisodeBundle:
    series_id: str
    episode_id: str
    episode_number: int
    premise: str
    outline: str
    script: str
    state: Mapping[str, Any]
    config: Mapping[str, Any]
    storage_metadata: Mapping[str, Any] | None = None
    audio_metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "episode_id": self.episode_id,
            "episode_number": self.episode_number,
            "premise": self.premise,
            "outline": self.outline,
            "script": self.script,
            "state": _to_mapping(self.state),
            "config": dict(self.config),
            "storage_metadata": dict(self.storage_metadata or {}),
            "audio_metadata": dict(self.audio_metadata or {}),
        }


class LitRPGEngine:
    """Small orchestrator that wires prompt generation, storage, and TTS."""

    def __init__(
        self,
        *,
        llm: Any,
        state_store: Any | None = None,
        episode_store: Any | None = None,
        tts_renderer: Any | None = None,
        config: LitRPGConfig | None = None,
    ) -> None:
        self.llm = llm
        self.state_store = state_store
        self.episode_store = episode_store
        self.tts_renderer = tts_renderer
        self.config = config or load_litrpg_config()

    def generate_episode(
        self,
        *,
        premise: str,
        series_id: str = "default-series",
        episode_number: int = 1,
        episode_id: str | None = None,
        callbacks: list[str] | None = None,
        replay_existing: bool = True,
        require_audio_for_replay: bool = False,
    ) -> dict[str, Any]:
        """Generate, persist, and optionally render one LitRPG audio episode."""
        resolved_episode_id = episode_id or f"episode-{episode_number:04d}"
        state = self._load_state(episode_number=episode_number) or {}
        config_payload = self._config_payload()
        replay_payload = {
            "series_id": series_id,
            "episode_id": resolved_episode_id,
            "episode_number": episode_number,
            "premise": premise,
            "state": _to_mapping(state),
            "config": config_payload,
            "require_audio": require_audio_for_replay,
        }
        if replay_existing:
            existing = self._find_existing_bundle(replay_payload)
            if existing is not None:
                return {
                    **replay_payload,
                    "episode_id": existing.get("episode_id", resolved_episode_id),
                    "episode_number": existing.get("episode_number", episode_number),
                    "outline": "",
                    "script": "",
                    "storage_metadata": existing,
                    "audio_metadata": dict(existing.get("audio_metadata") or {}),
                    "replayed": True,
                }

        outline_prompt = build_episode_outline_prompt(
            premise=premise,
            episode_number=episode_number,
            minutes=self.config.minutes,
            tone=self.config.tone,
            cast_roles=self.config.cast_roles,
            prior_state=state,
            callbacks=callbacks,
        )
        outline = self._generate_text(outline_prompt, stage="outline")

        script_prompt = build_audio_script_prompt(
            outline=outline,
            episode_number=episode_number,
            minutes=self.config.minutes,
            tone=self.config.tone,
            cast_roles=self.config.cast_roles,
            voice_effects=self.config.voice_effects_metadata(),
            prior_state=state,
        )
        script = self._generate_text(script_prompt, stage="script")

        bundle = LitRPGEpisodeBundle(
            series_id=series_id,
            episode_id=resolved_episode_id,
            episode_number=episode_number,
            premise=premise,
            outline=outline,
            script=script,
            state=_to_mapping(state),
            config=config_payload,
        )

        storage_metadata = self._save_bundle(bundle)
        bundle.storage_metadata = storage_metadata
        audio_metadata = self._render_tts(bundle) if self.tts_renderer else None
        bundle.audio_metadata = audio_metadata
        return bundle.to_dict()

    def _config_payload(self) -> dict[str, Any]:
        return {
            "minutes": self.config.minutes,
            "tone": self.config.tone,
            "episode_structure": self.config.episode_structure,
            "cast_roles": self.config.cast_roles,
            "voices": self.config.voices,
            "effects": self.config.effects,
        }

    def _load_state(self, *, episode_number: int) -> Mapping[str, Any] | None:
        if not self.state_store:
            return None
        if hasattr(self.state_store, "load_state"):
            return self.state_store.load_state(episode_number=episode_number)
        if hasattr(self.state_store, "load"):
            return self.state_store.load(episode_number=episode_number)
        if callable(self.state_store):
            return self.state_store(episode_number=episode_number)
        return None

    def _find_existing_bundle(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        if not self.episode_store:
            return None
        if hasattr(self.episode_store, "find_existing_bundle"):
            return self.episode_store.find_existing_bundle(dict(payload))
        return None

    def _save_bundle(
        self, bundle: LitRPGEpisodeBundle
    ) -> Mapping[str, Any] | None:
        if not self.episode_store:
            return None
        payload = bundle.to_dict()
        if hasattr(self.episode_store, "save_bundle"):
            return self.episode_store.save_bundle(payload)
        if hasattr(self.episode_store, "save"):
            return self.episode_store.save(payload)
        if callable(self.episode_store):
            return self.episode_store(payload)
        return None

    def _render_tts(
        self, bundle: LitRPGEpisodeBundle
    ) -> Mapping[str, Any] | None:
        payload = bundle.to_dict()
        if hasattr(self.tts_renderer, "render_episode"):
            return self.tts_renderer.render_episode(payload)
        if hasattr(self.tts_renderer, "render"):
            return self.tts_renderer.render(payload)
        if callable(self.tts_renderer):
            return self.tts_renderer(payload)
        return None

    def _generate_text(self, prompt: str, *, stage: str) -> str:
        generator = self.llm
        if hasattr(generator, "generate"):
            return str(generator.generate(prompt=prompt, stage=stage))
        if hasattr(generator, "generate_text"):
            return str(generator.generate_text(prompt=prompt, stage=stage))
        if callable(generator):
            return str(_call_with_stage(generator, prompt, stage))
        raise TypeError("llm must be callable or expose generate/generate_text")


def _call_with_stage(
    generator: Callable[..., Any], prompt: str, stage: str
) -> Any:
    try:
        return generator(prompt=prompt, stage=stage)
    except TypeError:
        return generator(prompt)


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": value}


def generate_litrpg_episode(**kwargs: Any) -> dict[str, Any]:
    """Convenience wrapper for callers that prefer a function API."""
    engine_kwargs = {
        key: kwargs.pop(key)
        for key in ["llm", "state_store", "episode_store", "tts_renderer", "config"]
        if key in kwargs
    }
    return LitRPGEngine(**engine_kwargs).generate_episode(**kwargs)
