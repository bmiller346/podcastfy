"""Prompt builders for audio-first LitRPG episode generation."""

from __future__ import annotations

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
