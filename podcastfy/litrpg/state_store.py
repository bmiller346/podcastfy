"""Persistent JSON storage for LitRPG series state."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from podcastfy.litrpg.models import CharacterState, QuestState, SeriesState

STATE_FILENAME = "series_state.json"
STATE_SCHEMA_VERSION = 1


def _state_path(series_dir: str | Path) -> Path:
    return Path(series_dir) / STATE_FILENAME


def _default_series_state(series_dir: str | Path) -> SeriesState:
    series_path = Path(series_dir)
    series_id = series_path.name or "default-series"
    return SeriesState(
        series_id=series_id,
        title=series_id.replace("-", " ").replace("_", " ").title(),
        episode_number=0,
        character=CharacterState(
            name="Hero",
            level=1,
            character_class="Adventurer",
            stats={},
            skills=[],
            inventory=[],
        ),
        schema_version=STATE_SCHEMA_VERSION,
        quests=[],
        current_location="",
        current_floor=None,
        memory=[],
        mechanics={},
        announcer_notes_log=[],
        pedro_phrases=[],
        crowd_reactions=[],
        sponsor_reactions=[],
    )


def _series_state_from_dict(data: dict[str, Any]) -> SeriesState:
    character_data = data.get("character") or {}
    quests_data = data.get("quests") or []
    return SeriesState(
        series_id=str(data.get("series_id", "default-series")),
        title=str(data.get("title", "Untitled Series")),
        episode_number=int(data.get("episode_number", 0)),
        character=CharacterState(
            name=str(character_data.get("name", "Hero")),
            level=int(character_data.get("level", 1)),
            character_class=str(character_data.get("character_class", "Adventurer")),
            stats=dict(character_data.get("stats") or {}),
            skills=list(character_data.get("skills") or []),
            inventory=list(character_data.get("inventory") or []),
        ),
        schema_version=int(data.get("schema_version", STATE_SCHEMA_VERSION)),
        quests=[
            QuestState(
                title=str(quest.get("title", "")),
                status=str(quest.get("status", "")),
                notes=str(quest.get("notes", "")),
            )
            for quest in quests_data
        ],
        current_location=str(data.get("current_location", "")),
        current_floor=_optional_int(data.get("current_floor")),
        memory=list(data.get("memory") or []),
        mechanics=dict(data.get("mechanics") or {}),
        announcer_notes_log=list(data.get("announcer_notes_log") or []),
        pedro_phrases=list(data.get("pedro_phrases") or []),
        crowd_reactions=_mapping_list(data.get("crowd_reactions")),
        sponsor_reactions=_mapping_list(data.get("sponsor_reactions")),
    )


def load_series_state(series_dir: str | Path) -> SeriesState:
    """Load series state, returning a sensible default when no state exists."""

    path = _state_path(series_dir)
    if not path.exists():
        return _default_series_state(series_dir)

    with path.open("r", encoding="utf-8") as state_file:
        data = json.load(state_file)
    return _series_state_from_dict(data)


def save_series_state(series_dir: str | Path, state: SeriesState) -> None:
    """Persist series state as deterministic, human-readable JSON."""

    path = _state_path(series_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as state_file:
        json.dump(asdict(state), state_file, ensure_ascii=True, indent=2, sort_keys=True)
        state_file.write("\n")


def next_episode_number(state: SeriesState) -> int:
    """Return the next episode number for a state object."""

    return state.episode_number + 1


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
