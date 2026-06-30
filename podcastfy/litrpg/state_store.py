"""Persistent JSON storage for LitRPG series state."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from podcastfy.litrpg.models import CharacterState, SeriesState, series_state_from_mapping

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
    return series_state_from_mapping(data, default_schema_version=STATE_SCHEMA_VERSION)


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
