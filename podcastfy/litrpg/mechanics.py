"""Deterministic LitRPG mechanics extraction and validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


MECHANICS_KEYWORDS = (
    "xp",
    "experience",
    "level",
    "class",
    "loot",
    "inventory",
    "quest",
    "skill",
    "stat",
    "status",
    "cooldown",
)

_ROLE_BLOCK_RE = re.compile(
    r"<(?P<role>[A-Za-z][A-Za-z0-9_-]*)(?:\s+[^>]*)?>(?P<text>.*?)</(?P=role)>",
    re.DOTALL,
)
_XP_GAIN_RE = re.compile(r"(?:\+|gains?|earned|awarded)\s*(?P<amount>\d+)\s*(?:xp|experience)\b", re.I)
_XP_SPEND_RE = re.compile(r"(?:spends?|spent|costs?|paid)\s*(?P<amount>\d+)\s*(?:xp|experience)\b", re.I)
_XP_TOTAL_RE = re.compile(r"(?:xp|experience)\s*(?:total|now|balance)?\s*[:=]?\s*(?P<amount>\d+)\b", re.I)
_LOOT_GAIN_RE = re.compile(
    r"(?:loot(?: gained)?|gained|obtained|received|picked up|found)\s*[:\-]?\s*(?P<item>[A-Za-z][A-Za-z0-9 '\-]{1,60})",
    re.I,
)
_CONSUME_RE = re.compile(
    r"(?:consumes?|used up|burns?|drinks?|eats?)\s+(?P<item>[A-Za-z][A-Za-z0-9 '\-]{1,60})",
    re.I,
)
_REMOVE_RE = re.compile(
    r"(?:removes?|lost|discarded|inventory\s*-\s*1)\s+(?P<item>[A-Za-z][A-Za-z0-9 '\-]{1,60})",
    re.I,
)
_COOLDOWN_ACTIVE_RE = re.compile(
    r"(?P<term>[A-Za-z][A-Za-z0-9 '\-]{1,50}?)\s+(?:is\s+)?(?:on\s+)?cooldown\b(?!\s+(?:ready|reset|cleared|ends?))|cooldown\s*[:\-]\s*(?P<term2>[A-Za-z][A-Za-z0-9 '\-]{1,50})",
    re.I,
)
_COOLDOWN_READY_RE = re.compile(
    r"(?P<term>[A-Za-z][A-Za-z0-9 '\-]{1,50}?)\s+cooldown\s+(?:ready|reset|cleared|ends?)\b|cooldown\s+(?:ready|reset|cleared|ends?)\s*[:\-]\s*(?P<term2>[A-Za-z][A-Za-z0-9 '\-]{1,50})",
    re.I,
)
_SKILL_LEARN_RE = re.compile(
    r"(?:learned|unlocked|gained)\s+(?:the\s+)?(?P<term>[A-Za-z][A-Za-z0-9 '\-]{1,50})\s+skill\b|skill\s+(?:learned|unlocked|gained)\s*[:\-]\s*(?P<term2>[A-Za-z][A-Za-z0-9 '\-]{1,50})",
    re.I,
)
_SKILL_MENTION_RE = re.compile(
    r"(?:casts?|activates?|uses?|triggers?)\s+(?:the\s+)?(?P<term>[A-Za-z][A-Za-z0-9 '\-]{1,50})(?:\s+skill)?\b|skill\s*[:\-]\s*(?P<term2>[A-Za-z][A-Za-z0-9 '\-]{1,50})",
    re.I,
)
_CLASS_RE = re.compile(r"\bclass\s*[:\-]\s*(?P<term>[A-Za-z][A-Za-z0-9 '\-]{1,50})", re.I)
_STAT_RE = re.compile(r"\b(?P<term>strength|dexterity|constitution|intelligence|wisdom|charisma|hp|mana|stamina|luck|agility)\s*(?:\+|-|:)\s*(?P<amount>\d+)?", re.I)
_QUEST_RE = re.compile(r"\bquest\s*(?:updated|accepted|complete|failed)?\s*[:\-]\s*(?P<term>[A-Za-z][A-Za-z0-9 '\-]{1,80})", re.I)
_STATUS_RE = re.compile(r"\bstatus\s*[:\-]\s*(?P<term>[A-Za-z][A-Za-z0-9 '\-]{1,50})", re.I)
_TRAILING_NOISE_RE = re.compile(
    r"\b(?:and|then|before|after|while|with|for|from|to|but|as|when|because|again|skill|cooldown|inventory|xp|experience)\b.*$",
    re.I,
)


@dataclass(slots=True)
class MechanicsValidationResult:
    ready: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    normalized_terms: dict[str, list[str]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.ready

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "pass": self.passed,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "events": list(self.events),
            "extracted_events": list(self.events),
            "normalized_terms": {key: list(value) for key, value in self.normalized_terms.items()},
        }


def extract_mechanics_events(script_text: str) -> list[dict[str, Any]]:
    """Extract lightweight mechanics events from role-tagged script text."""
    events: list[dict[str, Any]] = []
    for line_number, role, text in _script_segments(script_text):
        events.extend(_extract_from_segment(line_number=line_number, role=role, text=text))
    return events


def validate_mechanics(
    script_text: str,
    prior_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate script mechanics for obvious deterministic contradictions."""
    context = prior_context or {}
    events = extract_mechanics_events(script_text)
    normalized_terms = _normalized_terms(events, script_text)
    issues: list[str] = []
    warnings: list[str] = []

    if not normalized_terms:
        issues.append("No audible LitRPG mechanics detected")

    inventory = set(_normal_list(context.get("inventory")))
    skills = set(_normal_list(context.get("skills")))
    known_tools = set(_normal_list(context.get("known_tools")))
    character_class = _normalize_term(context.get("class") or context.get("character_class") or "")
    cooldowns = _normalize_cooldowns(context.get("cooldowns"))
    xp_total = _optional_int(context.get("xp"))
    xp_spent_since_total = False

    for event in events:
        kind = str(event["kind"])
        term = str(event.get("term") or "")
        amount = event.get("amount")

        if kind == "xp_gain" and isinstance(amount, int):
            if xp_total is not None:
                xp_total += amount
        elif kind == "xp_spend" and isinstance(amount, int):
            xp_spent_since_total = True
            if xp_total is not None:
                xp_total -= amount
        elif kind == "xp_total" and isinstance(amount, int):
            if xp_total is not None and amount < xp_total and not xp_spent_since_total:
                issues.append(
                    f"XP total decreases from {xp_total} to {amount} without an XP spend"
                )
            xp_total = amount
            xp_spent_since_total = False
        elif kind in {"loot_gain", "inventory_add"}:
            inventory.add(term)
        elif kind in {"item_consumed", "inventory_remove"}:
            if term not in inventory and term not in known_tools:
                issues.append(f"Item consumed or removed without inventory: {event['display']}")
            else:
                inventory.discard(term)
        elif kind == "skill_learned":
            skills.add(term)
        elif kind == "skill_used":
            if term in cooldowns:
                issues.append(f"Cooldown bypassed for unavailable ability: {event['display']}")
            if term not in skills and term not in known_tools and term != character_class:
                issues.append(f"Skill or class ability mentioned without availability: {event['display']}")
        elif kind == "cooldown_start":
            cooldowns.add(term)
        elif kind == "cooldown_ready":
            cooldowns.discard(term)

    return MechanicsValidationResult(
        ready=not issues,
        issues=_dedupe(issues),
        warnings=_dedupe(warnings),
        events=events,
        normalized_terms=normalized_terms,
    ).to_dict()


