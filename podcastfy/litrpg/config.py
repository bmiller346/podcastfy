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
            "NARRATOR": {"voice": "en-US-GuyNeural", "effect": "light_room"},
            "HERO": {"voice": "en-US-EricNeural", "effect": "close_mic"},
            "SYSTEM": {"voice": "en-US-JennyNeural", "effect": "soft_chime"},
            "SIDEKICK": {"voice": "en-US-AriaNeural", "effect": "close_mic"},
            "BOSS": {"voice": "en-US-ChristopherNeural", "effect": "subtle_reverb"},
            "RIVAL": {"voice": "en-US-RogerNeural", "effect": "close_mic"},
            "MENTOR": {"voice": "en-US-SteffanNeural", "effect": "light_room"},
            "MERCHANT": {"voice": "en-US-BrianNeural", "effect": "close_mic"},
            "HEALER": {"voice": "en-US-AvaNeural", "effect": "close_mic"},
            "TANK": {"voice": "en-US-AndrewNeural", "effect": "close_mic"},
            "ROGUE": {"voice": "en-US-EmmaNeural", "effect": "close_mic"},
            "MAGE": {"voice": "en-US-MichelleNeural", "effect": "light_room"},
            "BEAST": {"voice": "en-US-ChristopherNeural", "effect": "subtle_reverb"},
            "MINION": {"voice": "en-US-BrianNeural", "effect": "radio"},
            "GUIDE": {"voice": "en-US-JennyNeural", "effect": "soft_chime"},
            "VILLAIN": {"voice": "en-US-ChristopherNeural", "effect": "subtle_reverb"},
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
            effects=dict(values.get("effects", defaults.effects)),
        )

    def voice_effects_metadata(self) -> dict[str, Any]:
        return {"voices": self.voices, "effects": self.effects}


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
