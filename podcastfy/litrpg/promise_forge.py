"""Seed-time promise forging for LitRPG premise intake."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence


HOOK_BRIEF_SCHEMA: dict[str, Any] = {
    "logline": "",
    "back_cover_seed": "",
    "founding_injustice_candidate": "",
    "permanent_constraint_candidate": "",
    "comedic_signal": "",
    "reader_buy_button_image": "",
    "specificity_anchors": [],
    "do_not_smooth_out": [],
}

PROMISE_FORGE_SCHEMA: dict[str, Any] = {
    "founding_injustice": "",
    "permanent_constraint": "",
    "comedic_signal": "",
    "series_promise": "",
    "reader_buy_button_image": "",
    "must_recur": [],
    "must_not_become": [],
    "originality_locks": [],
    "source_brief": {},
}


def build_hook_brief_prompt(
    *,
    raw_context: str,
    genre: str = "",
    desired_tone: str = "",
) -> str:
    """Build a JSON-only prompt that compresses messy context into a hook brief."""

    return f"""You are the Hook Brief intake pass for a serial fiction seed.

Compress messy user context into a short, sellable narrative seed without losing
weird specific details. Preserve named people, relationships, places, objects,
specific obligations, family roles, and unusual world details.

Return ONLY valid JSON matching this schema:
{json.dumps(HOOK_BRIEF_SCHEMA, indent=2)}

Rules:
- logline should be short and commercial.
- back_cover_seed should sound like a story promise, not notes.
- founding_injustice_candidate must be unfair, funny, durable, and specific.
- permanent_constraint_candidate must be something the series can keep using.
- specificity_anchors should list concrete source anchors to preserve.
- do_not_smooth_out should list odd details that make the premise distinct.

Genre: {genre or "Infer from context"}
Desired tone: {desired_tone or "Infer from context"}

Raw messy context:
{raw_context}
"""


def build_promise_forge_prompt(
    *,
    raw_premise: str,
    genre: str = "",
    world_tone: str = "",
    existing_seed: Mapping[str, Any] | None = None,
) -> str:
    """Build a JSON-only prompt that turns a hook brief into a durable promise."""

    seed = json.dumps(dict(existing_seed or {}), indent=2, sort_keys=True)
    return f"""You are the Promise Forge intake pass for a LitRPG series.

Turn the raw premise or hook brief into a durable series contract. Return ONLY
valid JSON matching this schema:
{json.dumps(PROMISE_FORGE_SCHEMA, indent=2)}

Rules:
- founding_injustice must be specific to this protagonist and premise.
- It must be unfair, funny, permanent, and mechanically useful.
- It must not be generic dungeon survival.
- It must not imitate DCC names, voice, class names, system cadence, or terminology.
- permanent_constraint should create repeatable story pressure.
- artifacts should be shaped by the founding injustice and comedic signal, not
  only by environment inventory.
- must_not_become is for planning drift prevention.
- originality_locks is for prose-level prohibitions.
- source_brief may store the hook brief or existing seed, but the durable
  contract is the full promise_forge object.

Genre: {genre or "Infer from premise"}
World tone: {world_tone or "Infer from premise"}

Existing seed or hook brief:
{seed}

Raw premise:
{raw_premise}
"""


def normalize_promise_forge(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a stable promise_forge dict with expected keys and list shapes."""

    data = dict(value or {})
    normalized = {
        "founding_injustice": _clean_str(data.get("founding_injustice")),
        "permanent_constraint": _clean_str(data.get("permanent_constraint")),
        "comedic_signal": _clean_str(data.get("comedic_signal")),
        "series_promise": _clean_str(data.get("series_promise")),
        "reader_buy_button_image": _clean_str(data.get("reader_buy_button_image")),
        "must_recur": _string_list(data.get("must_recur")),
        "must_not_become": _string_list(data.get("must_not_become")),
        "originality_locks": _string_list(data.get("originality_locks")),
        "source_brief": dict(data.get("source_brief") or {}) if isinstance(data.get("source_brief"), Mapping) else {},
    }
    return normalized


