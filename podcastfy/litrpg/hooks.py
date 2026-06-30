"""Chapter hook taxonomy and deterministic prompt helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


HOOK_CATEGORIES = (
    "action_cliffhanger",
    "tonal_reframe",
    "quiet_dread",
    "emotional_cost",
    "plan_reversal",
    "rules_revelation",
    "social_faction_consequence",
)

REVEAL_TIMINGS = ("immediate", "next_chapter", "long_arc")

_HOOK_ALIASES = {
    "action": "action_cliffhanger",
    "action_cliffhanger": "action_cliffhanger",
    "cliffhanger": "action_cliffhanger",
    "tonal": "tonal_reframe",
    "tonal_reframe": "tonal_reframe",
    "quiet": "quiet_dread",
    "quiet_dread": "quiet_dread",
    "dread": "quiet_dread",
    "emotional": "emotional_cost",
    "emotional_cost": "emotional_cost",
    "cost": "emotional_cost",
    "plan_turn": "plan_reversal",
    "plan_reversal": "plan_reversal",
    "reversal": "plan_reversal",
    "rules": "rules_revelation",
    "rules_revelation": "rules_revelation",
    "revelation_question": "rules_revelation",
    "revelation": "rules_revelation",
    "social": "social_faction_consequence",
    "faction": "social_faction_consequence",
    "social_faction_consequence": "social_faction_consequence",
    "open_question": "quiet_dread",
}


@dataclass(frozen=True, slots=True)
class MysteryLock:
    """A question the chapter may plant but must not pay off too early."""

    question: str = ""
    locked_until: str = ""
    forbidden_payoff: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | str | None) -> "MysteryLock":
        if value is None:
            return cls()
        if isinstance(value, str):
            return cls(question=value.strip())
        if not isinstance(value, Mapping):
            raise ValueError("mystery_lock must be a string or JSON object")
        return cls(
            question=_clean_text(value.get("question") or value.get("open_question")),
            locked_until=_clean_text(value.get("locked_until") or value.get("payoff_after")),
            forbidden_payoff=_clean_text(
                value.get("forbidden_payoff") or value.get("do_not_reveal")
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HookContract:
    """Structured obligations a chapter opening and ending must satisfy."""

    opening_hook_obligation: str
    ending_hook_type: str
    last_image: str
    open_question: str
    implied_cost: str
    next_chapter_obligation: str
    reveal_timing: str
    forbidden_payoff: str
    mystery_lock: MysteryLock

    @classmethod
    def from_mapping(
        cls,
        contract: Mapping[str, Any] | None = None,
        *,
        previous_hook_context: str = "",
    ) -> "HookContract":
        data = contract or {}
        if not isinstance(data, Mapping):
            raise ValueError("hook contract must be a JSON object")

        explicit_type = data.get("ending_hook_type") or data.get("hook_type")
        ending_hook_type = _normalize_hook_type(explicit_type) if explicit_type else hook_type_for_contract(data)
        reveal_timing = _normalize_reveal_timing(
            data.get("reveal_timing") or data.get("timing"),
            ending_hook_type=ending_hook_type,
        )
        mystery_lock = MysteryLock.from_mapping(data.get("mystery_lock"))
        forbidden_payoff = _clean_text(
            data.get("forbidden_payoff")
            or mystery_lock.forbidden_payoff
            or data.get("do_not_reveal")
        )

        last_image = _clean_text(
            data.get("last_image") or data.get("final_image") or data.get("ends_on")
        )
        open_question = _clean_text(
            data.get("open_question")
            or data.get("question")
            or mystery_lock.question
        )
        implied_cost = _clean_text(
            data.get("implied_cost") or data.get("cost") or data.get("stakes")
        )
        opening = _clean_text(
            data.get("opening_hook_obligation")
            or data.get("opening_obligation")
            or data.get("opening")
        )
        if not opening:
            opening = _default_opening_obligation(previous_hook_context)

        next_obligation = _clean_text(
            data.get("next_chapter_obligation") or data.get("next_obligation")
        )
        if not next_obligation:
            next_obligation = _default_next_chapter_obligation(
                reveal_timing=reveal_timing,
                last_image=last_image,
                open_question=open_question,
                mystery_lock=mystery_lock,
            )

        return cls(
            opening_hook_obligation=opening,
            ending_hook_type=ending_hook_type,
            last_image=last_image,
            open_question=open_question,
            implied_cost=implied_cost,
            next_chapter_obligation=next_obligation,
            reveal_timing=reveal_timing,
            forbidden_payoff=forbidden_payoff,
            mystery_lock=mystery_lock,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mystery_lock"] = self.mystery_lock.to_dict()
        return payload


def hook_type_for_contract(contract: Mapping[str, Any] | None) -> str:
    """Choose the chapter-ending hook family from tempo and phase context."""

    data = contract or {}
    explicit = data.get("ending_hook_type") or data.get("hook_type")
    if explicit:
        return _normalize_hook_type(explicit)

    tension = _optional_int(data.get("tension"))
    phase = str(data.get("phase") or "").casefold()
    tags = " ".join(str(tag) for tag in _sequence_or_empty(data.get("tags"))).casefold()
    text = f"{phase} {tags}"

    if tension is not None and tension >= 8:
        return "action_cliffhanger"
    if any(token in text for token in ("faction", "reputation", "rival", "court", "guild")):
        return "social_faction_consequence"
    if any(token in text for token in ("setback", "lost", "grief", "sacrifice", "wound")):
        return "emotional_cost"
    if any(token in text for token in ("reversal", "betrayal", "plan", "build", "pattern")):
        return "plan_reversal"
    if any(token in text for token in ("rule", "rules", "system", "mechanic", "class", "quest")):
        return "rules_revelation"
    if any(token in text for token in ("exploration", "mystery", "discovery", "secret")):
        return "rules_revelation"
    if tension is not None and tension <= 3:
        if any(token in text for token in ("loot", "bivouac", "survey", "new terms")):
            return "tonal_reframe"
        return "quiet_dread"
    return "quiet_dread"


def hook_directive_for_type(hook_type: str) -> str:
    """Return concrete prose obligations for a hook family."""

    directives = {
        "action_cliffhanger": (
            "End on immediate motion, danger, or a physical reversal. The last image should "
            "make stopping feel unsafe."
        ),
        "tonal_reframe": (
            "End on a funny, strange, or absurd detail that recontextualizes the chapter without "
            "erasing consequence."
        ),
        "quiet_dread": (
            "End on a small unsettling detail, unanswered implication, or silence that makes the "
            "reader lean forward."
        ),
        "emotional_cost": (
            "End on what the scene cost a character emotionally, shown through behavior or a "
            "specific physical image."
        ),
        "plan_reversal": (
            "End with the plan changing shape: a clever possibility, a risky bargain, a betrayal, "
            "or a new constraint that forces the next chapter."
        ),
        "rules_revelation": (
            "End on a rule, mechanic, loophole, or system truth that answers one question while "
            "opening a sharper one."
        ),
        "social_faction_consequence": (
            "End on reputation damage, faction leverage, public pressure, or a relationship debt "
            "that will move the next chapter."
        ),
    }
    return directives.get(_normalize_hook_type(hook_type), directives["quiet_dread"])


def build_hook_contract(
    *,
    contract: Mapping[str, Any] | None = None,
    previous_hook_context: str = "",
) -> HookContract:
    """Build a structured hook contract from chapter/showrunner data."""

    return HookContract.from_mapping(
        contract,
        previous_hook_context=previous_hook_context,
    )


def format_opening_hook_obligation(hook_contract: HookContract | Mapping[str, Any]) -> str:
    """Format the opening hook obligation for prompts."""

    hook = _coerce_hook_contract(hook_contract)
    return "\n".join(
        [
            "Opening Hook Obligation:",
            f"- {hook.opening_hook_obligation}",
        ]
    )


def format_ending_hook_obligations(hook_contract: HookContract | Mapping[str, Any]) -> str:
    """Format clear chapter-ending obligations for prompts and review."""

    hook = _coerce_hook_contract(hook_contract)
    lines = [
        "Ending Hook Obligations:",
        f"- Ending hook category: {hook.ending_hook_type}",
        f"- Reveal timing: {hook.reveal_timing} ({_timing_description(hook.reveal_timing)})",
        f"- Category directive: {hook_directive_for_type(hook.ending_hook_type)}",
        f"- Last image: {hook.last_image or 'Create a concrete final image tied to the chapter consequence.'}",
        f"- Open question: {hook.open_question or 'Leave one specific unanswered question.'}",
        f"- Implied cost: {hook.implied_cost or 'Attach a concrete cost, risk, debt, injury, or choice.'}",
        f"- Next chapter obligation: {hook.next_chapter_obligation}",
    ]
    if hook.mystery_lock.question or hook.forbidden_payoff:
        lines.extend(format_mystery_lock(hook).splitlines())
    return "\n".join(lines)


def format_mystery_lock(hook_contract: HookContract | Mapping[str, Any]) -> str:
    """Format long-arc mystery discipline without permitting early payoff."""

    hook = _coerce_hook_contract(hook_contract)
    lock = hook.mystery_lock
    lines = ["Mystery Lock:"]
    lines.append(f"- Locked question: {lock.question or hook.open_question or 'Unspecified long-arc question.'}")
    if lock.locked_until:
        lines.append(f"- Locked until: {lock.locked_until}")
    lines.append(
        f"- Forbidden payoff: {hook.forbidden_payoff or 'Do not solve, explain, or name the hidden answer in this chapter.'}"
    )
    return "\n".join(lines)


def build_hook_context(
    *,
    contract: Mapping[str, Any] | None = None,
    previous_hook_context: str = "",
) -> str:
    """Format structured hook obligations for drafting prompts."""

    hook = build_hook_contract(
        contract=contract,
        previous_hook_context=previous_hook_context,
    )
    lines = [
        "Hook Engine:",
        format_opening_hook_obligation(hook),
        format_ending_hook_obligations(hook),
    ]
    if previous_hook_context.strip():
        lines.append("Prior Chapter Hook To Carry Forward:")
        lines.append(previous_hook_context.strip())
    return "\n".join(lines)


def _coerce_hook_contract(value: HookContract | Mapping[str, Any]) -> HookContract:
    if isinstance(value, HookContract):
        return value
    return HookContract.from_mapping(value)


def _normalize_hook_type(value: Any) -> str:
    key = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if key in _HOOK_ALIASES:
        return _HOOK_ALIASES[key]
    if key in HOOK_CATEGORIES:
        return key
    return "quiet_dread"


def _normalize_reveal_timing(value: Any, *, ending_hook_type: str) -> str:
    key = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if key in REVEAL_TIMINGS:
        return key
    if ending_hook_type == "action_cliffhanger":
        return "immediate"
    if ending_hook_type in {"rules_revelation", "social_faction_consequence"}:
        return "next_chapter"
    return "long_arc"


def _timing_description(reveal_timing: str) -> str:
    descriptions = {
        "immediate": "immediate cliffhanger; the next chapter must open in the pressure of this beat",
        "next_chapter": "near-term consequence; the next chapter must engage it before moving on",
        "long_arc": "long-arc mystery plant; preserve the question without payoff",
    }
    return descriptions.get(reveal_timing, descriptions["long_arc"])


def _default_opening_obligation(previous_hook_context: str) -> str:
    if previous_hook_context.strip():
        return (
            "The first meaningful paragraph must honor the prior chapter's final image, "
            "question, or emotional charge before moving on."
        )
    return (
        "Open with a concrete pressure, image, or unanswered implication that belongs to "
        "this chapter's immediate situation."
    )


def _default_next_chapter_obligation(
    *,
    reveal_timing: str,
    last_image: str,
    open_question: str,
    mystery_lock: MysteryLock,
) -> str:
    anchor = last_image or open_question or mystery_lock.question
    if reveal_timing == "immediate":
        return f"Open the next chapter inside the unresolved danger: {anchor or 'the final beat'}."
    if reveal_timing == "next_chapter":
        return f"Make the next chapter deal with the new constraint before changing scenes: {anchor or 'the revealed consequence'}."
    return f"Carry the mystery forward without paying it off: {anchor or 'the locked question'}."


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sequence_or_empty(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
