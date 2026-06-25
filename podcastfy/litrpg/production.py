"""Production planning helpers for cast-rich local audio chapters."""

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


GENERIC_CAST_ROLES = {
    "NARRATOR": "Cinematic narrator who keeps action clear and momentum high.",
    "HERO": "Primary point-of-view character with grounded reactions.",
    "SIDEKICK": "Loyal counterpoint who turns exposition into pressure and banter.",
    "RIVAL": "Competitive or oppositional character with a distinct agenda.",
    "MENTOR": "Experienced guide who knows more than they admit.",
    "VILLAIN": "Long-arc antagonist who should feel different from a scene threat.",
    "AUTHORITY": "Institutional pressure voice: boss, officer, judge, parent, or official.",
    "WITNESS": "Information-bearing character with a specific bias or memory.",
    "COMIC_RELIEF": "Funny pressure valve whose jokes do not erase consequences.",
    "SKEPTIC": "Character who challenges plans and forces clearer reasoning.",
    "ALLY": "Support character with practical help and independent wants.",
    "EXPERT": "Specialist who explains rules, history, clues, or constraints under stress.",
    "THREAT": "Immediate antagonist, danger, monster, culprit, or disaster voice.",
    "CROWD": "Background voices for social texture and public pressure.",
    "HOST": "Optional announcer, interviewer, showrunner, or framing-device voice.",
    "MYSTERY": "Unresolved force, clue trail, hidden patron, or eerie recurring presence.",
}


@dataclass(slots=True)
class StoryProfile:
    genre: str
    is_litrpg: bool
    script_label: str
    mechanics_label: str
    mechanics_examples: str
    tonal_target: str
    showmanship_label: str


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


