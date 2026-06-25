"""Pure LitRPG chapter state delta extraction and merge helpers."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any


_ROLE_BLOCK_RE = re.compile(
    r"<(?P<role>[A-Za-z][A-Za-z0-9_-]*)(?:\s+[^>]*)?>(?P<text>.*?)</(?P=role)>",
    re.DOTALL,
)
_VOCALIZED_RE = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z0-9_-]{1,40})\s+has\s+vocalized\s*:\s*[\"'](?P<text>[^\"']+)[\"']",
    re.I,
)
_FLOOR_RE = re.compile(
    r"\bFLOOR\s+(?P<floor>\d+)\s+(?P<action>CLEARED|COMPLETE|UNLOCKED|ENTERED)\b",
    re.I,
)
_CANON_RE = re.compile(
    r"\b(?:OFFICIAL|DECLARED|RECORDED|ON FILE|UNPRECEDENTED|THIS IS NOW CANON|FOR THE RECORD)\b",
    re.I,
)
_STAT_RE = re.compile(
    r"^(?P<key>strength|dexterity|constitution|intelligence|wisdom|charisma|hp|mana|stamina|luck|agility)\s*(?:\+|-|:)?\s*(?P<value>-?\d+)?$",
    re.I,
)


def extract_state_delta(chapter_result: Mapping[str, Any]) -> dict[str, Any]:
    """Extract a serializable state delta from a LitRPG chapter result."""

    delta: dict[str, Any] = {
        "inventory_gained": [],
        "inventory_lost": [],
        "mechanics": {},
        "familiar_phrases": [],
        "announcer_notes": [],
    }
    scripts = _chapter_scripts(chapter_result)

    for terms in _gate_normalized_terms(chapter_result):
        _append_many(delta["inventory_gained"], _terms_for_keys(terms, ("loot_gain", "inventory_add")))
        _append_many(
            delta["inventory_lost"],
            _terms_for_keys(terms, ("item_consumed", "inventory_remove", "inventory_lost")),
        )
        _extract_mechanics_terms(delta["mechanics"], terms)

    for event in _gate_events(chapter_result):
        _extract_event(delta, event)

    for script in scripts:
        _append_many(delta["familiar_phrases"], _familiar_phrases(script))
        _append_many(delta["announcer_notes"], _announcer_notes(script))

    current_floor = _floor_advance("\n".join(scripts))
    if current_floor is not None:
        delta["current_floor"] = current_floor

    return _pruned_delta(delta)


def apply_delta_to_state(state: Any, delta: Mapping[str, Any]) -> Any:
    """Return a copy of state with delta applied, leaving both inputs untouched."""

    updated = copy.deepcopy(state)
    mechanics = delta.get("mechanics") if isinstance(delta.get("mechanics"), Mapping) else {}

    inventory = _read_inventory(updated)
    for item in _string_list(delta.get("inventory_lost")):
        inventory = _remove_normalized(inventory, item)
    for item in _string_list(delta.get("inventory_gained")):
        inventory = _append_unique(inventory, item)
    _write_inventory(updated, inventory)

    if "current_floor" in delta:
        _write_value(updated, "current_floor", delta.get("current_floor"))

    _merge_list_field(updated, "announcer_notes_log", _string_list(delta.get("announcer_notes")))
    familiar_key = _existing_familiar_phrase_key(updated) or "pedro_phrases"
    _merge_list_field(updated, familiar_key, _string_list(delta.get("familiar_phrases")))

    if mechanics:
        _apply_mechanics(updated, mechanics)

    return updated


def _extract_event(delta: dict[str, Any], event: Mapping[str, Any]) -> None:
    kind = str(event.get("kind") or "")
    display = str(event.get("display") or event.get("term") or "").strip()
    term = str(event.get("term") or display).strip()
    amount = _optional_int(event.get("amount"))
    mechanics = delta["mechanics"]

    if kind in {"loot_gain", "inventory_add"} and display:
        _append_unique_in_place(delta["inventory_gained"], display)
    elif kind in {"item_consumed", "inventory_remove", "inventory_lost"} and (term or display):
        _append_unique_in_place(delta["inventory_lost"], term or display)
    elif kind == "xp_gain" and amount is not None:
        mechanics["xp_gained"] = int(mechanics.get("xp_gained") or 0) + amount
    elif kind == "xp_total" and amount is not None:
        mechanics["xp"] = amount
    elif kind == "skill_learned" and display:
        _append_unique_in_mapping_list(mechanics, "skills_gained", display)
    elif kind in {"skill_lost", "skill_removed"} and (term or display):
        _append_unique_in_mapping_list(mechanics, "skills_lost", term or display)
    elif kind == "class_mention" and display:
        mechanics["class"] = display
    elif kind == "stat_mention" and display:
        _merge_stat_term(mechanics, display)


def _extract_mechanics_terms(mechanics: dict[str, Any], terms: Mapping[str, Any]) -> None:
    for level in _terms_for_keys(terms, ("level", "level_up")):
        value = _optional_int(re.search(r"-?\d+", level).group(0) if re.search(r"-?\d+", level) else level)
        if value is not None:
            mechanics["level"] = value
    for xp in _terms_for_keys(terms, ("xp_gained", "xp_gain")):
        value = _optional_int(re.search(r"-?\d+", xp).group(0) if re.search(r"-?\d+", xp) else xp)
        if value is not None:
            mechanics["xp_gained"] = int(mechanics.get("xp_gained") or 0) + value
    for class_name in _terms_for_keys(terms, ("class", "class_mention")):
        mechanics["class"] = class_name
    for skill in _terms_for_keys(terms, ("skills_gained", "skill_learned")):
        _append_unique_in_mapping_list(mechanics, "skills_gained", skill)
    for skill in _terms_for_keys(terms, ("skills_lost", "skill_lost", "skill_removed")):
        _append_unique_in_mapping_list(mechanics, "skills_lost", skill)
    for stat in _terms_for_keys(terms, ("stats", "stat_mention")):
        _merge_stat_term(mechanics, stat)


def _apply_mechanics(state: Any, mechanics: Mapping[str, Any]) -> None:
    character = _character_container(state)
    stats = _read_mapping(character, "stats")
    skills = _read_list(character, "skills")

    if "level" in mechanics:
        _write_nested_value(state, character, "level", mechanics.get("level"))
    if "class" in mechanics:
        key = "character_class" if _has_key_or_attr(character, "character_class") else "class"
        _write_nested_value(state, character, key, mechanics.get("class"))
    if "xp_gained" in mechanics:
        stats["xp"] = int(stats.get("xp") or 0) + int(mechanics.get("xp_gained") or 0)
    elif "xp" in mechanics:
        stats["xp"] = mechanics.get("xp")

    for key, value in _mapping_or_empty(mechanics.get("stats")).items():
        stats[str(key)] = value
    for skill in _string_list(mechanics.get("skills_lost")):
        skills = _remove_normalized(skills, skill)
    for skill in _string_list(mechanics.get("skills_gained")):
        skills = _append_unique(skills, skill)

    _write_nested_value(state, character, "stats", stats)
    _write_nested_value(state, character, "skills", skills)

    remaining_mechanics = _read_mapping(state, "mechanics")
    for key, value in mechanics.items():
        if key in {"level", "class", "xp", "xp_gained", "stats", "skills_gained", "skills_lost"}:
            continue
        if isinstance(value, Mapping):
            existing = remaining_mechanics.get(key) if isinstance(remaining_mechanics.get(key), Mapping) else {}
            remaining_mechanics[key] = _deep_merge(existing, value)
        else:
            remaining_mechanics[str(key)] = copy.deepcopy(value)
    if remaining_mechanics:
        _write_value(state, "mechanics", remaining_mechanics)


def _chapter_scripts(chapter_result: Mapping[str, Any]) -> list[str]:
    scripts = []
    for key in ("combined_script", "script", "revised_script"):
        value = chapter_result.get(key)
        if isinstance(value, str) and value.strip():
            scripts.append(value)
    for part in _parts(chapter_result):
        for key in ("revised_script", "script"):
            value = part.get(key)
            if isinstance(value, str) and value.strip():
                scripts.append(value)
    return scripts


def _gate_normalized_terms(chapter_result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    terms = []
    for gate_stage in _gate_stages(chapter_result):
        mechanics = gate_stage.get("mechanics")
        if isinstance(mechanics, Mapping) and isinstance(mechanics.get("normalized_terms"), Mapping):
            terms.append(mechanics["normalized_terms"])
        if isinstance(gate_stage.get("mechanics_terms"), Mapping):
            terms.append(gate_stage["mechanics_terms"])
    return terms


def _gate_events(chapter_result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    events = []
    for gate_stage in _gate_stages(chapter_result):
        mechanics = gate_stage.get("mechanics")
        if not isinstance(mechanics, Mapping) or not isinstance(mechanics.get("events"), list):
            continue
        events.extend(event for event in mechanics["events"] if isinstance(event, Mapping))
    return events


def _gate_stages(chapter_result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    stages = []
    for part in _parts(chapter_result):
        gate = part.get("gate")
        if not isinstance(gate, Mapping):
            continue
        for key in ("initial", "draft", "final"):
            value = gate.get(key)
            if isinstance(value, Mapping):
                stages.append(value)
    return stages


def _parts(chapter_result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    parts = chapter_result.get("parts")
    if not isinstance(parts, list):
        return []
    return [part for part in parts if isinstance(part, Mapping)]


def _familiar_phrases(script: str) -> list[str]:
    phrases = []
    for match in _ROLE_BLOCK_RE.finditer(script):
        role = match.group("role")
        text = _clean_phrase(match.group("text"))
        if text and _is_familiar_role(role):
            phrases.append(text)
    for match in _VOCALIZED_RE.finditer(script):
        text = _clean_phrase(match.group("text"))
        if text:
            phrases.append(text)
    return _dedupe(phrases)


def _announcer_notes(script: str) -> list[str]:
    notes = []
    for match in _ROLE_BLOCK_RE.finditer(script):
        if match.group("role").upper() != "SYSTEM_ANNOUNCER":
            continue
        text = _clean_phrase(match.group("text"))
        if text and _CANON_RE.search(text):
            notes.append(text)
    return _dedupe(notes)


def _floor_advance(script: str) -> int | None:
    valid: list[int] = []
    for match in _FLOOR_RE.finditer(script):
        floor = _optional_int(match.group("floor"))
        if floor is None:
            continue
        action = match.group("action").upper()
        valid.append(floor if action == "ENTERED" else floor + 1)
    return max(valid) if valid else None


def _is_familiar_role(role: str) -> bool:
    normalized = role.upper()
    return any(
        token in normalized
        for token in ("PEDRO", "FAMILIAR", "COMPANION", "MASCOT", "PET")
    )


def _terms_for_keys(terms: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    values = []
    for key in keys:
        values.extend(_string_list(terms.get(key)))
    return values


def _merge_stat_term(mechanics: dict[str, Any], term: str) -> None:
    match = _STAT_RE.match(term.strip())
    if not match:
        return
    stats = mechanics.setdefault("stats", {})
    value = _optional_int(match.group("value"))
    stats[match.group("key").lower()] = value if value is not None else term


def _read_inventory(state: Any) -> list[str]:
    character = _character_container(state)
    return _read_list(character, "inventory")


def _write_inventory(state: Any, inventory: list[str]) -> None:
    character = _character_container(state)
    _write_nested_value(state, character, "inventory", inventory)


def _character_container(state: Any) -> Any:
    if isinstance(state, Mapping) and isinstance(state.get("character"), Mapping):
        return state["character"]
    if hasattr(state, "character"):
        return getattr(state, "character")
    return state


def _merge_list_field(state: Any, key: str, values: list[str]) -> None:
    if not values:
        return
    merged = _read_list(state, key)
    for value in values:
        merged = _append_unique(merged, value)
    _write_value(state, key, merged)


def _existing_familiar_phrase_key(state: Any) -> str | None:
    for key in ("familiar_phrases", "pedro_phrases"):
        if _has_key_or_attr(state, key):
            return key
    return None


def _read_list(container: Any, key: str) -> list[str]:
    value = _read_value(container, key)
    if isinstance(value, list):
        return list(value)
    return _string_list(value)


def _read_mapping(container: Any, key: str) -> dict[str, Any]:
    value = _read_value(container, key)
    return copy.deepcopy(value) if isinstance(value, Mapping) else {}


def _read_value(container: Any, key: str) -> Any:
    if isinstance(container, Mapping):
        return container.get(key)
    return getattr(container, key, None)


def _write_nested_value(state: Any, container: Any, key: str, value: Any) -> None:
    if container is state and isinstance(state, Mapping) and "character" in state:
        state["character"][key] = copy.deepcopy(value)
    else:
        _write_value(container, key, value)


def _write_value(container: Any, key: str, value: Any) -> None:
    if isinstance(container, dict):
        container[key] = copy.deepcopy(value)
    elif hasattr(container, key):
        setattr(container, key, copy.deepcopy(value))


def _has_key_or_attr(container: Any, key: str) -> bool:
    if isinstance(container, Mapping):
        return key in container
    return hasattr(container, key)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _deep_merge(base: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in incoming.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(key).strip() for key in value if str(key).strip()]
    if isinstance(value, Sequence):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _append_many(values: list[str], incoming: Sequence[str]) -> None:
    for value in incoming:
        _append_unique_in_place(values, value)


def _append_unique(values: list[str], value: str) -> list[str]:
    updated = list(values)
    _append_unique_in_place(updated, value)
    return updated


def _append_unique_in_mapping_list(mapping: dict[str, Any], key: str, value: str) -> None:
    values = _string_list(mapping.get(key))
    _append_unique_in_place(values, value)
    mapping[key] = values


def _append_unique_in_place(values: list[str], value: str) -> None:
    normalized = _normalize(value)
    if normalized and normalized not in {_normalize(item) for item in values}:
        values.append(value)


def _remove_normalized(values: list[str], value: str) -> list[str]:
    normalized = _normalize(value)
    return [item for item in values if _normalize(item) != normalized]


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _clean_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n\"'")


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        _append_unique_in_place(deduped, value)
    return deduped


def _pruned_delta(delta: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in delta.items()
        if value not in ({}, [], None)
    }
