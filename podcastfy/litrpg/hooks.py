"""Chapter hook taxonomy and review helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def hook_type_for_contract(contract: Mapping[str, Any] | None) -> str:
    """Choose the chapter-ending hook family from tempo and phase context."""

    data = contract or {}
    tension = _optional_int(data.get("tension"))
    phase = str(data.get("phase") or "").casefold()
    if tension is not None and tension >= 8:
        return "action_cliffhanger"
    if tension is not None and tension <= 3:
        if any(token in phase for token in ("loot", "bivouac", "survey", "new terms")):
            return "tonal_reframe"
        return "quiet_dread"
    if any(token in phase for token in ("setback", "lost", "reputation")):
        return "emotional_cost"
    if any(token in phase for token in ("build", "alliance", "pattern")):
        return "plan_turn"
    if any(token in phase for token in ("exploration", "mystery", "faction")):
        return "revelation_question"
    return "open_question"


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
        "plan_turn": (
            "End on the plan changing shape: a clever possibility, a risky bargain, or a new "
            "constraint that invites the next chapter."
        ),
        "revelation_question": (
            "End on a discovery that answers one question while opening a sharper one."
        ),
        "open_question": (
            "End on a clean unanswered question with a concrete image, cost, or choice attached."
        ),
    }
    return directives.get(hook_type, directives["open_question"])


def build_hook_context(
    *,
    contract: Mapping[str, Any] | None = None,
    previous_hook_context: str = "",
) -> str:
    """Format hook obligations for drafting prompts."""

    hook_type = hook_type_for_contract(contract)
    lines = [
        "Hook Engine:",
        f"- Required ending hook type: {hook_type}",
        f"- Ending obligation: {hook_directive_for_type(hook_type)}",
        "- Opening obligation: the first meaningful paragraph must honor the prior chapter's final image before moving on.",
    ]
    if previous_hook_context.strip():
        lines.append("- Prior chapter hook to carry forward:")
        lines.append(previous_hook_context.strip())
    return "\n".join(lines)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
