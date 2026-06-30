"""Structured comedy pressure beats."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


ALLOWED_SOURCES = {
    "rule_absurdity",
    "bureaucratic_cruelty",
    "character_mismatch",
    "social_embarrassment",
    "callback_inversion",
    "system_literalism",
}


@dataclass(slots=True)
class ComedyBeat:
    setup: str
    pressure_source: str
    escalation: str
    grounding_reaction: str
    callback: str = ""
    intended_to_undercut_emotion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_comedy_beats(
    *,
    chapter_contract: Mapping[str, Any] | None = None,
    setpiece_contract: Mapping[str, Any] | None = None,
    character_context: Mapping[str, Any] | None = None,
    max_beats: int = 3,
) -> list[dict[str, Any]]:
    chapter = dict(chapter_contract or {})
    setpiece = dict(setpiece_contract or {})
    characters = dict(character_context or {})
    seeds = chapter.get("comedy_beats")
    if isinstance(seeds, Sequence) and not isinstance(seeds, (str, bytes, bytearray)):
        return [normalize_comedy_beat(item).to_dict() for item in seeds[:max(1, min(3, int(max_beats)))] if isinstance(item, Mapping)]
    source = str(chapter.get("comedy_pressure_source") or "system_literalism")
    if source not in ALLOWED_SOURCES:
        source = "system_literalism"
    focus = ", ".join(_string_list(chapter.get("character_focus"))[:2]) or "the viewpoint characters"
    beat = ComedyBeat(
        setup=str(chapter.get("comedy_setup") or setpiece.get("rule") or "a rule is stated too literally"),
        pressure_source=source,
        escalation=str(chapter.get("comedy_escalation") or setpiece.get("goes_wrong") or "the literal reading makes the tactical problem worse"),
        grounding_reaction=str(chapter.get("grounding_reaction") or f"{focus} react from stress, embarrassment, or practical need"),
        callback=str(characters.get("callback") or chapter.get("callback") or ""),
    )
    return [beat.to_dict()]


def normalize_comedy_beat(value: Mapping[str, Any]) -> ComedyBeat:
    source = str(value.get("pressure_source") or "system_literalism")
    if source not in ALLOWED_SOURCES:
        source = "system_literalism"
    return ComedyBeat(
        setup=str(value.get("setup") or "setup missing"),
        pressure_source=source,
        escalation=str(value.get("escalation") or "escalation missing"),
        grounding_reaction=str(value.get("grounding_reaction") or "grounding reaction missing"),
        callback=str(value.get("callback") or ""),
        intended_to_undercut_emotion=bool(value.get("intended_to_undercut_emotion")),
    )


def validate_comedy_beats(beats: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    issues = []
    if len(beats) > 3:
        issues.append("too many comedy beats; cap at 1-3")
    for index, beat in enumerate(beats, 1):
        missing = [key for key in ("setup", "pressure_source", "escalation", "grounding_reaction") if not str(beat.get(key) or "").strip()]
        if missing:
            issues.append(f"beat {index} missing: {', '.join(missing)}")
        if str(beat.get("pressure_source") or "") not in ALLOWED_SOURCES:
            issues.append(f"beat {index} uses unsupported pressure source")
    return {"passed": not issues, "issues": issues}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value).strip() else []
