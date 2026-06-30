"""Prompt builders for audio-first LitRPG episode generation."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


ROLE_TAGS = (
    "NARRATOR",
    "HERO",
    "SYSTEM",
    "SIDEKICK",
    "BOSS",
    "RIVAL",
    "MENTOR",
    "MERCHANT",
    "HEALER",
    "TANK",
    "ROGUE",
    "MAGE",
    "BEAST",
    "MINION",
    "GUIDE",
    "VILLAIN",
)
LITRPG_MECHANICS = (
    "XP",
    "level",
    "class",
    "loot",
    "quest",
    "skill",
    "stat",
)

SCARCITY_LOCK_LANGUAGE = (
    "Track currencies, trade goods, costs, scarcity, repairs, consumed items, debts, and access as hard constraints.",
    "Do not grant a new resource, clue, item, alliance, safe route, or ability unless the script or source state earns it.",
    "When something is spent, damaged, delayed, or made scarce, make the consequence audible in later choices.",
)

ANNOUNCER_SYSTEM_TONE = (
    "SYSTEM or Announcer moments must land as events, not plain narration.",
    "Keep the voice crisp, hostile, performative, and funny because it is precise, not because it explains too much.",
    "If the chosen genre has no System, apply this to the closest narrator, host, authority, interface, or recurring audio device.",
)

BUREAUCRATIC_SADISM_RULES = (
    "Institutional cruelty should feel like fine print weaponized through permits, fees, registrations, audits, notices, or rule exceptions.",
    "Rules can be absurd, but their costs must be concrete and enforceable in the scene.",
    "Do not let bureaucracy become random chaos; make each punishment traceable to a stated or discoverable rule.",
)

CHARACTER_VOICE_SEPARATION = (
    "Separate character voices through diction, sentence rhythm, taboo phrases, favorite insults, humor modes, and pressure tells.",
    "Show how each major character sounds different in fear, anger, tenderness, and tactical focus.",
    "Do not collapse the cast into narrator monologue or interchangeable banter.",
)

PHYSICAL_CONTINUITY_DEGRADATION = (
    "Visual continuity is mandatory: preserve static anchors, dynamic degradation, current injuries, fatigue markers, gear damage, repairs, and absurd physical traits.",
    "A physical limitation or gear state should affect a choice, movement, joke, or consequence.",
    "Do not make bodies, clothing, equipment, bases, or vehicles pristine after prior damage unless repair is established.",
)

MYSTERY_LOCK_DISCIPLINE = (
    "Protect long-term mysteries: plant clues, red herrings, payoff windows, and what must not be revealed yet.",
    "Do not spend protected reveals, forbidden payoffs, or series-mystery answers before their intended timing.",
    "Prefer production-ready constraints over literary commentary: name the open question, lock, clue wording, and payoff boundary.",
)

TTS_FRIENDLY_ROLE_BLOCK_CONSTRAINTS = (
    "Use XML-style role blocks only, with no markdown, SSML, tables, JSON, or prose outside the script when final script text is requested.",
    "Keep each spoken block short enough for TTS regeneration and later review.",
    "Allowed role tags must be treated as a closed set; every required role must appear unless physically impossible.",
)


def _join_items(items: Sequence[str] | None, fallback: str) -> str:
    if not items:
        return fallback
    return ", ".join(str(item) for item in items)


def _format_state(state: Mapping[str, Any] | None) -> str:
    if not state:
        return "No prior state is available. Establish continuity cleanly."
    lines = []
    for key in sorted(state):
        lines.append(f"- {key}: {state[key]}")
    return "\n".join(lines)


def _format_policy_block(title: str, lines: Sequence[str]) -> str:
    body = "\n".join(f"- {line}" for line in lines if str(line).strip())
    return f"{title}:\n{body}"


def format_scarcity_lock_language() -> str:
    """Return canonical scarcity and earned-resource prompt constraints."""

    return _format_policy_block("Scarcity lock", SCARCITY_LOCK_LANGUAGE)


def format_announcer_system_tone() -> str:
    """Return canonical Announcer/System tone constraints."""

    return _format_policy_block("Announcer / System tone", ANNOUNCER_SYSTEM_TONE)


def format_bureaucratic_sadism_rules() -> str:
    """Return canonical bureaucratic-sadism rule constraints."""

    return _format_policy_block("Bureaucratic-sadism rules", BUREAUCRATIC_SADISM_RULES)


def format_character_voice_separation() -> str:
    """Return canonical character voice separation constraints."""

    return _format_policy_block("Character voice separation", CHARACTER_VOICE_SEPARATION)


def format_physical_continuity_degradation() -> str:
    """Return canonical physical continuity and degradation constraints."""

    return _format_policy_block(
        "Physical continuity / degradation",
        PHYSICAL_CONTINUITY_DEGRADATION,
    )


def format_mystery_lock_discipline() -> str:
    """Return canonical mystery-lock and payoff discipline constraints."""

    return _format_policy_block("Mystery lock discipline", MYSTERY_LOCK_DISCIPLINE)


def format_tts_role_block_constraints(allowed_roles: Sequence[str] | str | None = None) -> str:
    """Return canonical TTS-friendly role block constraints."""

    lines = list(TTS_FRIENDLY_ROLE_BLOCK_CONSTRAINTS)
    if allowed_roles:
        if isinstance(allowed_roles, str):
            role_text = allowed_roles
        else:
            role_text = ", ".join(str(role) for role in allowed_roles)
        lines.append(f"Allowed role tags: {role_text}.")
    return _format_policy_block("TTS-friendly role block constraints", lines)


def build_series_anchor_block(
    *,
    series_plan: Mapping[str, Any] | None = None,
    book_plan: Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
    forbidden_mysteries: Sequence[Any] | None = None,
    allowed_hints: Sequence[Any] | None = None,
    reveal_locks: Sequence[Any] | None = None,
    power_ceiling: str = "",
    current_phase: str = "",
    current_tension: int | str | None = None,
    scarcity_constraints: Sequence[Any] | None = None,
    scarcity_registry: Mapping[str, Any] | None = None,
) -> str:
    """Build a compact deterministic anchor block for chapter prompts."""

    contract = dict(chapter_contract or {})
    book = dict(book_plan or {})
    series = dict(series_plan or {})
    registry = dict(scarcity_registry or {})

    phase = _first_text(current_phase, contract.get("phase"))
    tension = _first_text(current_tension, contract.get("tension"))
    ceiling = _first_text(power_ceiling, contract.get("power_ceiling"), book.get("power_ceiling"))
    forbidden = _dedupe_texts(
        [
            *_as_sequence(forbidden_mysteries),
            *_as_sequence(contract.get("must_not_spend")),
            *_as_sequence(registry.get("forbidden_mysteries")),
            *_as_sequence(registry.get("forbidden_now")),
        ]
    )
    series_mysteries = _dedupe_texts(
        [
            *_as_sequence(series.get("series_mysteries")),
            *_as_sequence(book.get("must_preserve")),
            *_as_sequence(contract.get("must_preserve")),
        ]
    )
    constraints = _dedupe_texts(
        [
            *_as_sequence(scarcity_constraints),
            *_as_sequence(contract.get("scarcity_constraints")),
            *_as_sequence(book.get("scarcity_constraints")),
            *_as_sequence(registry.get("scarcity_constraints")),
        ]
    )
    hints = _dedupe_texts([*_as_sequence(allowed_hints), *_as_sequence(registry.get("allowed_hints"))])
    locks = _dedupe_texts([*_as_sequence(reveal_locks), *_as_sequence(registry.get("reveal_locks"))])
    payoff_locks = _dedupe_texts(registry.get("payoff_locks") or [])

    lines = ["Series Anchor Block:"]
    lines.append(f"- Series plan: {_summarize_plan(series, ('series_title', 'title', 'logline', 'premise', 'core_loop', 'series_mysteries'))}")
    lines.append(f"- Book plan / arc: {_summarize_plan(book, ('book', 'role', 'major_change', 'arc_style', 'must_resolve', 'must_preserve', 'floor_range'))}")
    lines.append(f"- Chapter contract: {_summarize_plan(contract, ('book', 'chapter', 'title', 'phase', 'tension', 'creativity', 'absurdity', 'directives', 'must_resolve', 'must_not_spend'))}")
    lines.append(f"- Current phase/tension: {phase or 'unspecified'} / {tension or 'unspecified'}")
    lines.append(f"- Power ceiling: {ceiling or 'unspecified; do not escalate powers beyond earned state'}")
    lines.append(f"- Series mysteries: {_join_or_none(series_mysteries)}")
    lines.append(f"- Forbidden now: {_join_or_none(forbidden)}")
    lines.append(f"- Allowed hints: {_join_or_none(hints)}")
    lines.append(f"- Reveal locks: {_join_or_none(locks)}")
    lines.append(f"- Payoff locks: {_join_or_none(payoff_locks)}")
    lines.append(f"- Scarcity/resource constraints: {_join_or_none(constraints)}")
    if registry:
        for key in (
            "hint_allowed_at_book",
            "reveal_allowed_at_book",
            "payoff_allowed_at_book",
        ):
            values = _dedupe_texts(registry.get(key) or [])
            lines.append(f"- {key}: {_join_or_none(values)}")
    lines.append(
        "- Anchor rule: hints may foreshadow locked material, but reveals, explanations, upgrades, resources, and payoffs must stay inside their allowed windows."
    )
    return "\n".join(lines)


def build_episode_outline_prompt(
    *,
    premise: str,
    episode_number: int,
    minutes: int,
    tone: str,
    cast_roles: Mapping[str, str] | None = None,
    prior_state: Mapping[str, Any] | None = None,
    callbacks: Sequence[str] | None = None,
) -> str:
    """Build a prompt for a compact LitRPG episode outline."""
    cast_text = _format_cast(cast_roles)
    callback_text = _join_items(callbacks, "Invent one callback to a prior joke, vow, wound, or item.")
    mechanics = ", ".join(LITRPG_MECHANICS)
    roles = ", ".join(ROLE_TAGS)

    return f"""Create an audio-first LitRPG serial outline.