def _extract_from_segment(*, line_number: int, role: str, text: str) -> list[dict[str, Any]]:
    specs = [
        ("xp_gain", _XP_GAIN_RE),
        ("xp_spend", _XP_SPEND_RE),
        ("xp_total", _XP_TOTAL_RE),
        ("loot_gain", _LOOT_GAIN_RE),
        ("item_consumed", _CONSUME_RE),
        ("inventory_remove", _REMOVE_RE),
        ("cooldown_start", _COOLDOWN_ACTIVE_RE),
        ("cooldown_ready", _COOLDOWN_READY_RE),
        ("skill_learned", _SKILL_LEARN_RE),
        ("skill_used", _SKILL_MENTION_RE),
        ("class_mention", _CLASS_RE),
        ("stat_mention", _STAT_RE),
        ("quest_mention", _QUEST_RE),
        ("status_mention", _STATUS_RE),
    ]
    events: list[dict[str, Any]] = []
    for kind, pattern in specs:
        for match in pattern.finditer(text):
            term = _match_term(match, kind)
            amount = _match_amount(match)
            display = _clean_display(term or match.group(0))
            if kind.startswith("xp"):
                display = match.group(0).strip()
            if not display:
                continue
            events.append(
                {
                    "kind": kind,
                    "term": _normalize_term(display),
                    "display": display,
                    "amount": amount,
                    "role": role,
                    "line": line_number,
                }
            )
    return sorted(events, key=lambda event: (event["line"], _event_priority(str(event["kind"]))))


