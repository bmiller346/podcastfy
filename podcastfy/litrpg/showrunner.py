"""Deterministic pacing controls for LitRPG chapter generation."""

from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class ArcEntry:
    chapter: int
    phase: str
    tension: int
    creativity: int
    absurdity: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WanderingEvent:
    name: str
    tension_override: int
    directive: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


NARRATIVE_ARC: tuple[ArcEntry, ...] = (
    ArcEntry(1, "The Drop", 8, 4, 7),
    ArcEntry(2, "The Drop", 7, 4, 7),
    ArcEntry(3, "The Drop", 8, 3, 8),
    ArcEntry(4, "The Bivouac", 3, 2, 4),
    ArcEntry(5, "The Bivouac", 2, 3, 5),
    ArcEntry(6, "The Bivouac", 3, 2, 4),
    ArcEntry(7, "Exploration", 5, 8, 6),
    ArcEntry(8, "Exploration", 5, 9, 6),
    ArcEntry(9, "Exploration", 6, 8, 7),
    ArcEntry(10, "Exploration", 5, 8, 6),
    ArcEntry(11, "Exploration", 6, 7, 6),
    ArcEntry(12, "Exploration", 7, 6, 5),
    ArcEntry(13, "Mid-Boss", 8, 3, 5),
    ArcEntry(14, "Mid-Boss", 9, 2, 4),
    ArcEntry(15, "Mid-Boss", 8, 3, 5),
    ArcEntry(16, "The Setback", 5, 4, 3),
    ArcEntry(17, "The Setback", 4, 5, 3),
    ArcEntry(18, "The Setback", 4, 4, 2),
    ArcEntry(19, "The Setback", 5, 5, 3),
    ArcEntry(20, "The Build", 6, 8, 7),
    ArcEntry(21, "The Build", 6, 9, 8),
    ArcEntry(22, "The Build", 7, 9, 8),
    ArcEntry(23, "The Build", 7, 8, 9),
    ArcEntry(24, "The Build", 8, 7, 8),
    ArcEntry(25, "The Build", 8, 9, 9),
    ArcEntry(26, "The Apex", 9, 2, 9),
    ArcEntry(27, "The Apex", 10, 2, 9),
    ArcEntry(28, "The Apex", 10, 2, 10),
    ArcEntry(29, "The Apex", 9, 2, 9),
    ArcEntry(30, "The Loot", 2, 8, 5),
)


WANDERING_EVENTS: tuple[WanderingEvent, ...] = (
    WanderingEvent(
        "Sudden Trap",
        8,
        "WANDERING EVENT: A trap triggers mid-scene. It is fast, ugly, and chaotic. "
        "Resolve it within this chapter and return to the base phase mood before the end.",
    ),
    WanderingEvent(
        "Uninvited Faction",
        7,
        "WANDERING EVENT: A hostile faction patrol intrudes. Combat is optional, but the threat is real.",
    ),
    WanderingEvent(
        "Familiar Incident",
        6,
        "WANDERING EVENT: A familiar or companion has done something unclear but escalating.",
    ),
    WanderingEvent(
        "System Anomaly",
        7,
        "WANDERING EVENT: The System corrects a previous announcement. The correction is worse.",
    ),
)


TENSION_DIRECTIVES = {
    "high": (
        "PACING: FRANTIC. Short, punchy sentences. Immediate visceral danger. "
        "No long internal monologue. Physical consequences are real and escalating."
    ),
    "mid": (
        "PACING: MODERATE. Mix action beats with brief breathing room. "
        "Characters can assess the situation, but threats remain present."
    ),
    "low": (
        "PACING: SLOW. Lean into sensory detail, banter, gear maintenance, "
        "environment observation, and character reflection. No sudden climax unless an override says so."
    ),
}


CREATIVITY_DIRECTIVES = {
    "locked": (
        "CONSTRAINT: STRICT INVENTORY LOCK. Do not introduce new items, skills, abilities, "
        "or environmental solutions that have not already been established."
    ),
    "normal": (
        "CONSTRAINT: STANDARD. Limited discoveries are allowed, but each new item, ability, "
        "or solution must be foreshadowed or logically consistent."
    ),
    "open": (
        "CONSTRAINT: LOOSE DISCOVERY. Bizarre, highly specific loot, mob behaviors, "
        "and lateral environmental solutions are allowed when they fit the scene."
    ),
}


