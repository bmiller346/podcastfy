"""Originality guardrail for structural ambition without source imitation."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


FORBIDDEN_PATTERNS = {
    "copied_dcc_character_roles": ("snarky cat familiar", "boxer shorts crawler", "princess donut"),
    "copied_dungeon_corporate_structures": ("borant", "crawl con", "galactic syndicate dungeon show"),
    "copied_system_announcer_cadence": ("new achievement", "goddammit donut", "mongo is appalled"),
    "copied_pet_familiar_dynamics": ("pampered show cat", "talking cat princess", "pet class dynastic"),
    "copied_faction_names_mechanics": ("mudskippers", "plenty", "bopca"),
    "over_specific_dcc_tonal_imitation": ("crawler world", "dungeon crawler carl", "ai showrunner says new achievement"),
}

ALLOWED_STRUCTURES = (
    "lethal absurd systems",
    "bureaucratic satire",
    "progression mechanics",
    "long-form conspiracy",
    "comedic pressure under danger",
)


def audit_originality(
    text: str = "",
    *,
    contracts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    haystack = " ".join([text, *(str(dict(item)) for item in contracts or [])]).lower()
    warnings = []
    for warning_type, patterns in FORBIDDEN_PATTERNS.items():
        matched = [pattern for pattern in patterns if pattern in haystack]
        if matched:
            warnings.append(
                {
                    "type": warning_type,
                    "matched": matched,
                    "action": _action_for(warning_type),
                }
            )
    return {
        "passed": not warnings,
        "warnings": warnings,
        "allowed_structures": list(ALLOWED_STRUCTURES),
    }


def _action_for(warning_type: str) -> str:
    return {
        "copied_dcc_character_roles": "Change role chemistry, status, competence profile, and emotional dependency.",
        "copied_dungeon_corporate_structures": "Rename and redesign governance, incentives, and enforcement mechanics.",
        "copied_system_announcer_cadence": "Use a distinct syntax, rhythm, reward language, and cruelty style.",
        "copied_pet_familiar_dynamics": "Alter species/status dynamics and relationship leverage.",
        "copied_faction_names_mechanics": "Replace names and mechanical niches with setting-native equivalents.",
        "over_specific_dcc_tonal_imitation": "Preserve structural pressure while rebuilding voice, imagery, and joke machinery.",
    }.get(warning_type, "Revise toward source-specific originality.")
