"""Series package artifacts generated from a LitRPG premise."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

SERIES_PACKAGE_FILENAME = "series_package.json"
SERIES_PACKAGE_SCHEMA_VERSION = 1


@dataclass(slots=True)
class SystemAnnouncerPackage:
    """Reusable performance profile for the System voice."""

    name: str = "System Announcer"
    voice: str = ""
    tone: str = ""
    purpose: str = ""
    rules: list[str] = field(default_factory=list)
    sample_lines: list[str] = field(default_factory=list)
    delivery_notes: list[str] = field(default_factory=list)
    audio_cues: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CharacterPackage:
    """Generated role package for a major cast member."""

    name: str = ""
    role: str = ""
    character_class: str = ""
    voice: str = ""
    personality: str = ""
    arc: str = ""
    rules: list[str] = field(default_factory=list)
    sample_lines: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FamiliarPackage:
    """Generated package for a familiar, mascot, pet, or nonhuman companion."""

    name: str = ""
    species: str = ""
    system_role: str = ""
    voice: str = ""
    vocabulary: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    sample_lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HomeBasePackage:
    """Generated package for a persistent base, vehicle, ship, or safe room."""

    name: str = ""
    description: str = ""
    advantages: list[str] = field(default_factory=list)
    vulnerabilities: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    upgrades: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FloorRulesPackage:
    """Generated package for current floor mechanics and constraints."""

    floor: str = ""
    premise: str = ""
    rules: list[str] = field(default_factory=list)
    hazards: list[str] = field(default_factory=list)
    rewards: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactionPackage:
    """Generated package for a faction relevant to the current series arc."""

    name: str = ""
    agenda: str = ""
    leader: str = ""
    resources: list[str] = field(default_factory=list)
    relationship: str = ""
    rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SeriesPackage:
    """Serializable premise expansion used before chapter generation."""

    series_id: str
    schema_version: int = SERIES_PACKAGE_SCHEMA_VERSION
    premise: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    system_announcer: SystemAnnouncerPackage = field(
        default_factory=SystemAnnouncerPackage
    )
    characters: dict[str, CharacterPackage] = field(default_factory=dict)
    familiar: FamiliarPackage = field(default_factory=FamiliarPackage)
    home_base: HomeBasePackage = field(default_factory=HomeBasePackage)
    floor_rules: FloorRulesPackage = field(default_factory=FloorRulesPackage)
    faction_map: dict[str, FactionPackage] = field(default_factory=dict)


PackageType = TypeVar(
    "PackageType",
    SystemAnnouncerPackage,
    CharacterPackage,
    FamiliarPackage,
    HomeBasePackage,
    FloorRulesPackage,
    FactionPackage,
)


def series_package_path(storage_dir: str | Path, series_id: str) -> Path:
    """Return the per-series package path under a LitRPG storage root."""

    return Path(storage_dir) / "series" / str(series_id) / SERIES_PACKAGE_FILENAME


def default_series_package(series_id: str, premise: str = "") -> SeriesPackage:
    """Build a safe empty package artifact for a series."""

    return SeriesPackage(series_id=str(series_id), premise=str(premise or ""))


def load_series_package(
    storage_dir: str | Path = "data/litrpg", series_id: str = "default-series"
) -> SeriesPackage:
    """Load a series package, returning a safe default when it is missing."""

    path = series_package_path(storage_dir, series_id)
    if not path.exists():
        return default_series_package(series_id)

    with path.open("r", encoding="utf-8") as package_file:
        data = json.load(package_file)
    if not isinstance(data, dict):
        return default_series_package(series_id)
    return series_package_from_dict(data, fallback_series_id=str(series_id))


def save_series_package(
    storage_dir: str | Path = "data/litrpg",
    package: SeriesPackage | dict[str, Any] | None = None,
) -> None:
    """Persist a series package as deterministic, human-readable JSON."""

    if package is None:
        package = default_series_package("default-series")
    typed_package = ensure_series_package(package)
    path = series_package_path(storage_dir, typed_package.series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as package_file:
        json.dump(
            series_package_to_dict(typed_package),
            package_file,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        package_file.write("\n")


def update_series_package(
    storage_dir: str | Path, series_id: str, updates: SeriesPackage | dict[str, Any]
) -> SeriesPackage:
    """Load, merge, save, and return a series package."""

    package = load_series_package(storage_dir, series_id)
    merge_series_package_updates(package, updates)
    save_series_package(storage_dir, package)
    return package


def ensure_series_package(value: SeriesPackage | dict[str, Any]) -> SeriesPackage:
    """Return a typed SeriesPackage from an existing package or loose mapping."""

    if isinstance(value, SeriesPackage):
        return value
    if isinstance(value, dict):
        return series_package_from_dict(value)
    raise TypeError(f"Unsupported series package value: {type(value)!r}")


def series_package_from_dict(
    data: dict[str, Any], fallback_series_id: str = "default-series"
) -> SeriesPackage:
    """Build a SeriesPackage from loose JSON without requiring every field."""

    series_id = str(data.get("series_id") or fallback_series_id)
    return SeriesPackage(
        series_id=series_id,
        schema_version=_safe_int(
            data.get("schema_version"), SERIES_PACKAGE_SCHEMA_VERSION
        ),
        premise=str(data.get("premise") or ""),
        metadata=_dict(data.get("metadata")),
        system_announcer=_dataclass_from_dict(
            SystemAnnouncerPackage, _dict(data.get("system_announcer"))
        ),
        characters=_package_map(
            data.get("characters") or data.get("character_packages"),
            CharacterPackage,
        ),
        familiar=_dataclass_from_dict(
            FamiliarPackage, _dict(data.get("familiar") or data.get("familiar_package"))
        ),
        home_base=_dataclass_from_dict(HomeBasePackage, _dict(data.get("home_base"))),
        floor_rules=_dataclass_from_dict(
            FloorRulesPackage, _dict(data.get("floor_rules"))
        ),
        faction_map=_package_map(data.get("faction_map"), FactionPackage),
    )


def series_package_to_dict(package: SeriesPackage | dict[str, Any]) -> dict[str, Any]:
    """Return a plain dict representation suitable for JSON or UI payloads."""

    typed_package = ensure_series_package(package)
    return asdict(typed_package)


def merge_series_package_updates(
    package: SeriesPackage, updates: SeriesPackage | dict[str, Any]
) -> SeriesPackage:
    """Apply generated package updates without clearing existing useful detail."""

    update_keys = set(updates.keys()) if isinstance(updates, dict) else None
    update_package = ensure_series_package(updates)
    if update_package.premise:
        package.premise = update_package.premise
    if update_keys is None or "schema_version" in update_keys:
        package.schema_version = update_package.schema_version
    package.metadata.update(update_package.metadata)
    if update_keys is None or "system_announcer" in update_keys:
        _merge_dataclass(package.system_announcer, update_package.system_announcer)
    if update_keys is None or update_keys & {"characters", "character_packages"}:
        _merge_package_map(package.characters, update_package.characters)
    if update_keys is None or update_keys & {"familiar", "familiar_package"}:
        _merge_dataclass(package.familiar, update_package.familiar)
    if update_keys is None or "home_base" in update_keys:
        _merge_dataclass(package.home_base, update_package.home_base)
    if update_keys is None or "floor_rules" in update_keys:
        _merge_dataclass(package.floor_rules, update_package.floor_rules)
    if update_keys is None or "faction_map" in update_keys:
        _merge_package_map(package.faction_map, update_package.faction_map)
    return package


def format_series_package_summary(
    package: SeriesPackage | dict[str, Any],
    max_characters: int = 6,
    max_factions: int = 4,
) -> str:
    """Return compact package context suitable for prompt injection."""

    typed_package = ensure_series_package(package)
    lines = [f"Series Package ({typed_package.series_id})"]
    metadata = dict(typed_package.metadata or {})
    title = str(metadata.get("title") or metadata.get("series_title") or "").strip()
    logline = str(metadata.get("logline") or metadata.get("summary") or "").strip()
    if title:
        lines.append(f"Title: {title}")
    if logline:
        lines.append(f"Logline: {logline}")
    if typed_package.premise:
        lines.append(f"Premise: {typed_package.premise}")

    announcer_bits = _profile_bits(
        typed_package.system_announcer,
        ["voice", "tone", "purpose"],
        ["rules", "delivery_notes", "sample_lines"],
    )
    if announcer_bits:
        name = typed_package.system_announcer.name or "System Announcer"
        lines.append(f"{name}: {' | '.join(announcer_bits)}")

    for character in list(typed_package.characters.values())[:max_characters]:
        bits = _profile_bits(
            character,
            ["role", "character_class", "voice", "personality", "arc"],
            ["rules", "relationships", "sample_lines"],
        )
        if bits:
            lines.append(f"{character.name or 'Character'}: {' | '.join(bits)}")
        elif character.name:
            lines.append(f"{character.name}: character package pending detail")
    if len(typed_package.characters) > max_characters:
        lines.append(
            f"... plus {len(typed_package.characters) - max_characters} more character package(s)."
        )

    familiar_bits = _profile_bits(
        typed_package.familiar,
        ["species", "system_role", "voice"],
        ["vocabulary", "rules", "sample_lines"],
    )
    if familiar_bits:
        lines.append(f"Familiar {typed_package.familiar.name or ''}: {' | '.join(familiar_bits)}")

    home_bits = _profile_bits(
        typed_package.home_base,
        ["description"],
        ["advantages", "vulnerabilities", "rules", "upgrades"],
    )
    if home_bits:
        lines.append(f"Home Base {typed_package.home_base.name or ''}: {' | '.join(home_bits)}")

    floor_bits = _profile_bits(
        typed_package.floor_rules,
        ["floor", "premise"],
        ["rules", "hazards", "rewards", "constraints"],
    )
    if floor_bits:
        lines.append(f"Floor Rules: {' | '.join(floor_bits)}")

    for faction in list(typed_package.faction_map.values())[:max_factions]:
        bits = _profile_bits(
            faction,
            ["agenda", "leader", "relationship"],
            ["resources", "rules", "notes"],
        )
        if bits:
            lines.append(f"Faction {faction.name or 'Unknown'}: {' | '.join(bits)}")
    if len(typed_package.faction_map) > max_factions:
        lines.append(
            f"... plus {len(typed_package.faction_map) - max_factions} more faction package(s)."
        )

    return "\n".join(lines)


def _package_map(
    value: Any, package_type: type[PackageType]
) -> dict[str, PackageType]:
    if isinstance(value, list):
        items = [
            _dataclass_from_dict(package_type, item)
            for item in value
            if isinstance(item, dict)
        ]
        return {
            _package_key(item, fallback=f"item-{index + 1}"): item
            for index, item in enumerate(items)
        }
    if isinstance(value, dict):
        return {
            str(key): _dataclass_from_dict(package_type, _with_fallback_name(raw, key))
            for key, raw in value.items()
            if isinstance(raw, dict)
        }
    return {}


def _merge_package_map(
    target: dict[str, PackageType], updates: dict[str, PackageType]
) -> None:
    for key, update in updates.items():
        existing_key = _find_package_key(target, key, update)
        if existing_key is None:
            target[key] = update
            continue
        _merge_dataclass(target[existing_key], update)


def _merge_dataclass(target: Any, update: Any) -> None:
    for field_info in fields(target):
        name = field_info.name
        current = getattr(target, name)
        incoming = getattr(update, name)
        if isinstance(current, list):
            _extend_unique(current, _string_list(incoming))
        elif isinstance(current, dict):
            current.update(_dict(incoming))
        elif incoming:
            setattr(target, name, incoming)


def _profile_bits(profile: Any, scalar_fields: list[str], list_fields: list[str]) -> list[str]:
    bits: list[str] = []
    for name in scalar_fields:
        value = str(getattr(profile, name, "") or "").strip()
        if value:
            bits.append(f"{name.replace('_', ' ')}: {value}")
    for name in list_fields:
        values = _string_list(getattr(profile, name, []))
        if values:
            bits.append(f"{name.replace('_', ' ')}: " + "; ".join(_compact(values, 3)))
    return bits[:5]


def _dataclass_from_dict(
    package_type: type[PackageType], data: dict[str, Any]
) -> PackageType:
    allowed = {field_info.name for field_info in fields(package_type)}
    kwargs: dict[str, Any] = {}
    for field_info in fields(package_type):
        if field_info.name not in data:
            continue
        value = data[field_info.name]
        if field_info.name == "metadata":
            kwargs[field_info.name] = _dict(value)
        elif _is_list_field(field_info.name, package_type):
            kwargs[field_info.name] = _string_list(value)
        elif field_info.name in allowed:
            kwargs[field_info.name] = str(value) if value is not None else ""
    return package_type(**kwargs)


def _is_list_field(name: str, package_type: type[Any]) -> bool:
    defaults = package_type()
    return isinstance(getattr(defaults, name, None), list)


def _with_fallback_name(raw: Any, key: str) -> dict[str, Any]:
    data = _dict(raw)
    if "name" not in data or not str(data.get("name") or "").strip():
        data["name"] = str(key)
    return data


def _package_key(item: Any, fallback: str) -> str:
    name = str(getattr(item, "name", "") or "").strip()
    return name or fallback


def _find_package_key(target: dict[str, Any], update_key: str, update: Any) -> str | None:
    candidate_names = {str(update_key).casefold()}
    update_name = str(getattr(update, "name", "") or "").strip()
    if update_name:
        candidate_names.add(update_name.casefold())
    for key, value in target.items():
        existing_names = {str(key).casefold()}
        existing_name = str(getattr(value, "name", "") or "").strip()
        if existing_name:
            existing_names.add(existing_name.casefold())
        if candidate_names & existing_names:
            return key
    return None


def _compact(items: list[str], limit: int) -> list[str]:
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


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
