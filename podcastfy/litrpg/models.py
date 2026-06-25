"""Typed storage models for LitRPG series state and episode artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CharacterState:
    name: str
    level: int
    character_class: str
    stats: dict[str, Any] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QuestState:
    title: str
    status: str
    notes: str


@dataclass(slots=True)
class SeriesState:
    series_id: str
    title: str
    episode_number: int
    character: CharacterState
    schema_version: int = 1
    quests: list[QuestState] = field(default_factory=list)
    current_location: str = ""
    memory: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EpisodeConfig:
    prompt: str
    minutes: int
    tone: str
    cast: dict[str, Any] = field(default_factory=dict)
    tts_model: str | None = None
    model_version: str | None = None


@dataclass(slots=True)
class ScriptLine:
    role: str
    text: str
    style: str | None = None


@dataclass(slots=True)
class EpisodeBundle:
    series_id: str
    episode_id: str
    episode_number: int
    cache_key: str
    prompt: str
    config: EpisodeConfig
    paths: dict[str, str] = field(default_factory=dict)
