"""Production planning helpers for cast-rich LitRPG audio chapters."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Mapping, Sequence


DEFAULT_CAST_ROLES = {
    "NARRATOR": "Cinematic narrator who keeps action clear and momentum high.",
    "HERO": "Primary point-of-view adventurer with grounded reactions.",
    "SYSTEM": "Hostile achievement and rules announcer with crisp comedic timing.",
    "SIDEKICK": "Loyal counterpoint who turns exposition into pressure and banter.",
    "BOSS": "Major antagonist with theatrical menace.",
    "RIVAL": "Competitive survivor with grudging respect for the hero.",
    "MENTOR": "Experienced delver who knows more than they admit.",
    "MERCHANT": "Opportunistic vendor with suspiciously useful inventory.",
    "HEALER": "Practical support character with dry triage humor.",
    "TANK": "Front-line bruiser who treats danger as logistics.",
    "ROGUE": "Sneaky opportunist who notices traps and social leverage.",
    "MAGE": "Rules-minded caster who explains mechanics under stress.",
    "BEAST": "Monster or summoned creature with simple but distinct vocal identity.",
    "MINION": "Disposable enemy voice for crowd texture and combat beats.",
    "GUIDE": "Dungeon tutorial voice separate from the hostile SYSTEM.",
    "VILLAIN": "Long-arc antagonist who should feel different from BOSS.",
}


@dataclass(slots=True)
class ChapterPart:
    part_id: str
    title: str
    purpose: str
    required_roles: list[str]
    injected_beats: list[str] = field(default_factory=list)
    target_minutes: int = 5


@dataclass(slots=True)
class ChapterPlan:
    chapter_number: int
    title: str
    premise: str
    cast_roles: dict[str, str]
    parts: list[ChapterPart]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_cast_roles(extra_roles: Mapping[str, str] | None = None) -> dict[str, str]:
    cast = dict(DEFAULT_CAST_ROLES)
    if extra_roles:
        cast.update({str(role).upper(): str(description) for role, description in extra_roles.items()})
    return cast


def build_chapter_plan(
    *,
    premise: str,
    chapter_number: int = 1,
    title: str | None = None,
    target_minutes: int = 30,
    cast_roles: Mapping[str, str] | None = None,
    injected_beats: Sequence[str] | None = None,
) -> ChapterPlan:
    """Build a deterministic starter chapter plan with cast-rich parts."""
    cast = default_cast_roles(cast_roles)
    beats = list(injected_beats or [])
    part_minutes = max(3, target_minutes // 5)
    part_templates = [
        (
            "cold-open",
            "Cold Open",
            "Open with immediate danger, a clear POV, and a SYSTEM interruption.",
            ["NARRATOR", "HERO", "SYSTEM", "SIDEKICK", "MINION"],
        ),
        (
            "party-pressure",
            "Party Pressure",
            "Introduce social friction, tactical roles, and a short breather with jokes.",
            ["NARRATOR", "HERO", "RIVAL", "HEALER", "TANK", "ROGUE", "MAGE"],
        ),
        (
            "mechanics-reveal",
            "Mechanics Reveal",
            "Reveal loot, XP, class consequences, and one rule that changes the fight.",
            ["NARRATOR", "SYSTEM", "GUIDE", "HERO", "MERCHANT", "MENTOR"],
        ),
        (
            "boss-setpiece",
            "Boss Setpiece",
            "Escalate into a staged combat scene with distinct enemy voices.",
            ["NARRATOR", "HERO", "SYSTEM", "BOSS", "BEAST", "MINION", "SIDEKICK"],
        ),
        (
            "fallout-cliffhanger",
            "Fallout and Cliffhanger",
            "Resolve rewards, update relationships, and end with a long-arc threat.",
            ["NARRATOR", "HERO", "SYSTEM", "VILLAIN", "RIVAL", "MENTOR"],
        ),
    ]
    parts = [
        ChapterPart(
            part_id=part_id,
            title=part_title,
            purpose=purpose,
            required_roles=roles,
            injected_beats=beats if index == 0 else [],
            target_minutes=part_minutes,
        )
        for index, (part_id, part_title, purpose, roles) in enumerate(part_templates)
    ]
    return ChapterPlan(
        chapter_number=chapter_number,
        title=title or f"Chapter {chapter_number}",
        premise=premise,
        cast_roles=cast,
        parts=parts,
    )


def build_chapter_part_prompt(
    *,
    chapter_plan: ChapterPlan,
    part: ChapterPart,
    prior_parts_summary: str = "",
) -> str:
    roles = ", ".join(part.required_roles)
    cast = "\n".join(
        f"- {role}: {chapter_plan.cast_roles[role]}"
        for role in part.required_roles
        if role in chapter_plan.cast_roles
    )
    injections = "\n".join(f"- {beat}" for beat in part.injected_beats) or "- None"
    return f"""Write one production-ready LitRPG audio chapter part.

Chapter {chapter_plan.chapter_number}: {chapter_plan.title}
Chapter premise: {chapter_plan.premise}
Part: {part.title}
Purpose: {part.purpose}
Target length: {part.target_minutes} minutes
Allowed role tags for this part: {roles}

Cast direction:
{cast}

Injected beats that must appear:
{injections}

Prior parts summary:
{prior_parts_summary or "This is the first part."}