Episode: {episode_number}
Target length: {minutes} minutes
Tone: {tone}
Premise: {premise}

Required speaking roles: {roles}
Cast metadata:
{cast_text}

Prior state:
{_format_state(prior_state)}

Continuity callbacks to use: {callback_text}

Outline requirements:
- Structure the episode for listening, not reading: fast orientation, vivid action beats, and clear scene turns.
- Include short exchanges across a broad ensemble; do not limit the chapter to two or five voices.
- Plan at least three explicit system notifications using the SYSTEM role.
- Include LitRPG mechanics: {mechanics}, loot drops, XP gains, class or skill updates, and quest progress.
- Give each scene a spoken cadence note, such as clipped combat, tense whisper, comic breath, or ominous pause.
- Include callbacks that reward serial listeners without requiring homework.
- End on a strong cliffhanger that tees up the next episode.

Return:
1. A numbered scene outline.
2. Required role tags per scene using only {roles}.
3. System notifications and mechanic changes.
4. Final cliffhanger beat.
"""


def build_audio_script_prompt(
    *,
    outline: str,
    episode_number: int,
    minutes: int,
    tone: str,
    cast_roles: Mapping[str, str] | None = None,
    voice_effects: Mapping[str, Any] | None = None,
    prior_state: Mapping[str, Any] | None = None,
    series_anchor_block: str = "",
) -> str:
    """Build a prompt for the final audio-first LitRPG script."""
    roles = ", ".join(ROLE_TAGS)
    mechanics = ", ".join(LITRPG_MECHANICS)

    return f"""Write the final audio script for a local AI LitRPG audio serial.

