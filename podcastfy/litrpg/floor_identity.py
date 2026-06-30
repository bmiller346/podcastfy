"""Floor identity contracts for chapter planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class FloorIdentity:
    floor: int
    name: str
    visual_grammar: list[str] = field(default_factory=list)
    economy: list[str] = field(default_factory=list)
    common_threats: list[str] = field(default_factory=list)
    reward_logic: list[str] = field(default_factory=list)
    social_rules: list[str] = field(default_factory=list)
    traversal_constraint: str = ""
    faction_pressure: list[str] = field(default_factory=list)
    system_joke_style: str = ""
    exploit_pattern: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_FIELDS = (
    "visual_grammar",
    "economy",
    "common_threats",
    "reward_logic",
    "social_rules",
    "traversal_constraint",
    "faction_pressure",
    "system_joke_style",
    "exploit_pattern",
)


def build_floor_identity(
    *,
    floor: int = 1,
    floor_plan: Mapping[str, Any] | None = None,
    world_register: Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact, chapter-safe floor grammar."""

    plan = dict(floor_plan or {})
    register = dict(world_register or {})
    contract = dict(chapter_contract or {})
    floor_number = int(plan.get("floor") or contract.get("floor") or floor or 1)
    locations = _matching_entries(register.get("locations"), floor_number)
    ecology = _matching_entries(register.get("entity_ecology"), floor_number)
    rules = _matching_entries(register.get("rules"), floor_number) or _mapping_entries(register.get("rules"))
    economy = _matching_entries(register.get("economy_anchors"), floor_number) or _mapping_entries(register.get("economy_anchors"))

    identity = FloorIdentity(
        floor=floor_number,
        name=str(plan.get("name") or contract.get("floor_name") or contract.get("setting") or f"Floor {floor_number}"),
        visual_grammar=_string_list(plan.get("visual_grammar")) or _entry_details(locations, "detail")[:4],
        economy=_string_list(plan.get("economy")) or _entry_details(economy, "detail", fallback="name")[:4],
        common_threats=_string_list(plan.get("common_threats")) or _entry_details(ecology, "entity", fallback="detail")[:5],
        reward_logic=_string_list(plan.get("reward_logic")) or _string_list(contract.get("reward_logic")) or ["rewards require visible cost or trade"],
        social_rules=_string_list(plan.get("social_rules")) or _entry_details(rules, "detail", fallback="rule")[:4],
        traversal_constraint=str(plan.get("traversal_constraint") or contract.get("traversal_constraint") or "movement has a floor-specific constraint"),
        faction_pressure=_string_list(plan.get("faction_pressure")) or _string_list(contract.get("faction_pressure")),
        system_joke_style=str(plan.get("system_joke_style") or contract.get("system_joke_style") or "literal bureaucracy under danger"),
        exploit_pattern=str(plan.get("exploit_pattern") or contract.get("exploit_pattern") or "rules can be bent only after the cost is understood"),
    )
    return identity.to_dict()


def validate_floor_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    missing = []
    for field_name in REQUIRED_FIELDS:
        value = identity.get(field_name)
        if value in (None, "", [], {}):
            missing.append(field_name)
    return {"passed": not missing, "missing": missing}


def format_floor_identity_context(identity: Mapping[str, Any]) -> str:
    data = dict(identity or {})
    lines = [f"[floor_identity] {data.get('name') or 'Floor'} (floor {data.get('floor') or 1})"]
    for key in REQUIRED_FIELDS:
        value = data.get(key)
        text = "; ".join(_string_list(value)) if isinstance(value, (list, tuple, set)) else str(value or "")
        if text:
            lines.append(f"- {key}: {_compact(text)}")
    return "\n".join(lines)


def _matching_entries(value: Any, floor: int) -> list[Mapping[str, Any]]:
    return [
        item
        for item in _mapping_entries(value)
        if item.get("floor") in (None, "", floor, str(floor))
    ]


def _mapping_entries(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(item, id=str(key)) if isinstance(item, Mapping) else {"id": str(key), "detail": item} for key, item in value.items()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _entry_details(entries: Sequence[Mapping[str, Any]], key: str, *, fallback: str = "detail") -> list[str]:
    return _dedupe(str(item.get(key) or item.get(fallback) or item.get("name") or "").strip() for item in entries)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(item) for item in value.values() if str(item or "").strip()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value).strip() else []


def _dedupe(values: Sequence[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _compact(value: str, limit: int = 260) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
