"""Character arc and relationship-graph planning for prose context."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.continuity import EmotionalArcRegistry
from podcastfy.litrpg.continuity import load_emotional_arcs


@dataclass(slots=True)
class RelationshipEdge:
    source: str
    target: str
    state: str
    pressure: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CharacterArcPressure:
    character: str
    wound: str = ""
    current_coping_mode: str = ""
    last_significant_emotional_event: str = ""
    allowed_shift: str = "micro-beat only"
    relationship_pressure: list[str] = field(default_factory=list)
    forbidden_growth: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CharacterArcEngine:
    """Read emotional arcs and expose chapter-safe growth pressure."""

    def __init__(self, storage_dir: str | Path, series_id: str) -> None:
        self.storage_dir = Path(storage_dir)
        self.series_id = str(series_id or "default-series")

    def read(self) -> EmotionalArcRegistry:
        return load_emotional_arcs(self.storage_dir, self.series_id)

    def get_chapter_context(
        self,
        *,
        chapter_contract: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_character_arc_context(self.read(), chapter_contract=chapter_contract)


def build_character_arc_context(
    registry: EmotionalArcRegistry | Mapping[str, Any],
    *,
    chapter_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = _coerce_registry(registry)
    contract = dict(chapter_contract or {})
    focus = {_normalize(item) for item in _string_list(contract.get("character_focus"))}
    arcs = [
        arc
        for arc in state.characters.values()
        if not focus or _normalize(arc.character) in focus
    ]
    if not arcs and state.characters:
        arcs = list(state.characters.values())[:4]

    pressures = [
        _pressure_for_arc(arc, contract).to_dict()
        for arc in arcs[:4]
    ]
    graph = _relationship_graph(arcs or state.characters.values())
    forbidden = _forbidden_arc_moves(pressures, graph)
    return {
        "arc_pressure": pressures,
        "relationship_graph": [edge.to_dict() for edge in graph],
        "forbidden_arc_moves": forbidden,
    }


def format_character_arc_context(context: Mapping[str, Any] | None) -> str:
    data = dict(context or {})
    lines = []
    pressure_lines = []
    for item in _mapping_sequence(data.get("arc_pressure")):
        relationships = "; ".join(_string_list(item.get("relationship_pressure")))
        forbidden = "; ".join(_string_list(item.get("forbidden_growth")))
        pressure_lines.append(
            _compact(
                f"{item.get('character')}: coping={item.get('current_coping_mode')}; "
                f"allowed_shift={item.get('allowed_shift')}; relationships={relationships}; "
                f"locks={forbidden}"
            )
        )
    if pressure_lines:
        lines.append("Character arc pressure:")
        lines.extend(f"- {line}" for line in pressure_lines)

    graph_lines = []
    for edge in _mapping_sequence(data.get("relationship_graph")):
        graph_lines.append(
            _compact(f"{edge.get('source')} -> {edge.get('target')}: {edge.get('state')}")
        )
    if graph_lines:
        lines.append("Relationship graph:")
        lines.extend(f"- {line}" for line in graph_lines[:8])

    forbidden = _string_list(data.get("forbidden_arc_moves"))
    if forbidden:
        lines.append("Forbidden arc moves:")
        lines.extend(f"- {item}" for item in forbidden[:8])
    return "\n".join(lines)


def _pressure_for_arc(arc: Any, contract: Mapping[str, Any]) -> CharacterArcPressure:
    character = str(getattr(arc, "character", "") or "Unknown")
    relationships = [
        f"{target}: {state}"
        for target, state in sorted(getattr(arc, "relationships", {}).items())
    ]
    return CharacterArcPressure(
        character=character,
        wound=str(getattr(arc, "wound", "") or ""),
        current_coping_mode=str(getattr(arc, "current_coping_mode", "") or ""),
        last_significant_emotional_event=str(
            getattr(arc, "last_significant_emotional_event", "") or ""
        ),
        allowed_shift=_allowed_shift(character, contract),
        relationship_pressure=relationships,
        forbidden_growth=_growth_locks(arc, contract),
    )


def _allowed_shift(character: str, contract: Mapping[str, Any]) -> str:
    resolves = {_normalize(item) for item in _string_list(contract.get("resolves"))}
    introduces = {_normalize(item) for item in _string_list(contract.get("introduces"))}
    character_key = _normalize(character)
    if any(character_key in item and ("arc" in item or "wound" in item or "relationship" in item) for item in resolves):
        return "payoff allowed if earned on page"
    if any(character_key in item for item in introduces):
        return "establish baseline without resolving wound"
    tension = _optional_int(contract.get("tension"))
    if tension is not None and tension >= 8:
        return "stress response may worsen coping mode"
    return "micro-beat only"


def _growth_locks(arc: Any, contract: Mapping[str, Any]) -> list[str]:
    character = str(getattr(arc, "character", "") or "Unknown")
    allowed = _allowed_shift(character, contract)
    locks = []
    wound = str(getattr(arc, "wound", "") or "").strip()
    if wound and not allowed.startswith("payoff"):
        locks.append(f"{character}: do not resolve wound ({wound})")
    coping = str(getattr(arc, "current_coping_mode", "") or "").strip()
    if coping and allowed == "micro-beat only":
        locks.append(f"{character}: do not replace coping mode ({coping})")
    for target, state in sorted(getattr(arc, "relationships", {}).items()):
        if not allowed.startswith("payoff"):
            locks.append(f"{character} -> {target}: do not fully resolve relationship state ({state})")
    return locks


def _relationship_graph(arcs: Sequence[Any]) -> list[RelationshipEdge]:
    edges = []
    for arc in arcs:
        source = str(getattr(arc, "character", "") or "Unknown")
        for target, state in sorted(getattr(arc, "relationships", {}).items()):
            edges.append(
                RelationshipEdge(
                    source=source,
                    target=str(target),
                    state=str(state),
                    pressure=_relationship_pressure(str(state)),
                )
            )
    return edges


def _relationship_pressure(state: str) -> str:
    lowered = state.lower()
    if any(token in lowered for token in ("hostile", "contempt", "rival", "debt")):
        return "conflict pressure"
    if any(token in lowered for token in ("trust", "loyal", "caretaker")):
        return "trust pressure"
    return "status pressure"


def _forbidden_arc_moves(pressures: Sequence[Mapping[str, Any]], graph: Sequence[RelationshipEdge]) -> list[str]:
    values = []
    for item in pressures:
        values.extend(_string_list(item.get("forbidden_growth")))
    for edge in graph:
        if edge.pressure == "conflict pressure":
            values.append(f"{edge.source} -> {edge.target}: do not soften conflict without an earned beat")
    return _dedupe(values)


def _coerce_registry(value: EmotionalArcRegistry | Mapping[str, Any]) -> EmotionalArcRegistry:
    if isinstance(value, EmotionalArcRegistry):
        return value
    from podcastfy.litrpg.continuity import emotional_arc_registry_from_dict

    return emotional_arc_registry_from_dict(dict(value))


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(item) for item in value.values() if str(item or "").strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _dedupe(values: Sequence[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = _normalize(text)
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _compact(value: str, *, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."
