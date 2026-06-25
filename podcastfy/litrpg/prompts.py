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