def format_promise_forge_context(value: Mapping[str, Any] | None) -> str:
    """Format a compact source-labeled promise forge block for downstream planning."""

    data = normalize_promise_forge(value)
    if not any(data.get(key) for key in data if key != "source_brief"):
        return ""
    lines = ["[promise_forge]"]
    fields = (
        ("founding_injustice", "founding injustice"),
        ("permanent_constraint", "permanent constraint"),
        ("comedic_signal", "comedic signal"),
        ("series_promise", "series promise"),
        ("reader_buy_button_image", "reader-buy-button image"),
        ("must_recur", "must recur"),
        ("must_not_become", "must not become"),
        ("originality_locks", "originality locks"),
    )
    for key, label in fields:
        value = data.get(key)
        if isinstance(value, list):
            text = "; ".join(value[:4])
        else:
            text = str(value or "")
        if text:
            lines.append(f"- {label}: {_compact(text, 180)}")
    return "\n".join(lines[:9])


def validate_promise_forge_specificity(
    *,
    promise_forge: Mapping[str, Any],
    raw_premise: str,
) -> dict[str, Any]:
    """Validate that the promise forge uses concrete source anchors."""

    data = normalize_promise_forge(promise_forge)
    fields = {
        "founding_injustice": data["founding_injustice"],
        "permanent_constraint": data["permanent_constraint"],
        "reader_buy_button_image": data["reader_buy_button_image"],
    }
    anchors = _specificity_anchors(raw_premise, data.get("source_brief"))
    matched: dict[str, list[str]] = {}
    for field, text in fields.items():
        hits = _anchors_in_text(anchors, text)
        if hits:
            matched[field] = hits

    generic_issues = _generic_issues(data["founding_injustice"])
    issues = list(generic_issues)
    if not matched:
        issues.append(
            "founding_injustice, permanent_constraint, or reader_buy_button_image must reference concrete premise anchors"
        )
    if not data["founding_injustice"]:
        issues.append("founding_injustice is required")

    return {
        "passed": not issues,
        "issues": issues,
        "anchors": anchors[:20],
        "matched_anchors": matched,
    }


def _specificity_anchors(raw_premise: str, source_brief: Any) -> list[str]:
    text = str(raw_premise or "")
    if isinstance(source_brief, Mapping):
        for key in ("specificity_anchors", "do_not_smooth_out"):
            for item in _string_list(source_brief.get(key)):
                text += "\n" + item
        for key in (
            "logline",
            "back_cover_seed",
            "founding_injustice_candidate",
            "permanent_constraint_candidate",
            "reader_buy_button_image",
        ):
            text += "\n" + _clean_str(source_brief.get(key))

    anchors: list[str] = []
    anchors.extend(re.findall(r"\b[A-Z][a-z]+(?:\s+(?:II|III|IV|[A-Z][a-z]+))*\b", text))
    anchors.extend(re.findall(r"\b[A-Z]{2,}(?:\s+[A-Z][a-z]+)?\b", text))
    anchors.extend(re.findall(r"\b(?:mother|father|wife|husband|spouse|kid|kids|daughter|son|sister|brother|family|captain|crew|boat|ship|familiar|macaw|cockatoo)\b", text, flags=re.IGNORECASE))
    anchors.extend(re.findall(r"\b[\w'-]+(?:\s+[\w'-]+){0,4}\s+(?:board|permit|authority|obligation|debt|chore|boat|ship|vessel|fumes|pan|casino|guild|hall|scrip|wraiths|mimics|gargoyles)\b", text, flags=re.IGNORECASE))
    return _dedupe([anchor.strip(" .,:;!?\"'()[]{}") for anchor in anchors if len(anchor.strip()) >= 3])


def _anchors_in_text(anchors: Sequence[str], text: str) -> list[str]:
    haystack = str(text or "").casefold()
    hits = []
    for anchor in anchors:
        folded = anchor.casefold()
        if folded and folded in haystack:
            hits.append(anchor)
    return hits[:10]


def _generic_issues(found_injustice: str) -> list[str]:
    text = found_injustice.strip().casefold()
    if not text:
        return []
    generic_patterns = (
        "protagonist is forced",
        "forced to accept responsibility",
        "must survive the dungeon",
        "trapped in a dungeon",
        "chosen by the system",
        "has to become stronger",
        "generic dungeon survival",
    )
    if any(pattern in text for pattern in generic_patterns):
        return ["founding_injustice is generic enough to apply unchanged to another LitRPG protagonist"]
    return []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(item).strip() for item in value.values() if str(item or "").strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _compact(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


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