Requirements:
- Use XML-style role blocks only, for example <HERO>...</HERO>.
- Do not collapse the cast into narrator monologue. Let characters speak.
- Every required role must appear at least once unless physically impossible.
- Keep each spoken block short enough for TTS regeneration and later review.
- Include audible LitRPG mechanics where relevant: XP, loot, quest, status, cooldown, stat, skill, or class.
- Preserve continuity and leave a clear handoff into the next part.
"""


def build_part_review_prompt(*, part_script: str, required_roles: Sequence[str]) -> str:
    roles = ", ".join(required_roles)
    return f"""Review this LitRPG audio script part before it is rendered.

Required roles: {roles}

Check for:
- Missing required role voices.
- Overlong monologues that should be split for TTS.
- Flat or generic dialogue.
- Confusing LitRPG mechanics.
- Continuity mistakes or unresolved injected beats.
- Places where a SYSTEM or announcer-style insert would improve pacing.

Return actionable fixes first, then a concise pass/fail recommendation.

Script:
{part_script}
"""


def build_director_pass_prompt(*, part_script: str, required_roles: Sequence[str]) -> str:
    roles = ", ".join(required_roles)
    return f"""Mark performance intent for this LitRPG audio script part.

Required roles: {roles}

Do not rewrite the prose. Add production intent only.

For each meaningful spoken block or beat, identify:
- emotion: panic, dry irritation, triumph, disgust, grief, dread, awe, or another precise playable state.
- delivery: whisper, bark, deadpan, breathless, smug, clipped, reverent, ragged, or another TTS-directable choice.
- timing: beat, long pause, interrupt, overlap, speed-up, hard stop, or another timing instruction.
- audio_effect: announcer slapback, radio filter, crowd swell, dungeon reverb, UI chime, low hit, or none.

Return compact JSON with:
- summary
- cues: an ordered list of role, trigger_text, emotion, delivery, timing, audio_effect.
- render_notes: any global notes for casting or TTS.

Script:
{part_script}
"""


def build_mechanics_audit_prompt(
    *,
    part_script: str,
    chapter_premise: str,
    prior_parts_summary: str = "",
) -> str:
    return f"""Audit LitRPG mechanics credibility for this chapter part.

Chapter premise: {chapter_premise}
Prior parts summary:
{prior_parts_summary or "This is the first part."}

Check:
- XP totals, loot, inventory, cooldowns, class abilities, stats, quests, and status effects.
- Whether consumed items are removed or consequences are acknowledged.
- Whether the solution uses tools or abilities available in the script or prior summary.
- Whether a character gains a power, item, or class feature without earning it.
- Whether mechanics are audible enough for listeners to follow.

Return:
- verdict: pass, revise, or block.
- blocking_issues: concise list.
- fixes: concrete script-level fixes.

Script:
{part_script}
"""


def build_tonal_audit_prompt(*, part_script: str, target_tone: str = "") -> str:
    return f"""Score the LitRPG chapter part on tonal dissonance.

Target tone: {target_tone or "absurd dungeon spectacle with emotionally real stakes"}

Give two independent 1-10 ratings:
- stakes_seriousness: consequences feel emotionally real.
- absurdity_pressure: dungeon/game layer is weird and active enough.

Reject or revise if the part is only goofy, only grim, or lets jokes erase consequences.

Return:
- stakes_seriousness
- absurdity_pressure
- verdict: pass, revise, or block.
- fixes: concrete changes that preserve the script's best material.

Script:
{part_script}
"""


def build_showmanship_audit_prompt(*, part_script: str) -> str:
    return f"""Simulate the dungeon audience and sponsor desk reviewing this chapter part.

Score 1-10:
- crowd_engagement
- brutality
- creativity
- humiliation
- meme_potential
- sponsor_appeal

Then recommend one reward, announcement, punishment, or complication for the next part if useful.

Return:
- scores
- verdict: pass, revise, or block.
- awards_or_complications
- fixes

Script:
{part_script}
"""


def build_part_revision_prompt(
    *,
    draft_script: str,
    director_tags: str,
    mechanics_audit: str,
    tonal_audit: str,
    showmanship_audit: str,
    required_roles: Sequence[str],
) -> str:
    roles = ", ".join(required_roles)
    return f"""Revise this LitRPG audio script part for render readiness.

Allowed role tags: {roles}

Use the review material below as constraints, not as decorative notes.
Preserve strong jokes, character choices, and continuity. Fix blocking issues.
Keep XML-style role blocks only. Do not include markdown, explanations, or JSON.
Add style attributes sparingly when director intent matters, for example:
<SYSTEM style="smug announcer, slapback">ACHIEVEMENT UNLOCKED.</SYSTEM>

Director pass:
{director_tags}

Mechanics audit:
{mechanics_audit}

Tonal audit:
{tonal_audit}

Showmanship audit:
{showmanship_audit}

Draft script:
{draft_script}
"""


def build_chapter_review_prompt(*, part_scripts: Sequence[str], cast_roles: Mapping[str, str]) -> str:
    cast = ", ".join(cast_roles)
    scripts = "\n\n".join(part_scripts)
    return f"""Review the completed LitRPG audio chapter as a produced audio drama.

Cast roles available: {cast}

Check:
- Character voice separation across at least 15 distinct roles where applicable.
- Whether SYSTEM/announcer moments land as events, not plain narration.
- Chapter pacing across parts: hook, escalation, mechanics reveal, setpiece, fallout, cliffhanger.
- Whether any role appears redundant and should be merged or rewritten.
- Whether any missing injected scene should be added before render.

Return a production review with blocking fixes, optional polish, and render readiness.

Chapter scripts:
{scripts}
"""