def story_profile(genre: str = "") -> StoryProfile:
    clean_genre = str(genre or "").strip()
    is_litrpg = "litrpg" in clean_genre.casefold() or not clean_genre
    label = "LitRPG" if is_litrpg else clean_genre
    return StoryProfile(
        genre=label,
        is_litrpg=is_litrpg,
        script_label=f"{label} audio chapter",
        mechanics_label="LitRPG mechanics" if is_litrpg else f"{label} story logic",
        mechanics_examples=(
            "XP, loot, quest, status, cooldown, stat, skill, or class"
            if is_litrpg
            else "clues, promises, secrets, relationships, resources, motives, rules, debts, injuries, or constraints"
        ),
        tonal_target=(
            "absurd dungeon spectacle with emotionally real stakes"
            if is_litrpg
            else f"{label} with emotionally real stakes and genre-appropriate contrast"
        ),
        showmanship_label=(
            "dungeon audience and sponsor desk"
            if is_litrpg
            else "audio-series audience, editor, and engagement desk"
        ),
    )


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
    genre: str = "",
) -> ChapterPlan:
    """Build a deterministic starter chapter plan with cast-rich parts."""
    profile = story_profile(genre)
    cast = default_cast_roles(cast_roles) if profile.is_litrpg else _default_story_cast_roles(cast_roles)
    beats = list(injected_beats or [])
    part_minutes = max(3, target_minutes // 5)
    part_templates = _litrpg_part_templates() if profile.is_litrpg else _generic_part_templates()
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


def _default_story_cast_roles(extra_roles: Mapping[str, str] | None = None) -> dict[str, str]:
    cast = dict(GENERIC_CAST_ROLES)
    if extra_roles:
        cast.update({str(role).upper(): str(description) for role, description in extra_roles.items()})
    return cast


def _litrpg_part_templates() -> list[tuple[str, str, str, list[str]]]:
    return [
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


def _generic_part_templates() -> list[tuple[str, str, str, list[str]]]:
    return [
        (
            "cold-open",
            "Cold Open",
            "Open with immediate pressure, a clear POV, and one distinctive audio hook.",
            ["NARRATOR", "HERO", "SIDEKICK", "THREAT", "CROWD"],
        ),
        (
            "social-pressure",
            "Social Pressure",
            "Introduce relationship friction, competing agendas, and a breath of humor.",
            ["NARRATOR", "HERO", "RIVAL", "ALLY", "SKEPTIC", "AUTHORITY"],
        ),
        (
            "rules-reveal",
            "Rules Reveal",
            "Reveal the story constraint, clue, bargain, setting rule, or emotional cost that changes the plan.",
            ["NARRATOR", "HERO", "EXPERT", "MENTOR", "WITNESS", "HOST"],
        ),
        (
            "setpiece",
            "Setpiece",
            "Escalate into a staged confrontation, chase, reveal, performance, or disaster.",
            ["NARRATOR", "HERO", "THREAT", "SIDEKICK", "COMIC_RELIEF", "CROWD"],
        ),
        (
            "fallout-cliffhanger",
            "Fallout and Cliffhanger",
            "Resolve immediate consequences, update relationships, and end with a long-arc question.",
            ["NARRATOR", "HERO", "VILLAIN", "RIVAL", "MENTOR", "MYSTERY"],
        ),
    ]


def build_chapter_part_prompt(
    *,
    chapter_plan: ChapterPlan,
    part: ChapterPart,
    prior_parts_summary: str = "",
    story_bible_summary: str = "",
    series_package_summary: str = "",
    showrunner_context: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    roles = ", ".join(part.required_roles)
    cast = "\n".join(
        f"- {role}: {chapter_plan.cast_roles[role]}"
        for role in part.required_roles
        if role in chapter_plan.cast_roles
    )
    injections = "\n".join(f"- {beat}" for beat in part.injected_beats) or "- None"
    return f"""Write one production-ready {profile.script_label} part.

Chapter {chapter_plan.chapter_number}: {chapter_plan.title}
Genre/style: {profile.genre}
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

Story bible continuity:
{story_bible_summary or "No separate story bible is available yet."}

Series package context:
{series_package_summary or "No separate series package is available yet."}

Showrunner pacing and constraint context:
{showrunner_context or "No separate showrunner tempo context is available yet."}

Requirements:
- Use XML-style role blocks only, for example <HERO>...</HERO>.
- Do not collapse the cast into narrator monologue. Let characters speak.
- Every required role must appear at least once unless physically impossible.
- Keep each spoken block short enough for TTS regeneration and later review.
- Include audible {profile.mechanics_label} where relevant: {profile.mechanics_examples}.
- Preserve continuity and leave a clear handoff into the next part.
"""


def build_part_review_prompt(
    *,
    part_script: str,
    required_roles: Sequence[str],
    series_package_summary: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    roles = ", ".join(required_roles)
    return f"""Review this {profile.script_label} script part before it is rendered.

Required roles: {roles}

Series package context:
{series_package_summary or "No separate series package is available yet."}

Check for:
- Missing required role voices.
- Overlong monologues that should be split for TTS.
- Flat or generic dialogue.
- Confusing or unsupported {profile.mechanics_label}.
- Continuity mistakes or unresolved injected beats.
- Places where a narrator, host, announcer, or recurring audio device would improve pacing.

Return actionable fixes first, then a concise pass/fail recommendation.

Script:
{part_script}
"""


def build_director_pass_prompt(
    *,
    part_script: str,
    required_roles: Sequence[str],
    series_package_summary: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    roles = ", ".join(required_roles)
    return f"""Mark performance intent for this {profile.script_label} script part.

Required roles: {roles}

Series package context:
{series_package_summary or "No separate series package is available yet."}

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
    story_bible_summary: str = "",
    series_package_summary: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    primary_check = (
        "XP totals, loot, inventory, cooldowns, class abilities, stats, quests, and status effects."
        if profile.is_litrpg
        else f"Track {profile.mechanics_examples}."
    )
    return f"""Audit {profile.mechanics_label} credibility for this chapter part.

Genre/style: {profile.genre}
Chapter premise: {chapter_premise}
Prior parts summary:
{prior_parts_summary or "This is the first part."}

Story bible continuity:
{story_bible_summary or "No separate story bible is available yet."}

Series package context:
{series_package_summary or "No separate series package is available yet."}

Check:
- {primary_check}
- Whether consumed items are removed or consequences are acknowledged.
- Whether the solution uses tools, facts, relationships, abilities, resources, or constraints available in the script or prior summary.
- Whether a character gains a new advantage, clue, item, alliance, or ability without earning it.
- Whether the story logic is audible enough for listeners to follow.

Return:
- verdict: pass, revise, or block.
- blocking_issues: concise list.
- fixes: concrete script-level fixes.

Script:
{part_script}
"""


def build_description_audit_prompt(
    *,
    part_script: str,
    story_bible_summary: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    return f"""Audit physical description and character visual continuity for this {profile.script_label} part.

Story bible continuity:
{story_bible_summary or "No separate story bible is available yet."}

Check as hard constraints, not optional polish:
- Are static visual anchors, current injuries, fatigue markers, gear condition, and absurd traits respected?
- Does at least one physical limitation or gear state affect a choice, movement, joke, or consequence?
- Are emotions shown through body, posture, voice texture, gear behavior, or environmental contact before being named?
- Does description develop character or plot instead of decorating the scene?
- Are recurring visual jokes reused with variation rather than copy-pasted?
- Does any item appear pristine after prior damage or disrepair?

Return compact JSON when possible:
{{
  "verdict": "pass|revise|block",
  "score": 1-10,
  "checks": {{
    "anchors_used": true,
    "degradation_respected": true,
    "physical_choice_consequence": true,
    "emotion_shown_physically": true,
    "visual_joke_callback": true
  }},
  "blocking_issues": [],
  "fixes": []
}}

Do not rewrite the script. Give strict director notes for revision.

Script:
{part_script}
"""


def build_visual_state_extraction_prompt(
    *,
    final_script: str,
    story_bible_summary: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    return f"""Extract updates for the character and visual continuity bible from this finalized {profile.script_label} script.

Existing story bible continuity:
{story_bible_summary or "No separate story bible is available yet."}

Return only JSON compatible with the StoryBible shape. Capture new or changed:
- visual_anchors_static
- visual_anchors_dynamic
- current_injuries
- fatigue_markers
- equipped_gear
- gear_absurd_traits
- description_rules
- wounds, traumas, running_jokes, rivalries, unresolved_promises, favorite_insults, never_contradict_facts, voice_rules

Do not remove existing facts. Do not invent facts not supported by the script.

Final script:
{final_script}
"""


def build_tonal_audit_prompt(*, part_script: str, target_tone: str = "", genre: str = "") -> str:
    profile = story_profile(genre)
    return f"""Score the chapter part on tonal control for {profile.genre}.

Target tone: {target_tone or profile.tonal_target}

Give two independent 1-10 ratings:
- stakes_seriousness: consequences feel emotionally real.
- genre_pressure: the chosen genre engine is active enough.

Reject or revise if the part is tonally flat, generic, or lets jokes erase consequences.

Return:
- stakes_seriousness
- genre_pressure
- verdict: pass, revise, or block.
- fixes: concrete changes that preserve the script's best material.

Script:
{part_script}
"""


def build_showmanship_audit_prompt(*, part_script: str, genre: str = "") -> str:
    profile = story_profile(genre)
    return f"""Simulate the {profile.showmanship_label} reviewing this chapter part.

Score 1-10:
- crowd_engagement
- intensity
- creativity
- emotional_payoff
- meme_potential
- sponsor_appeal

Then recommend one reveal, announcement, reward, punishment, or complication for the next part if useful.

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
    description_audit: str = "",
    series_package_summary: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    roles = ", ".join(required_roles)
    return f"""Revise this {profile.script_label} script part for render readiness.

Allowed role tags: {roles}

Series package context:
{series_package_summary or "No separate series package is available yet."}

Use the review material below as constraints, not as decorative notes.
Preserve strong jokes, character choices, and continuity. Fix blocking issues.
Keep XML-style role blocks only. Do not include markdown, explanations, or JSON.
Add style attributes sparingly when director intent matters, for example:
<HOST style="smug announcer, slapback">The room goes quiet.</HOST>

Director pass:
{director_tags}

Story logic audit:
{mechanics_audit}

Description and character audit:
{description_audit or "No description audit was run."}

Tonal audit:
{tonal_audit}

Showmanship audit:
{showmanship_audit}

Draft script:
{draft_script}
"""


def build_chapter_review_prompt(
    *,
    part_scripts: Sequence[str],
    cast_roles: Mapping[str, str],
    series_package_summary: str = "",
    genre: str = "",
) -> str:
    profile = story_profile(genre)
    cast = ", ".join(cast_roles)
    scripts = "\n\n".join(part_scripts)
    device_check = (
        "Whether SYSTEM/announcer moments land as events, not plain narration."
        if profile.is_litrpg
        else "Whether narrator, host, announcer, or recurring audio-device moments land as events, not plain narration."
    )
    return f"""Review the completed {profile.script_label} as a produced audio drama.

Cast roles available: {cast}
Genre/style: {profile.genre}

Series package context:
{series_package_summary or "No separate series package is available yet."}

Check:
- Character voice separation across at least 15 distinct roles where applicable.
- {device_check}
- Chapter pacing across parts: hook, escalation, rules reveal, setpiece, fallout, cliffhanger.
- Whether any role appears redundant and should be merged or rewritten.
- Whether any missing injected scene should be added before render.

Return a production review with blocking fixes, optional polish, and render readiness.

Chapter scripts:
{scripts}
"""
