"""Continuity bible storage and prompt summaries for LitRPG series."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BIBLE_FILENAME = "story_bible.json"
BIBLE_SCHEMA_VERSION = 1


@dataclass(slots=True)
class CharacterBibleEntry:
    """Continuity facts for a character, separate from game mechanics."""

    name: str
    aliases: list[str] = field(default_factory=list)
    wounds: list[str] = field(default_factory=list)
    traumas: list[str] = field(default_factory=list)
    running_jokes: list[str] = field(default_factory=list)
    rivalries: list[str] = field(default_factory=list)
    unresolved_promises: list[str] = field(default_factory=list)
    favorite_insults: list[str] = field(default_factory=list)
    never_contradict_facts: list[str] = field(default_factory=list)
    voice_rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StoryBible:
    """Serializable continuity record for a LitRPG series."""

    series_id: str
    schema_version: int = BIBLE_SCHEMA_VERSION
    premise: str = ""
    never_contradict_facts: list[str] = field(default_factory=list)
    unresolved_threads: list[str] = field(default_factory=list)
    timeline_notes: list[str] = field(default_factory=list)
    characters: dict[str, CharacterBibleEntry] = field(default_factory=dict)


def story_bible_path(storage_dir: str | Path, series_id: str) -> Path:
    """Return the per-series bible path under a LitRPG storage root."""

    return Path(storage_dir) / "series" / str(series_id) / BIBLE_FILENAME


def load_story_bible(storage_dir: str | Path, series_id: str) -> StoryBible:
    """Load a story bible, returning a safe empty default when absent."""

    path = story_bible_path(storage_dir, series_id)
    if not path.exists():
        return StoryBible(series_id=str(series_id))

    with path.open("r", encoding="utf-8") as bible_file:
        data = json.load(bible_file)
    if not isinstance(data, dict):
        return StoryBible(series_id=str(series_id))
    return story_bible_from_dict(data, fallback_series_id=str(series_id))


def save_story_bible(storage_dir: str | Path, bible: StoryBible) -> None:
    """Persist a story bible as deterministic, human-readable JSON."""

    path = story_bible_path(storage_dir, bible.series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as bible_file:
        json.dump(asdict(bible), bible_file, ensure_ascii=True, indent=2, sort_keys=True)
        bible_file.write("\n")


def story_bible_from_dict(
    data: dict[str, Any], fallback_series_id: str = "default-series"
) -> StoryBible:
    """Build a StoryBible from loose JSON without requiring every field."""

    characters = data.get("characters") or {}
    if isinstance(characters, list):
        character_entries = {
            str(item.get("name") or ""): character_bible_entry_from_dict(item)
            for item in characters
            if isinstance(item, dict) and str(item.get("name") or "")
        }
    elif isinstance(characters, dict):
        character_entries = {
            str(key): character_bible_entry_from_dict(value, fallback_name=str(key))
            for key, value in characters.items()
            if isinstance(value, dict)
        }
    else:
        character_entries = {}

    return StoryBible(
        series_id=str(data.get("series_id") or fallback_series_id),
        schema_version=int(data.get("schema_version") or BIBLE_SCHEMA_VERSION),
        premise=str(data.get("premise") or ""),
        never_contradict_facts=_string_list(data.get("never_contradict_facts")),
        unresolved_threads=_string_list(data.get("unresolved_threads")),
        timeline_notes=_string_list(data.get("timeline_notes")),
        characters=character_entries,
    )


def character_bible_entry_from_dict(
    data: dict[str, Any], fallback_name: str = ""
) -> CharacterBibleEntry:
    """Build a character bible entry from loose JSON."""

    return CharacterBibleEntry(
        name=str(data.get("name") or fallback_name),
        aliases=_string_list(data.get("aliases")),
        wounds=_string_list(data.get("wounds")),
        traumas=_string_list(data.get("traumas")),
        running_jokes=_string_list(data.get("running_jokes")),
        rivalries=_string_list(data.get("rivalries")),
        unresolved_promises=_string_list(data.get("unresolved_promises")),
        favorite_insults=_string_list(data.get("favorite_insults")),
        never_contradict_facts=_string_list(data.get("never_contradict_facts")),
        voice_rules=_string_list(data.get("voice_rules")),
        notes=_string_list(data.get("notes")),
    )


def merge_story_bible_updates(
    bible: StoryBible, updates: StoryBible | dict[str, Any]
) -> StoryBible:
    """Apply extracted continuity updates without clearing existing facts."""

    update_bible = (
        updates
        if isinstance(updates, StoryBible)
        else story_bible_from_dict(updates, fallback_series_id=bible.series_id)
    )

    if update_bible.premise:
        bible.premise = update_bible.premise
    _extend_unique(bible.never_contradict_facts, update_bible.never_contradict_facts)
    _extend_unique(bible.unresolved_threads, update_bible.unresolved_threads)
    _extend_unique(bible.timeline_notes, update_bible.timeline_notes)

    for _, update_entry in update_bible.characters.items():
        existing_key = _find_character_key(bible, update_entry)
        if existing_key is None:
            bible.characters[update_entry.name] = update_entry
            continue
        _merge_character_entry(bible.characters[existing_key], update_entry)

    return bible


def format_story_bible_summary(bible: StoryBible, max_characters: int = 6) -> str:
    """Return compact continuity context suitable for prompt injection."""

    lines = [f"Story Bible ({bible.series_id})"]
    if bible.premise:
        lines.append(f"Premise: {bible.premise}")
    if bible.never_contradict_facts:
        lines.append(
            "Never contradict: "
            + "; ".join(_compact_items(bible.never_contradict_facts, limit=5))
        )
    if bible.unresolved_threads:
        lines.append(
            "Unresolved threads: "
            + "; ".join(_compact_items(bible.unresolved_threads, limit=4))
        )
    if bible.timeline_notes:
        lines.append(
            "Timeline: " + "; ".join(_compact_items(bible.timeline_notes, limit=4))
        )

    for entry in list(bible.characters.values())[:max_characters]:
        facts = _character_summary_facts(entry)
        if facts:
            lines.append(f"{entry.name}: " + " | ".join(facts))

    if len(bible.characters) > max_characters:
        remaining = len(bible.characters) - max_characters
        lines.append(f"... plus {remaining} more character(s).")

    return "\n".join(lines)


def _merge_character_entry(
    existing: CharacterBibleEntry, update: CharacterBibleEntry
) -> None:
    if update.name and existing.name != update.name:
        _extend_unique(existing.aliases, [update.name])
    _extend_unique(existing.aliases, update.aliases)
    _extend_unique(existing.wounds, update.wounds)
    _extend_unique(existing.traumas, update.traumas)
    _extend_unique(existing.running_jokes, update.running_jokes)
    _extend_unique(existing.rivalries, update.rivalries)
    _extend_unique(existing.unresolved_promises, update.unresolved_promises)
    _extend_unique(existing.favorite_insults, update.favorite_insults)
    _extend_unique(existing.never_contradict_facts, update.never_contradict_facts)
    _extend_unique(existing.voice_rules, update.voice_rules)
    _extend_unique(existing.notes, update.notes)


def _find_character_key(
    bible: StoryBible, update_entry: CharacterBibleEntry
) -> str | None:
    names = {
        update_entry.name.casefold(),
        *[alias.casefold() for alias in update_entry.aliases],
    }
    for key, entry in bible.characters.items():
        existing_names = {key.casefold(), entry.name.casefold()}
        existing_names.update(alias.casefold() for alias in entry.aliases)
        if names & existing_names:
            return key
    return None


def _character_summary_facts(entry: CharacterBibleEntry) -> list[str]:
    facts: list[str] = []
    for label, values in [
        ("facts", entry.never_contradict_facts),
        ("voice", entry.voice_rules),
        ("wounds", entry.wounds),
        ("trauma", entry.traumas),
        ("jokes", entry.running_jokes),
        ("rivals", entry.rivalries),
        ("promises", entry.unresolved_promises),
        ("insults", entry.favorite_insults),
    ]:
        if values:
            facts.append(f"{label}: " + "; ".join(_compact_items(values, limit=2)))
    return facts[:4]


def _compact_items(items: list[str], limit: int) -> list[str]:
    compact = [item for item in items if item][:limit]
    if len(items) > limit:
        compact.append(f"+{len(items) - limit} more")
    return compact


def _extend_unique(target: list[str], values: list[str]) -> None:
    seen = {item.casefold() for item in target}
    for value in values:
        normalized = value.strip()
        if not normalized or normalized.casefold() in seen:
            continue
        target.append(normalized)
        seen.add(normalized.casefold())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