Episode: {episode_number}
Target length: {minutes} minutes
Tone: {tone}

Use only these XML-style role tags for spoken lines:
{roles}

Cast metadata:
{_format_cast(cast_roles)}

Voice and effects metadata:
{_format_mapping(voice_effects)}

Prior state:
{_format_state(prior_state)}

Approved outline:
{outline}

Series anchor:
{series_anchor_block or build_series_anchor_block(
    chapter_contract=prior_state if isinstance(prior_state, Mapping) else None,
    scarcity_constraints=SCARCITY_LOCK_LANGUAGE,
)}

Reusable prompt policy:
{format_tts_role_block_constraints(ROLE_TAGS)}
{format_character_voice_separation()}
{format_scarcity_lock_language()}
{format_announcer_system_tone()}
{format_bureaucratic_sadism_rules()}
{format_physical_continuity_degradation()}
{format_mystery_lock_discipline()}

Script requirements:
- Format every spoken line as an XML-style role block, using only the allowed cast role tags.
- Example: <SYSTEM style="hostile announcer">NEW QUEST: Survive the bakery cult.</SYSTEM>
- Write for audio first: short exchanges, clean attribution, punchy sentences, and cadence cues that can guide TTS.
- Keep paragraphs brief; avoid ebook-style exposition and visual-only formatting.
- Include recurring SYSTEM notifications for quests, loot, XP, class, level, skill, stat, and status updates.
- Make the LitRPG mechanics audible and satisfying: {mechanics}, loot reveals, class identity, cooldowns, and consequences.
- Include callbacks to earlier state or running bits, but explain only what a listener needs in the moment.
- Give the BOSS a distinct threat, the SIDEKICK a useful counterpoint, and the HERO an active choice.
- Include a clear mid-episode turn and a final cliffhanger line.
- Do not include markdown tables, XML, SSML, or prose outside the script.

Return only the script.
"""


def _format_cast(cast_roles: Mapping[str, str] | None) -> str:
    if not cast_roles:
        return "\n".join(f"- {role}: default {role.lower()} voice" for role in ROLE_TAGS)
    return "\n".join(f"- {role}: {description}" for role, description in cast_roles.items())


def _format_mapping(values: Mapping[str, Any] | None) -> str:
    if not values:
        return "- Use default voice/effects metadata."
    return "\n".join(f"- {key}: {value}" for key, value in values.items())


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _join_or_none(values: Sequence[str]) -> str:
    return "; ".join(values) if values else "None"


def _dedupe_texts(values: Sequence[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, Mapping):
            text = _compact_json(value)
        else:
            text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        deduped.append(text)
        seen.add(key)
    return deduped


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    if isinstance(value, Sequence):
        return list(value)
    return [value]


def _summarize_plan(data: Mapping[str, Any], keys: Sequence[str]) -> str:
    pieces = []
    for key in keys:
        if key not in data:
            continue
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, Mapping):
            rendered = _compact_json(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            rendered = ", ".join(str(item) for item in value if str(item).strip())
        else:
            rendered = str(value)
        if rendered:
            pieces.append(f"{key}: {rendered}")
    return "; ".join(pieces) if pieces else "Not supplied"


def _compact_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
