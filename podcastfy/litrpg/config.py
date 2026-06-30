"""Default configuration helpers for the LitRPG serial engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from podcastfy.litrpg.production import DEFAULT_CAST_ROLES

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in bare envs
    yaml = None


DEFAULT_CONFIG_FILE = "litrpg_config.yaml"


@dataclass(frozen=True)
class LitRPGConfig:
    """Small config object for prompt and orchestration defaults."""

    minutes: int = 18
    tone: str = "cinematic, witty, high-stakes, audio-first"
    episode_structure: list[str] = field(
        default_factory=lambda: [
            "cold_open_cliff_recap",
            "quest_hook",
            "combat_or_skill_trial",
            "loot_xp_class_update",
            "character_callback",
            "boss_reversal",
            "cliffhanger",
        ]
    )
    cast_roles: dict[str, str] = field(
        default_factory=lambda: {
            **DEFAULT_CAST_ROLES,
        }
    )
    voices: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "NARRATOR": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "ballad",
            },
            "HERO": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "ash",
            },
            "SYSTEM": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "onyx",
            },
            "SIDEKICK": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "coral",
            },
            "BOSS": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "echo",
            },
            "RIVAL": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "verse",
            },
            "MENTOR": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "sage",
            },
            "MERCHANT": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "fable",
            },
            "HEALER": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "shimmer",
            },
            "TANK": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "echo",
            },
            "ROGUE": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "nova",
            },
            "MAGE": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "marin",
            },
            "BEAST": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "onyx",
            },
            "MINION": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "alloy",
            },
            "GUIDE": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "alloy",
            },
            "VILLAIN": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "onyx",
            },
        }
    )
    voice_processing: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "SYSTEM": {"chain": "announcer_broadcast", "pitch_shift_semitones": -1.5},
            "NARRATOR": {"chain": "warm_narration"},
            "HERO": {"chain": "none"},
        }
    )
    effects: dict[str, str] = field(
        default_factory=lambda: {
            "notification": "short crystalline ping before SYSTEM updates",
            "loot_drop": "small rising sparkle under the reveal",
            "level_up": "confident two-note flourish",
            "cliffhanger": "low pulse, then abrupt silence",
        }
    )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "LitRPGConfig":
        if not values:
            return cls()
        defaults = cls()
        return cls(
            minutes=int(values.get("minutes", defaults.minutes)),
            tone=str(values.get("tone", defaults.tone)),
            episode_structure=list(
                values.get("episode_structure", defaults.episode_structure)
            ),
            cast_roles=dict(values.get("cast_roles", defaults.cast_roles)),
            voices=dict(values.get("voices", defaults.voices)),
            voice_processing=dict(
                values.get("voice_processing", defaults.voice_processing)
            ),
            effects=dict(values.get("effects", defaults.effects)),
        )

    def voice_effects_metadata(self) -> dict[str, Any]:
        return {
            "voices": self.voices,
            "voice_processing": self.voice_processing,
            "effects": self.effects,
        }


def get_default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / DEFAULT_CONFIG_FILE


def load_litrpg_config(config_path: str | Path | None = None) -> LitRPGConfig:
    """Load LitRPG config from YAML, falling back to dataclass defaults."""
    path = Path(config_path) if config_path else get_default_config_path()
    if not path.exists():
        return LitRPGConfig()
    if yaml is None:
        if config_path is None:
            return LitRPGConfig()
        raise ModuleNotFoundError("PyYAML is required to load custom LitRPG config")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return LitRPGConfig.from_mapping(data)
