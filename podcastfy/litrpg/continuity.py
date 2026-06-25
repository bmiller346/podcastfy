"""Continuity, emotional arc, and world-register helpers for LitRPG series."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

CONTINUITY_LEDGER_FILENAME = "continuity_ledger.json"
EMOTIONAL_ARCS_FILENAME = "emotional_arcs.json"
WORLD_REGISTER_FILENAME = "world_register.json"
CONTINUITY_SCHEMA_VERSION = 1


@dataclass(slots=True)
class LedgerEntry:
    text: str
    chapter: int | None = None
    phase: str = ""
    floor: int | None = None
    location: str = ""
    characters: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContinuityLedger:
    series_id: str
    schema_version: int = CONTINUITY_SCHEMA_VERSION
    notable_moments: list[LedgerEntry] = field(default_factory=list)
    running_gags: list[LedgerEntry] = field(default_factory=list)
    motifs: list[LedgerEntry] = field(default_factory=list)
    world_details: list[LedgerEntry] = field(default_factory=list)
    emotional_beats: list[LedgerEntry] = field(default_factory=list)
    callbacks: list[LedgerEntry] = field(default_factory=list)


@dataclass(slots=True)
class EmotionalArc:
    character: str
    wound: str = ""
    current_coping_mode: str = ""
    relationships: dict[str, str] = field(default_factory=dict)
    last_significant_emotional_event: str = ""
    beats: list[LedgerEntry] = field(default_factory=list)


@dataclass(slots=True)
class EmotionalArcRegistry:
    series_id: str
    schema_version: int = CONTINUITY_SCHEMA_VERSION
    characters: dict[str, EmotionalArc] = field(default_factory=dict)


@dataclass(slots=True)
class LocationDetail:
    name: str
    detail: str
    floor: int | None = None
    phase: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EntityEcology:
    entity: str
    detail: str
    floor: int | None = None
    location: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuleEntry:
    rule: str
    detail: str = ""
    floor: int | None = None
    phase: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EconomyAnchor:
    name: str
    detail: str
    floor: int | None = None
    location: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorldRegister:
    series_id: str
    schema_version: int = CONTINUITY_SCHEMA_VERSION
    locations: list[LocationDetail] = field(default_factory=list)
    entity_ecology: list[EntityEcology] = field(default_factory=list)
    rules: list[RuleEntry] = field(default_factory=list)
    economy_anchors: list[EconomyAnchor] = field(default_factory=list)


def continuity_ledger_from_dict(data: Mapping[str, Any]) -> ContinuityLedger:
    return ContinuityLedger(
        series_id=str(data.get("series_id") or "default-series"),
        schema_version=int(data.get("schema_version") or CONTINUITY_SCHEMA_VERSION),
        notable_moments=_ledger_entries(data.get("notable_moments")),
        running_gags=_ledger_entries(data.get("running_gags")),
        motifs=_ledger_entries(data.get("motifs")),
        world_details=_ledger_entries(data.get("world_details")),
        emotional_beats=_ledger_entries(data.get("emotional_beats")),
        callbacks=_ledger_entries(data.get("callbacks")),
    )


def emotional_arc_registry_from_dict(data: Mapping[str, Any]) -> EmotionalArcRegistry:
    raw_characters = data.get("characters")
    characters: dict[str, EmotionalArc] = {}
    if isinstance(raw_characters, Mapping):
        for name, value in raw_characters.items():
            if isinstance(value, Mapping):
                arc = emotional_arc_from_dict(value, fallback_character=str(name))
                characters[_character_key(arc.character)] = arc
    return EmotionalArcRegistry(
        series_id=str(data.get("series_id") or "default-series"),
        schema_version=int(data.get("schema_version") or CONTINUITY_SCHEMA_VERSION),
        characters=characters,
    )


def emotional_arc_from_dict(
    data: Mapping[str, Any], *, fallback_character: str = ""
) -> EmotionalArc:
    return EmotionalArc(
        character=str(data.get("character") or fallback_character or "Unknown"),
        wound=str(data.get("wound") or ""),
        current_coping_mode=str(data.get("current_coping_mode") or ""),
        relationships={
            str(key): str(value)
            for key, value in (data.get("relationships") or {}).items()
        }
        if isinstance(data.get("relationships"), Mapping)
        else {},
        last_significant_emotional_event=str(
            data.get("last_significant_emotional_event") or ""
        ),
        beats=_ledger_entries(data.get("beats")),
    )


def world_register_from_dict(data: Mapping[str, Any]) -> WorldRegister:
    return WorldRegister(
        series_id=str(data.get("series_id") or "default-series"),
        schema_version=int(data.get("schema_version") or CONTINUITY_SCHEMA_VERSION),
        locations=[
            _location_detail(item)
            for item in _mapping_items(data.get("locations"))
        ],
        entity_ecology=[
            _entity_ecology(item)
            for item in _mapping_items(data.get("entity_ecology"))
        ],
        rules=[_rule_entry(item) for item in _mapping_items(data.get("rules"))],
        economy_anchors=[
            _economy_anchor(item)
            for item in _mapping_items(data.get("economy_anchors"))
        ],
    )


def load_continuity_ledger(storage_dir: str | Path, series_id: str) -> ContinuityLedger:
    path = _series_path(storage_dir, series_id, CONTINUITY_LEDGER_FILENAME)
    if not path.exists():
        return ContinuityLedger(series_id=series_id)
    return continuity_ledger_from_dict(_load_json_object(path))


def save_continuity_ledger(
    storage_dir: str | Path, series_id: str, ledger: ContinuityLedger | Mapping[str, Any]
) -> None:
    _save_json(
        _series_path(storage_dir, series_id, CONTINUITY_LEDGER_FILENAME),
        _to_plain(ledger),
    )


def load_emotional_arcs(storage_dir: str | Path, series_id: str) -> EmotionalArcRegistry:
    path = _series_path(storage_dir, series_id, EMOTIONAL_ARCS_FILENAME)
    if not path.exists():
        return EmotionalArcRegistry(series_id=series_id)
    return emotional_arc_registry_from_dict(_load_json_object(path))


def save_emotional_arcs(
    storage_dir: str | Path,
    series_id: str,
    registry: EmotionalArcRegistry | Mapping[str, Any],
) -> None:
    _save_json(_series_path(storage_dir, series_id, EMOTIONAL_ARCS_FILENAME), _to_plain(registry))


def load_world_register(storage_dir: str | Path, series_id: str) -> WorldRegister:
    path = _series_path(storage_dir, series_id, WORLD_REGISTER_FILENAME)
    if not path.exists():
        return WorldRegister(series_id=series_id)
    return world_register_from_dict(_load_json_object(path))


def save_world_register(
    storage_dir: str | Path,
    series_id: str,
    register: WorldRegister | Mapping[str, Any],
) -> None:
    _save_json(_series_path(storage_dir, series_id, WORLD_REGISTER_FILENAME), _to_plain(register))


def merge_continuity_ledgers(
    base: ContinuityLedger | Mapping[str, Any],
    incoming: ContinuityLedger | Mapping[str, Any],
) -> ContinuityLedger:
    """Return merged continuity state, deduping normalized scoped entries."""

    left = _coerce_ledger(base)
    right = _coerce_ledger(incoming)
    merged = ContinuityLedger(
        series_id=left.series_id or right.series_id,
        schema_version=max(left.schema_version, right.schema_version),
    )
    for field_name in _LEDGER_FIELDS:
        setattr(
            merged,
            field_name,
            _dedupe_entries(
                list(getattr(left, field_name)) + list(getattr(right, field_name))
            ),
        )
    return merged


def upsert_emotional_arc(
    registry: EmotionalArcRegistry | Mapping[str, Any],
    arc: EmotionalArc | Mapping[str, Any],
) -> EmotionalArcRegistry:
    """Return a registry with one character arc merged by character name."""

    updated = _coerce_arc_registry(registry)
    incoming = _coerce_arc(arc)
    existing = updated.characters.get(_character_key(incoming.character))
    if existing is None:
        updated.characters[_character_key(incoming.character)] = copy.deepcopy(incoming)
        return updated

    updated.characters[_character_key(incoming.character)] = EmotionalArc(
        character=existing.character,
        wound=incoming.wound or existing.wound,
        current_coping_mode=incoming.current_coping_mode or existing.current_coping_mode,
        relationships={**existing.relationships, **incoming.relationships},
        last_significant_emotional_event=(
            incoming.last_significant_emotional_event
            or existing.last_significant_emotional_event
        ),
        beats=_dedupe_entries(existing.beats + incoming.beats),
    )
    return updated


def merge_world_registers(
    base: WorldRegister | Mapping[str, Any],
    incoming: WorldRegister | Mapping[str, Any],
) -> WorldRegister:
    """Return merged world-register state, deduping normalized scoped entries."""

    left = _coerce_world_register(base)
    right = _coerce_world_register(incoming)
    return WorldRegister(
        series_id=left.series_id or right.series_id,
        schema_version=max(left.schema_version, right.schema_version),
        locations=_dedupe_dataclasses(left.locations + right.locations, ("name", "floor")),
        entity_ecology=_dedupe_dataclasses(
            left.entity_ecology + right.entity_ecology,
            ("entity", "floor", "location"),
        ),
        rules=_dedupe_dataclasses(left.rules + right.rules, ("rule", "floor")),
        economy_anchors=_dedupe_dataclasses(
            left.economy_anchors + right.economy_anchors,
            ("name", "floor", "location"),
        ),
    )


def format_continuity_context(
    ledger: ContinuityLedger | Mapping[str, Any],
    chapter_contract: Mapping[str, Any] | None = None,
    *,
    max_items_per_section: int = 3,
) -> str:
    state = _coerce_ledger(ledger)
    contract = dict(chapter_contract or {})
    sections = []
    labels = {
        "notable_moments": "Notable moments",
        "running_gags": "Running gags",
        "motifs": "Motifs",
        "world_details": "World details",
        "emotional_beats": "Emotional beats",
        "callbacks": "Callbacks",
    }
    for field_name in _LEDGER_FIELDS:
        entries = _relevant_entries(getattr(state, field_name), contract)
        if entries:
            sections.append(
                _format_lines(labels[field_name], [entry.text for entry in entries[:max_items_per_section]])
            )
    return "\n".join(sections)


def format_emotional_arc_context(
    registry: EmotionalArcRegistry | Mapping[str, Any],
    chapter_contract: Mapping[str, Any] | None = None,
    *,
    max_characters: int = 4,
) -> str:
    state = _coerce_arc_registry(registry)
    contract = dict(chapter_contract or {})
    focus = {_normalize(item) for item in _string_list(contract.get("character_focus"))}
    lines = []
    for arc in state.characters.values():
        if focus and _normalize(arc.character) not in focus:
            continue
        pieces = [arc.character]
        if arc.wound:
            pieces.append(f"wound={arc.wound}")
        if arc.current_coping_mode:
            pieces.append(f"coping={arc.current_coping_mode}")
        if arc.last_significant_emotional_event:
            pieces.append(f"last={arc.last_significant_emotional_event}")
        if arc.relationships:
            relationships = ", ".join(
                f"{name}: {status}" for name, status in sorted(arc.relationships.items())
            )
            pieces.append(f"relationships={relationships}")
        lines.append("; ".join(pieces))
        if len(lines) >= max_characters:
            break
    return _format_lines("Emotional arcs", lines) if lines else ""


def format_world_register_context(
    register: WorldRegister | Mapping[str, Any],
    chapter_contract: Mapping[str, Any] | None = None,
    *,
    max_items_per_section: int = 3,
) -> str:
    state = _coerce_world_register(register)
    contract = dict(chapter_contract or {})
    sections = []
    locations = [
        f"{item.name}: {item.detail}"
        for item in _relevant_scoped(state.locations, contract, location_attr="name")
    ]
    entities = [
        f"{item.entity}: {item.detail}"
        for item in _relevant_scoped(state.entity_ecology, contract)
    ]
    rules = [
        f"{item.rule}: {item.detail}" if item.detail else item.rule
        for item in _relevant_scoped(state.rules, contract)
    ]
    economy = [
        f"{item.name}: {item.detail}"
        for item in _relevant_scoped(state.economy_anchors, contract)
    ]
    for title, values in (
        ("Locations", locations),
        ("Entity ecology", entities),
        ("Rules", rules),
        ("Economy anchors", economy),
    ):
        if values:
            sections.append(_format_lines(title, values[:max_items_per_section]))
    return "\n".join(sections)


def format_chapter_memory_context(
    *,
    ledger: ContinuityLedger | Mapping[str, Any] | None = None,
    emotional_arcs: EmotionalArcRegistry | Mapping[str, Any] | None = None,
    world_register: WorldRegister | Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
) -> str:
    """Return compact prompt context assembled from any provided state slices."""

    blocks = []
    if ledger is not None:
        blocks.append(format_continuity_context(ledger, chapter_contract))
    if emotional_arcs is not None:
        blocks.append(format_emotional_arc_context(emotional_arcs, chapter_contract))
    if world_register is not None:
        blocks.append(format_world_register_context(world_register, chapter_contract))
    return "\n\n".join(block for block in blocks if block)


_LEDGER_FIELDS = (
    "notable_moments",
    "running_gags",
    "motifs",
    "world_details",
    "emotional_beats",
    "callbacks",
)


def _coerce_ledger(value: ContinuityLedger | Mapping[str, Any]) -> ContinuityLedger:
    if isinstance(value, ContinuityLedger):
        return copy.deepcopy(value)
    return continuity_ledger_from_dict(copy.deepcopy(value))


def _coerce_arc_registry(
    value: EmotionalArcRegistry | Mapping[str, Any],
) -> EmotionalArcRegistry:
    if isinstance(value, EmotionalArcRegistry):
        return copy.deepcopy(value)
    return emotional_arc_registry_from_dict(copy.deepcopy(value))


def _coerce_arc(value: EmotionalArc | Mapping[str, Any]) -> EmotionalArc:
    if isinstance(value, EmotionalArc):
        return copy.deepcopy(value)
    return emotional_arc_from_dict(copy.deepcopy(value))


def _coerce_world_register(value: WorldRegister | Mapping[str, Any]) -> WorldRegister:
    if isinstance(value, WorldRegister):
        return copy.deepcopy(value)
    return world_register_from_dict(copy.deepcopy(value))


def _ledger_entries(value: Any) -> list[LedgerEntry]:
    entries = []
    for item in _mapping_items(value):
        entries.append(
            LedgerEntry(
                text=str(item.get("text") or item.get("detail") or ""),
                chapter=_optional_int(item.get("chapter")),
                phase=str(item.get("phase") or ""),
                floor=_optional_int(item.get("floor")),
                location=str(item.get("location") or ""),
                characters=_string_list(item.get("characters")),
                tags=_string_list(item.get("tags")),
                metadata=copy.deepcopy(item.get("metadata"))
                if isinstance(item.get("metadata"), Mapping)
                else {},
            )
        )
    return [entry for entry in entries if entry.text.strip()]


def _location_detail(item: Mapping[str, Any]) -> LocationDetail:
    return LocationDetail(
        name=str(item.get("name") or item.get("location") or ""),
        detail=str(item.get("detail") or ""),
        floor=_optional_int(item.get("floor")),
        phase=str(item.get("phase") or ""),
        tags=_string_list(item.get("tags")),
    )


def _entity_ecology(item: Mapping[str, Any]) -> EntityEcology:
    return EntityEcology(
        entity=str(item.get("entity") or item.get("name") or ""),
        detail=str(item.get("detail") or ""),
        floor=_optional_int(item.get("floor")),
        location=str(item.get("location") or ""),
        tags=_string_list(item.get("tags")),
    )


def _rule_entry(item: Mapping[str, Any]) -> RuleEntry:
    return RuleEntry(
        rule=str(item.get("rule") or item.get("name") or ""),
        detail=str(item.get("detail") or ""),
        floor=_optional_int(item.get("floor")),
        phase=str(item.get("phase") or ""),
        tags=_string_list(item.get("tags")),
    )


def _economy_anchor(item: Mapping[str, Any]) -> EconomyAnchor:
    return EconomyAnchor(
        name=str(item.get("name") or ""),
        detail=str(item.get("detail") or ""),
        floor=_optional_int(item.get("floor")),
        location=str(item.get("location") or ""),
        tags=_string_list(item.get("tags")),
    )


def _relevant_entries(
    entries: Sequence[LedgerEntry], contract: Mapping[str, Any]
) -> list[LedgerEntry]:
    return [entry for entry in entries if _matches_scope(entry, contract)]


def _relevant_scoped(
    entries: Sequence[Any],
    contract: Mapping[str, Any],
    *,
    location_attr: str = "location",
) -> list[Any]:
    return [
        entry
        for entry in entries
        if _matches_scope(entry, contract, location_attr=location_attr)
    ]


def _matches_scope(
    entry: Any, contract: Mapping[str, Any], *, location_attr: str = "location"
) -> bool:
    phase = _normalize(contract.get("phase"))
    floor = _optional_int(contract.get("floor"))
    if floor is None and isinstance(contract.get("floor_range"), Sequence):
        floor_range = [
            _optional_int(item)
            for item in contract.get("floor_range", [])
            if _optional_int(item) is not None
        ]
        floor = floor_range[0] if len(floor_range) == 1 else None
    location = _normalize(contract.get("location") or contract.get("current_location"))
    entry_phase = _normalize(getattr(entry, "phase", ""))
    entry_floor = getattr(entry, "floor", None)
    entry_location = _normalize(getattr(entry, location_attr, ""))

    scoped = bool(entry_phase or entry_floor is not None or entry_location)
    if not scoped:
        return True
    if phase and entry_phase and phase == entry_phase:
        return True
    if floor is not None and entry_floor is not None and floor == entry_floor:
        return True
    if location and entry_location and location == entry_location:
        return True
    return False


def _dedupe_entries(entries: Sequence[LedgerEntry]) -> list[LedgerEntry]:
    deduped = []
    seen = set()
    for entry in entries:
        key = (
            _normalize(entry.text),
            _normalize(entry.phase),
            entry.floor,
            _normalize(entry.location),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(copy.deepcopy(entry))
    return deduped


def _dedupe_dataclasses(entries: Sequence[Any], identity_fields: Sequence[str]) -> list[Any]:
    deduped = []
    seen = set()
    for entry in entries:
        plain = _to_plain(entry)
        key = tuple(_normalize(plain.get(field)) for field in identity_fields)
        detail = _normalize(plain.get("detail") or plain.get("rule"))
        key = key + (detail,)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(copy.deepcopy(entry))
    return deduped


def _series_path(storage_dir: str | Path, series_id: str, filename: str) -> Path:
    return Path(storage_dir) / "series" / str(series_id) / filename


def _load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _save_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=True, indent=2, sort_keys=True)
        json_file.write("\n")


def _to_plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return copy.deepcopy(value)


def _mapping_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


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


def _format_lines(title: str, values: Sequence[str]) -> str:
    compact = [str(value).strip() for value in values if str(value).strip()]
    if not compact:
        return ""
    return f"{title}: " + " | ".join(compact)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _character_key(value: str) -> str:
    return _normalize(value)


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())