ABSURDITY_DIRECTIVES = {
    "high": (
        "TONE: ABSURDIST. Let the dungeon layer be aggressively weird, while keeping "
        "injury, fear, and consequences emotionally real."
    ),
    "mid": (
        "TONE: GROUNDED ABSURDISM. Comedy is present but not dominant. "
        "The setting is strange; character reactions stay specific."
    ),
    "low": (
        "TONE: GROUNDED. Play the consequences straight. Save most jokes so the story earns weight."
    ),
}


def arc_entry_for_chapter(
    chapter_number: int,
    *,
    arc: Sequence[ArcEntry] = NARRATIVE_ARC,
) -> ArcEntry:
    """Return the fixed tempo-map entry for a chapter, clamping past the arc end."""

    if not arc:
        raise ValueError("Narrative arc must contain at least one entry")
    for entry in arc:
        if entry.chapter == chapter_number:
            return entry
    if chapter_number < arc[0].chapter:
        return arc[0]
    return arc[-1]


def roll_wandering_event(
    arc_entry: ArcEntry,
    *,
    rng: random.Random | None = None,
    sides: int = 20,
    trigger_roll: int = 20,
    events: Sequence[WanderingEvent] = WANDERING_EVENTS,
) -> WanderingEvent | None:
    """Roll a plateau-only D20-style micro-spike."""

    if arc_entry.tension > 4 or not events:
        return None
    roller = rng or random
    if roller.randint(1, sides) != trigger_roll:
        return None
    return roller.choice(list(events))


def build_showrunner_payload(
    *,
    chapter_number: int,
    wandering_event: WanderingEvent | Mapping[str, Any] | None = None,
    enable_wandering: bool = False,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Build deterministic chapter pacing metadata and prompt directives."""

    arc_entry = arc_entry_for_chapter(chapter_number)
    event = _coerce_event(wandering_event)
    if event is None and enable_wandering:
        event = roll_wandering_event(arc_entry, rng=rng)
    tension = event.tension_override if event is not None else arc_entry.tension
    payload = {
        "chapter": chapter_number,
        "phase": arc_entry.phase,
        "base_tension": arc_entry.tension,
        "tension": tension,
        "creativity": arc_entry.creativity,
        "absurdity": arc_entry.absurdity,
        "directives": [
            TENSION_DIRECTIVES[_tension_key(tension)],
            CREATIVITY_DIRECTIVES[_creativity_key(arc_entry.creativity)],
            ABSURDITY_DIRECTIVES[_absurdity_key(arc_entry.absurdity)],
        ],
        "wandering_event": event.to_dict() if event is not None else None,
    }
    if event is not None:
        payload["directives"].append(event.directive)
    return payload


def format_showrunner_context(payload: Mapping[str, Any] | None) -> str:
    """Return compact prompt context derived from showrunner metadata."""

    if not payload:
        return ""
    lines = [
        "Director's Console:",
        f"- Phase: {payload.get('phase') or 'Unknown'}",
        (
            "- Targets: "
            f"tension {payload.get('tension')}, "
            f"creativity {payload.get('creativity')}, "
            f"absurdity {payload.get('absurdity')}"
        ),
    ]
    directives = payload.get("directives")
    if isinstance(directives, Sequence) and not isinstance(directives, (str, bytes)):
        lines.append("- Directives:")
        lines.extend(f"  - {directive}" for directive in directives if directive)
    event = payload.get("wandering_event")
    if isinstance(event, Mapping) and event.get("name"):
        lines.append(f"- Wandering event: {event['name']}")
    return "\n".join(lines)


def _coerce_event(value: WanderingEvent | Mapping[str, Any] | None) -> WanderingEvent | None:
    if value is None:
        return None
    if isinstance(value, WanderingEvent):
        return value
    return WanderingEvent(
        name=str(value.get("name") or "Wandering Event"),
        tension_override=int(value.get("tension_override") or value.get("tension") or 8),
        directive=str(value.get("directive") or ""),
    )


def _tension_key(value: int) -> str:
    if value >= 8:
        return "high"
    if value <= 4:
        return "low"
    return "mid"


def _creativity_key(value: int) -> str:
    if value <= 3:
        return "locked"
    if value >= 8:
        return "open"
    return "normal"


def _absurdity_key(value: int) -> str:
    if value >= 8:
        return "high"
    if value <= 4:
        return "low"
    return "mid"