def _script_segments(script_text: str) -> list[tuple[int, str, str]]:
    matches = list(_ROLE_BLOCK_RE.finditer(script_text))
    if not matches:
        return [(1, "SCRIPT", script_text)]
    segments = []
    for match in matches:
        line_number = script_text.count("\n", 0, match.start()) + 1
        segments.append((line_number, match.group("role").upper(), match.group("text").strip()))
    return segments


def _match_term(match: re.Match[str], kind: str) -> str:
    group = (
        match.groupdict().get("term")
        or match.groupdict().get("term2")
        or match.groupdict().get("item")
    )
    if group:
        return group
    if kind.startswith("xp"):
        return "xp"
    return match.group(0)


def _match_amount(match: re.Match[str]) -> int | None:
    value = match.groupdict().get("amount")
    if value is None:
        return None
    return int(value)


def _clean_display(value: str) -> str:
    cleaned = _TRAILING_NOISE_RE.sub("", value).strip(" .,:;!?\"'")
    return re.sub(r"\s+", " ", cleaned)


def _normalize_term(value: Any) -> str:
    cleaned = _clean_display(str(value).lower())
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned)
    return cleaned


def _normal_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_normalize_term(value)]
    if isinstance(value, Mapping):
        return [_normalize_term(key) for key in value]
    if isinstance(value, Sequence):
        return [_normalize_term(item) for item in value]
    return []


def _normalize_cooldowns(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        return {
            _normalize_term(key)
            for key, state in value.items()
            if state not in {False, 0, None, "ready", "available", "off"}
        }
    return set(_normal_list(value))


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _normalized_terms(events: list[dict[str, Any]], script_text: str) -> dict[str, list[str]]:
    terms: dict[str, set[str]] = {}
    lower_script = script_text.lower()
    for keyword in MECHANICS_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lower_script):
            terms.setdefault("mechanics", set()).add(keyword)
    for event in events:
        kind = str(event["kind"])
        term = str(event.get("term") or "")
        if term:
            terms.setdefault(kind, set()).add(term)
    return {key: sorted(value) for key, value in sorted(terms.items()) if value}


def _event_priority(kind: str) -> int:
    order = {
        "xp_spend": 0,
        "xp_gain": 1,
        "xp_total": 2,
        "loot_gain": 3,
        "inventory_add": 4,
        "item_consumed": 5,
        "inventory_remove": 6,
        "cooldown_ready": 7,
        "skill_learned": 8,
        "skill_used": 9,
        "cooldown_start": 10,
    }
    return order.get(kind, 50)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
