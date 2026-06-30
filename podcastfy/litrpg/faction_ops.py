"""Constrained faction move planning without exposing hidden truth."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


MOVE_TYPES = {"sponsor", "dungeon_system", "crawler_political", "economic"}


@dataclass(slots=True)
class FactionMove:
    faction: str
    move_type: str
    apparent_goal: str
    hidden_goal_reference: str = ""
    hidden_motive_label: str = ""
    resources_used: list[str] = field(default_factory=list)
    legal_system_constraint: str = ""
    visible_action: str = ""
    protagonist_visible_effect: str = ""
    cost: str = ""
    vulnerability_exposed: str = ""
    protagonist_awareness_level: str = ""
    delayed_consequence: str = ""
    counterplay_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_FIELDS = (
    "faction",
    "move_type",
    "apparent_goal",
    "resources_used",
    "legal_system_constraint",
    "visible_action",
    "protagonist_visible_effect",
    "cost",
    "vulnerability_exposed",
    "protagonist_awareness_level",
    "delayed_consequence",
    "counterplay_path",
)


def plan_faction_move(
    *,
    conspiracy_context: Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
    floor_identity: Mapping[str, Any] | None = None,
    allowed_hidden_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Plan one visible, counterplayable faction move from safe context."""

    context = dict(conspiracy_context or {})
    chapter = dict(chapter_contract or {})
    floor = dict(floor_identity or {})
    factions = context.get("faction_constraints") if isinstance(context.get("faction_constraints"), Mapping) else {}
    faction_id, faction = _select_faction(factions, chapter)
    move_type = str(chapter.get("faction_move_type") or _infer_move_type(faction_id, faction))
    if move_type not in MOVE_TYPES:
        move_type = "dungeon_system"
    hidden_ref = str(chapter.get("hidden_goal_reference") or "")
    if hidden_ref and hidden_ref not in set(allowed_hidden_refs or []):
        hidden_ref = ""
    move = FactionMove(
        faction=str(faction.get("name") or faction_id or "unnamed faction"),
        move_type=move_type,
        apparent_goal=str(chapter.get("faction_apparent_goal") or faction.get("apparent_goal") or "advance a visible operational goal"),
        hidden_goal_reference=hidden_ref,
        hidden_motive_label=str(chapter.get("hidden_motive_label") or faction_id or "withheld motive"),
        resources_used=_string_list(chapter.get("faction_resources_used")) or _string_list(faction.get("resources")) or ["existing authority or pressure"],
        legal_system_constraint=str(chapter.get("legal_system_constraint") or (faction.get("operational_rules") or ["cannot act without a rule hook"])[0]),
        visible_action=str(chapter.get("visible_action") or "changes a rule, price, route, reputation, or threat posture on-page"),
        protagonist_visible_effect=str(chapter.get("protagonist_visible_effect") or f"the move changes access, price, threat posture, or social pressure on {floor.get('name') or 'the floor'}"),
        cost=str(chapter.get("faction_cost") or chapter.get("cost") or "spends authority, favors, money, credibility, or timing"),
        vulnerability_exposed=str(chapter.get("vulnerability_exposed") or "reveals one constraint the protagonists can pressure later"),
        protagonist_awareness_level=str(chapter.get("protagonist_awareness_level") or "visible effect understood; motive unconfirmed"),
        delayed_consequence=str(chapter.get("delayed_consequence") or "the consequence matures after the protagonists respond"),
        counterplay_path=str(chapter.get("counterplay_path") or "find the constraint, document the abuse, exploit a loophole, or force a costly overreach"),
    )
    return move.to_dict()


def validate_faction_move(move: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if move.get(field) in (None, "", [], {})]
    issues = []
    if str(move.get("move_type") or "") not in MOVE_TYPES:
        issues.append("move_type must distinguish sponsor, dungeon_system, crawler_political, or economic")
    if "truth_document" in str(move):
        issues.append("move exposes truth_document")
    return {"passed": not missing and not issues, "missing": missing, "issues": issues}


def _select_faction(factions: Mapping[str, Any], chapter: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    wanted = str(chapter.get("faction") or "").casefold()
    for key, value in factions.items():
        if not isinstance(value, Mapping):
            continue
        name = str(value.get("name") or key)
        if not wanted or wanted in {str(key).casefold(), name.casefold()}:
            return str(key), value
    return "", {}


def _infer_move_type(faction_id: str, faction: Mapping[str, Any]) -> str:
    text = f"{faction_id} {faction.get('name') or ''} {faction.get('apparent_goal') or ''}".lower()
    if "sponsor" in text or "broadcast" in text:
        return "sponsor"
    if "market" in text or "fee" in text or "economic" in text:
        return "economic"
    if "crawler" in text or "politic" in text:
        return "crawler_political"
    return "dungeon_system"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value).strip() else []
