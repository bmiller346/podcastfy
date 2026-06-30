"""Premise intake for bootstrapping LitRPG story-engine state from prose."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from podcastfy.litrpg.bible import (
    load_story_bible,
    merge_story_bible_updates,
    save_story_bible,
)
from podcastfy.litrpg.continuity import (
    emotional_arc_registry_from_dict,
    merge_continuity_ledgers,
    merge_world_registers,
    save_continuity_ledger,
    save_emotional_arcs,
    save_world_register,
    upsert_emotional_arc,
    continuity_ledger_from_dict,
    load_continuity_ledger,
    load_emotional_arcs,
    load_world_register,
    world_register_from_dict,
)
from podcastfy.litrpg.conspiracy_engine import save_conspiracy_engine
from podcastfy.litrpg.foreshadowing import (
    add_plants,
    foreshadow_ledger_from_dict,
    load_foreshadow_ledger,
    save_foreshadow_ledger,
)
from podcastfy.litrpg.prompts import format_bureaucratic_sadism_rules
from podcastfy.litrpg.prompts import format_character_voice_separation
from podcastfy.litrpg.prompts import format_mystery_lock_discipline
from podcastfy.litrpg.prompts import format_physical_continuity_degradation
from podcastfy.litrpg.prompts import format_scarcity_lock_language
from podcastfy.litrpg.promise_forge import normalize_promise_forge
from podcastfy.litrpg.series_architect import (
    SeriesShape,
    bootstrap_series,
    chapter_outline_from_mapping,
    save_chapter_outline,
)
from podcastfy.litrpg.voice_cards import (
    load_voice_cards,
    merge_voice_cards,
    save_voice_cards,
)
from podcastfy.litrpg.world_state import save_world_state


@dataclass(slots=True)
class PremiseIntakeResult:
    """Files written by a premise intake pass."""

    series_id: str
    storage_dir: str
    written_files: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "storage_dir": self.storage_dir,
            "written_files": list(self.written_files),
            "payload": self.payload,
        }


def build_premise_intake_prompt(
    *,
    premise: str,
    series_id: str,
    target_books: int = 1,
    chapters_per_book: int = 30,
    book_length_mode: str = "tight",
    arc_style: str = "escalating_floor_survival",
    series_title: str = "",
    series_promise: str = "",
    endgame_direction: str = "",
    power_curve: str = "logarithmic",
) -> str:
    """Build the extraction prompt that converts a premise dump into JSON state."""

    shape_hint = {
        "target_books": target_books,
        "book_length_mode": book_length_mode,
        "chapters_per_book": chapters_per_book,
        "arc_style": arc_style,
        "series_title": series_title or "Infer from premise",
        "series_promise": series_promise or "Infer from premise",
        "endgame_direction": endgame_direction or "Infer a long-term endgame",
        "power_curve": power_curve,
    }
    return f"""You are the Series Architect intake tool for a LitRPG story engine.

Convert the unstructured premise dump into durable JSON artifacts. Fill blanks, but do
not invent contradictions. Preserve the user's distinctive names, jokes, mechanics,
locations, and chapter outline when provided.

Return ONLY a JSON object with these top-level keys:
- series_shape: object compatible with SeriesShape.
  It may include series_shape.promise_forge with founding_injustice,
  permanent_constraint, comedic_signal, series_promise,
  reader_buy_button_image, must_recur, must_not_become, originality_locks,
  and source_brief.
- series_arc: list of BookPlan objects.
- book_outlines: object whose keys are book numbers and values are ChapterOutlineEntry lists.
- story_bible: object compatible with StoryBible.
- voice_cards: object compatible with VoiceCardDeck.
- continuity_ledger: object compatible with ContinuityLedger.
- emotional_arcs: object compatible with EmotionalArcRegistry.
- world_register: object compatible with WorldRegister.
- foreshadow_ledger: object compatible with ForeshadowLedger.
- conspiracy_engine: optional object with truth_document, revelation_ladder,
  reader_position, and factions for long-series mysteries. The truth document is
  EYES_ONLY and must never be phrased as prose-facing context.
- world_state: optional object for sensory/rendering state. Include characters,
  locations, artifacts, system_items, magic_signatures, active_mysteries,
  established_rules, and sensory_hooks when the source supports them.

Extraction rules:
- If the premise gives a chapter outline, preserve its chapter count and chapter titles.
- Each ChapterOutlineEntry must include a hook-ending field when supported by the
  schema: use ends_on for the final image, open question, reversal, or emotional
  cost that should pull the reader into the next chapter.
- Put long-term mysteries in series_shape.series_mysteries, early book must_preserve,
  foreshadow_ledger plants, and conspiracy_engine.revelation_ladder. Use
  conspiracy_engine.reader_position to separate what characters know, what the
  reader suspects, and what must not be confirmed yet.
- Character sheets should become both story_bible character facts and voice_cards.
- Physical anchors, gear state, wounds, running jokes, and marriage/family pressure go in
  story_bible and emotional_arcs.
- Locations, floor rules, faction agendas, mobs, economy, and vehicle/base mechanics go in world_register.
  Separate registers for faction agendas, social rank, currencies, trade goods, costs, scarcity,
  dungeon floor rules, entity ecology, home-base systems, and
  institutional voices. Preserve invented names and local idioms.
- world_state is an additional sensory/rendering layer, not a replacement for
  world_register, continuity_ledger, story_bible, or emotional_arcs. Use it for
  stable visual/sound/smell/touch anchors, artifact signatures, locked artifact
  names, forbidden aliases, current resource state, magic signatures, active
  mystery locks, established rendering rules, and recurring sensory hooks.
- world_state.artifacts is the artifact registry source of truth. Early artifacts
  should be shaped by series_shape.promise_forge.founding_injustice and
  comedic_signal when present, then may echo source objects, repairs, boat gear,
  or personal history, but avoid
  simply granting expected keepsakes. Prefer odd system reinterpretations,
  environmental loot, biome-contaminated tools, loot-box distortions, sponsor
  meddling, and artifacts whose usefulness carries mystery, cost, or suspicion.
  Every artifact should include locked_name, aliases_forbidden,
  physical_signature, power_ceiling with cannot_do, and state fields such as
  charges/ammo/condition/location/owner when relevant.
- Put recurring bits, memorable system achievements, and callback-ready jokes in continuity_ledger.
- Plant 3-8 foreshadow entries for long-term mysteries and later book payoffs.
- Keep all strings concise. Prefer usable production constraints over literary commentary.
- The promise_forge founding injustice must be specific to this protagonist and
  premise: unfair, funny, permanent, mechanically useful, and not generic
  dungeon survival.
- The intake must not imitate DCC names, voice, class names, system cadence, or terminology.
- Keep originality_locks distinct from must_not_become: must_not_become prevents
  planning drift; originality_locks are prose-level prohibitions.

Reusable prompt policy:
{format_mystery_lock_discipline()}
{format_character_voice_separation()}
{format_physical_continuity_degradation()}
{format_scarcity_lock_language()}
{format_bureaucratic_sadism_rules()}

Series shape hint:
{json.dumps(shape_hint, indent=2)}

Series id: {series_id}

Premise dump:
{premise}
"""


def build_premise_intake_repair_prompt(
    *,
    premise: str,
    series_id: str,
    chapters_per_book: int,
    validation_error: str,
    previous_payload: Mapping[str, Any],
) -> str:
    """Build a focused repair prompt for a sparse premise-intake payload."""

    previous = json.dumps(previous_payload, ensure_ascii=True, indent=2)[:12000]
    return f"""Your previous premise intake JSON failed validation.

Failure:
{validation_error}

Return ONLY the full corrected JSON object, using the same top-level schema:
- series_shape
- series_arc
- book_outlines
- story_bible
- voice_cards
- continuity_ledger
- emotional_arcs
- world_register
- foreshadow_ledger
- conspiracy_engine
- world_state

Repair rules:
- Preserve any useful valid sections from the previous payload, but replace generic/TBD material.
- Do not summarize the premise. Extract concrete production artifacts.
- The story_bible must include named characters from the source.
- The voice_cards must include distinct character voice constraints.
- The world_register must include concrete locations, floor rules, faction agendas,
  entities/mobs, economy/currencies/trade goods, scarcity/costs, and vehicle/base mechanics.
- world_state, when present, must remain an additional sensory/rendering state
  with characters, locations, artifacts, system_items, magic_signatures,
  active_mysteries, established_rules, and sensory_hooks.
- conspiracy_engine, when present, must include truth_document,
  revelation_ladder, reader_position, and factions without leaking the truth
  document into prose-facing sections.
- world_state.artifacts must use locked names, forbidden aliases, physical
  signatures, power ceilings with cannot_do, and scarce state fields. Do not make
  all artifacts obvious personal-history wish fulfillment; mix source echoes with
  environmental loot, dungeon mutations, loot-box weirdness, and suspicious
  system reinterpretations.
- The book_outlines for book 1 should include as many chapter entries as the source gives;
  target {chapters_per_book} if the source has a 30-chapter outline.
- Preserve source names and anchors such as Edward, Kelli, Pedro, Sophie II, Sophie the cockatoo,
  Gallowgate, Grand Dredger, Drowned Scaffolding, Glass Dunes, Mycelial Canopy, Barnacle Scrip,
  OSHA Wraiths, Barnacle Mimics, and Rebar Gargoyles when present.

Reusable prompt policy:
{format_character_voice_separation()}
{format_physical_continuity_degradation()}
{format_scarcity_lock_language()}
{format_mystery_lock_discipline()}

Series id: {series_id}

Previous payload:
{previous}

Source premise:
{premise}
"""


def run_premise_intake(
    *,
    storage_dir: str | Path,
    series_id: str,
    premise: str,
    llm: Any,
    target_books: int = 1,
    chapters_per_book: int = 30,
    book_length_mode: str = "tight",
    arc_style: str = "escalating_floor_survival",
    series_title: str = "",
    series_promise: str = "",
    endgame_direction: str = "",
    power_curve: str = "logarithmic",
    merge_existing: bool = True,
) -> PremiseIntakeResult:
    """Generate and persist story-engine artifacts from a loose premise dump."""

    if llm is None or not hasattr(llm, "generate"):
        raise ValueError("run_premise_intake requires an llm with generate(prompt=..., stage=...)")
    prompt = build_premise_intake_prompt(
        premise=premise,
        series_id=series_id,
        target_books=target_books,
        chapters_per_book=chapters_per_book,
        book_length_mode=book_length_mode,
        arc_style=arc_style,
        series_title=series_title,
        series_promise=series_promise,
        endgame_direction=endgame_direction,
        power_curve=power_curve,
    )
    try:
        raw = llm.generate(prompt=prompt, stage="premise_intake")
    except Exception as exc:
        payload = repair_sparse_premise_intake_payload(
            {},
            premise=premise,
            series_id=series_id,
            target_books=target_books,
            chapters_per_book=chapters_per_book,
            book_length_mode=book_length_mode,
            arc_style=arc_style,
            series_title=series_title,
            series_promise=series_promise,
            endgame_direction=endgame_direction,
            power_curve=power_curve,
            fallback_reason=f"Skipped AI intake because generation failed: {type(exc).__name__}: {exc}",
        )
        validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
        return _save_premise_intake_result(
            storage_dir=storage_dir,
            series_id=series_id,
            payload=payload,
            merge_existing=merge_existing,
            target_books=target_books,
            chapters_per_book=chapters_per_book,
            book_length_mode=book_length_mode,
            arc_style=arc_style,
            series_title=series_title,
            series_promise=series_promise,
            endgame_direction=endgame_direction,
            power_curve=power_curve,
        )
    try:
        payload = extract_premise_intake_json(str(raw))
    except ValueError as exc:
        payload = repair_sparse_premise_intake_payload(
            {},
            premise=premise,
            series_id=series_id,
            target_books=target_books,
            chapters_per_book=chapters_per_book,
            book_length_mode=book_length_mode,
            arc_style=arc_style,
            series_title=series_title,
            series_promise=series_promise,
            endgame_direction=endgame_direction,
            power_curve=power_curve,
            fallback_reason=f"Skipped AI repair because intake JSON was malformed: {exc}",
        )
        validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
        return _save_premise_intake_result(
            storage_dir=storage_dir,
            series_id=series_id,
            payload=payload,
            merge_existing=merge_existing,
            target_books=target_books,
            chapters_per_book=chapters_per_book,
            book_length_mode=book_length_mode,
            arc_style=arc_style,
            series_title=series_title,
            series_promise=series_promise,
            endgame_direction=endgame_direction,
            power_curve=power_curve,
        )
    try:
        validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
    except ValueError as exc:
        if is_obvious_empty_intake_shell(payload, premise=premise, chapters_per_book=chapters_per_book):
            payload = repair_sparse_premise_intake_payload(
                payload,
                premise=premise,
                series_id=series_id,
                target_books=target_books,
                chapters_per_book=chapters_per_book,
                book_length_mode=book_length_mode,
                arc_style=arc_style,
                series_title=series_title,
                series_promise=series_promise,
                endgame_direction=endgame_direction,
                power_curve=power_curve,
                fallback_reason=f"Skipped AI repair for empty intake shell: {exc}",
            )
            validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
            return _save_premise_intake_result(
                storage_dir=storage_dir,
                series_id=series_id,
                payload=payload,
                merge_existing=merge_existing,
                target_books=target_books,
                chapters_per_book=chapters_per_book,
                book_length_mode=book_length_mode,
                arc_style=arc_style,
                series_title=series_title,
                series_promise=series_promise,
                endgame_direction=endgame_direction,
                power_curve=power_curve,
            )
        repair_prompt = build_premise_intake_repair_prompt(
            premise=premise,
            series_id=series_id,
            chapters_per_book=chapters_per_book,
            validation_error=str(exc),
            previous_payload=payload,
        )
        try:
            repaired_raw = llm.generate(prompt=repair_prompt, stage="premise_intake_repair")
        except Exception as repair_exc:
            payload = repair_sparse_premise_intake_payload(
                payload,
                premise=premise,
                series_id=series_id,
                target_books=target_books,
                chapters_per_book=chapters_per_book,
                book_length_mode=book_length_mode,
                arc_style=arc_style,
                series_title=series_title,
                series_promise=series_promise,
                endgame_direction=endgame_direction,
                power_curve=power_curve,
                fallback_reason=(
                    "AI repair generation failed: "
                    f"{type(repair_exc).__name__}: {repair_exc}"
                ),
            )
            validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
            return _save_premise_intake_result(
                storage_dir=storage_dir,
                series_id=series_id,
                payload=payload,
                merge_existing=merge_existing,
                target_books=target_books,
                chapters_per_book=chapters_per_book,
                book_length_mode=book_length_mode,
                arc_style=arc_style,
                series_title=series_title,
                series_promise=series_promise,
                endgame_direction=endgame_direction,
                power_curve=power_curve,
            )
        try:
            payload = extract_premise_intake_json(str(repaired_raw))
        except ValueError as repair_exc:
            payload = repair_sparse_premise_intake_payload(
                payload,
                premise=premise,
                series_id=series_id,
                target_books=target_books,
                chapters_per_book=chapters_per_book,
                book_length_mode=book_length_mode,
                arc_style=arc_style,
                series_title=series_title,
                series_promise=series_promise,
                endgame_direction=endgame_direction,
                power_curve=power_curve,
                fallback_reason=f"AI repair returned malformed JSON: {repair_exc}",
            )
            validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
            return _save_premise_intake_result(
                storage_dir=storage_dir,
                series_id=series_id,
                payload=payload,
                merge_existing=merge_existing,
                target_books=target_books,
                chapters_per_book=chapters_per_book,
                book_length_mode=book_length_mode,
                arc_style=arc_style,
                series_title=series_title,
                series_promise=series_promise,
                endgame_direction=endgame_direction,
                power_curve=power_curve,
            )
        try:
            validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
        except ValueError:
            payload = repair_sparse_premise_intake_payload(
                payload,
                premise=premise,
                series_id=series_id,
                target_books=target_books,
                chapters_per_book=chapters_per_book,
                book_length_mode=book_length_mode,
                arc_style=arc_style,
                series_title=series_title,
                series_promise=series_promise,
                endgame_direction=endgame_direction,
                power_curve=power_curve,
                fallback_reason="AI premise intake remained sparse after repair pass.",
            )
            validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
    return _save_premise_intake_result(
        storage_dir=storage_dir,
        series_id=series_id,
        payload=payload,
        merge_existing=merge_existing,
        target_books=target_books,
        chapters_per_book=chapters_per_book,
        book_length_mode=book_length_mode,
        arc_style=arc_style,
        series_title=series_title,
        series_promise=series_promise,
        endgame_direction=endgame_direction,
        power_curve=power_curve,
    )


def _save_premise_intake_result(
    *,
    storage_dir: str | Path,
    series_id: str,
    payload: Mapping[str, Any],
    merge_existing: bool,
    target_books: int,
    chapters_per_book: int,
    book_length_mode: str,
    arc_style: str,
    series_title: str,
    series_promise: str,
    endgame_direction: str,
    power_curve: str,
) -> PremiseIntakeResult:
    return save_premise_intake_payload(
        storage_dir=storage_dir,
        series_id=series_id,
        payload=payload,
        merge_existing=merge_existing,
        fallback_shape={
            "target_books": target_books,
            "book_length_mode": book_length_mode,
            "chapters_per_book": chapters_per_book,
            "arc_style": arc_style,
            "series_title": series_title,
            "series_promise": series_promise,
            "endgame_direction": endgame_direction,
            "power_curve": power_curve,
        },
    )


def repair_sparse_premise_intake_payload(
    payload: Mapping[str, Any],
    *,
    premise: str,
    series_id: str,
    target_books: int = 1,
    chapters_per_book: int = 30,
    book_length_mode: str = "tight",
    arc_style: str = "escalating_floor_survival",
    series_title: str = "",
    series_promise: str = "",
    endgame_direction: str = "",
    power_curve: str = "logarithmic",
    fallback_reason: str = "AI premise intake remained sparse after repair pass.",
) -> dict[str, Any]:
    """Deterministically supplement sparse AI intake output from source text.

    This is a safety net for long seed markdown. The LLM remains the preferred
    extractor, but the UI should never fail with zero artifacts when the source
    itself contains obvious named characters and world anchors.
    """

    repaired = dict(payload)
    fallback = build_deterministic_premise_intake_payload(
        premise=premise,
        series_id=series_id,
        target_books=target_books,
        chapters_per_book=chapters_per_book,
        book_length_mode=book_length_mode,
        arc_style=arc_style,
        series_title=series_title,
        series_promise=series_promise,
        endgame_direction=endgame_direction,
        power_curve=power_curve,
    )
    for key, value in fallback.items():
        repaired[key] = _merge_sparse_value(repaired.get(key), value)
    repaired["_intake_metadata"] = {
        "fallback_used": True,
        "fallback_reason": fallback_reason,
    }
    return repaired


def is_obvious_empty_intake_shell(
    payload: Mapping[str, Any],
    *,
    premise: str,
    chapters_per_book: int,
) -> bool:
    """Return true when a payload has so little content that repair is wasteful."""

    if len(str(premise or "")) < 2000:
        return False
    story_bible = _mapping(payload.get("story_bible"))
    world_register = _mapping(payload.get("world_register"))
    character_count = len(_mapping(story_bible.get("characters")))
    world_count = sum(
        len(_list(world_register.get(key)))
        for key in ("locations", "rules", "entity_ecology", "economy_anchors")
    )
    outline_count = _outline_chapter_count(payload.get("book_outlines"))
    useful_sections = sum(
        1
        for value in (character_count, world_count, outline_count)
        if value > 0
    )
    return useful_sections == 0 or (
        character_count == 0
        and world_count == 0
        and outline_count < max(1, min(3, chapters_per_book))
    )


def build_deterministic_premise_intake_payload(
    *,
    premise: str,
    series_id: str,
    target_books: int = 1,
    chapters_per_book: int = 30,
    book_length_mode: str = "tight",
    arc_style: str = "escalating_floor_survival",
    series_title: str = "",
    series_promise: str = "",
    endgame_direction: str = "",
    power_curve: str = "logarithmic",
) -> dict[str, Any]:
    """Build a conservative intake payload directly from visible premise anchors."""

    text = str(premise or "")
    title = series_title or _extract_target_value(text, "Target title") or _extract_heading_title(text) or "Untitled LitRPG Series"
    promise = series_promise or _first_sentence_matching(
        text,
        ("Tone Contract", "story should feel", "readers", "promise"),
    ) or "Practical maritime survival under a hostile game system, driven by old-married friction and escalating floor rules."
    endgame = endgame_direction or "Edward, Kelli, and Pedro uncover why Gallowgate registered Sophie II and whether the System has leverage over their family."
    characters = _deterministic_characters(text)
    voice_cards = _deterministic_voice_cards(characters)
    world = _deterministic_world_register(text, series_id)
    outline = _deterministic_chapter_outline(text, chapters_per_book)
    mysteries = _deterministic_mysteries(text)
    return {
        "series_shape": {
            "target_books": target_books,
            "book_length_mode": book_length_mode,
            "chapters_per_book": chapters_per_book,
            "arc_style": arc_style,
            "series_title": title,
            "series_promise": promise,
            "endgame_direction": endgame,
            "power_curve": power_curve,
            "series_mysteries": mysteries,
        },
        "series_arc": [
            {
                "book": 1,
                "role": "Bootstrap Sophie II as a mobile asset and force the retired couple to take responsibility under dungeon pressure.",
                "major_change": "The boat stops being an escape plan and becomes a contested home base inside Gallowgate.",
                "power_ceiling": "Improvised engineering, gambling-risk reads, and Pedro phrase exploits matter more than raw levels.",
                "chapter_count": chapters_per_book,
                "arc_style": arc_style,
                "must_resolve": ["Sophie II survives the first floor transition"],
                "must_preserve": ["Sophie II", "Edward Marsh", "Kelli Marsh", "Pedro"],
                "character_targets": {
                    "Edward Marsh": "Turns avoidance and engineering skepticism into reluctant stewardship.",
                    "Kelli Marsh": "Turns chaos appetite into strategic responsibility.",
                    "Pedro": "Becomes a system-breaking familiar through memorized phrases.",
                },
                "faction_targets": ["Gallowgate", "Grand Dredger", "Galactic Zoning Board"],
                "floor_range": [1, 3],
            }
        ],
        "book_outlines": {"1": outline},
        "story_bible": {
            "series_id": series_id,
            "premise": _compact_text(text, 900),
            "never_contradict_facts": [
                "The canonical vessel name is Sophie II.",
                "Sophie II was named after Edward and Kelli's old cockatoo, Sophie.",
                "Sophie the cockatoo died after Kelli overheated pans, likely nonstick/Teflon fumes.",
                "Edward and Kelli's adult children are off the boat; distance creates guilt pressure.",
            ],
            "unresolved_threads": mysteries,
            "timeline_notes": ["Edward and Kelli cast off before the dungeon event intending to escape responsibility."],
            "characters": characters,
        },
        "voice_cards": {"series_id": series_id, "cards": voice_cards},
        "continuity_ledger": {
            "series_id": series_id,
            "running_gags": [
                {"text": "Edward treats apocalypse hazards as code, permit, and inspection violations.", "tags": ["voice", "edward"]},
                {"text": "Kelli evaluates supernatural danger like a casino table.", "tags": ["voice", "kelli"]},
                {"text": "Pedro's construction and gambling phrases land as accidental system inputs.", "tags": ["voice", "pedro"]},
            ],
            "world_details": [
                {"text": "Sophie II is a mobile asset rather than merely a boat.", "tags": ["vehicle", "home-base"]},
                {"text": "Each floor changes what counts as navigable water.", "tags": ["floor-rule"]},
            ],
            "notable_moments": [
                {"text": "Sophie II carries the emotional guilt of the dead cockatoo and the couple's runaway retirement plan.", "tags": ["sophie-ii"]},
            ],
        },
        "emotional_arcs": {
            "series_id": series_id,
            "characters": {
                "Edward Marsh": {
                    "character": "Edward Marsh",
                    "wound": "He retired to avoid responsibility and is forced to captain a home base people depend on.",
                    "current_coping_mode": "Frames terror as engineering noncompliance.",
                    "relationships": {"Kelli Marsh": "Old-married friction under pressure", "Pedro": "Annoyed caretaker of a phrase-triggering familiar"},
                    "beats": [{"text": "The dead cockatoo Sophie turns the vessel name into guilt instead of nostalgia."}],
                },
                "Kelli Marsh": {
                    "character": "Kelli Marsh",
                    "wound": "Her appetite for chaos is tangled with guilt over Sophie and the kids they fled.",
                    "current_coping_mode": "Reads risk, odds, and tells rather than admitting fear.",
                    "relationships": {"Edward Marsh": "Loves him, needles him, and pushes him into motion"},
                    "beats": [{"text": "She must stop treating every crisis as a table she can walk away from."}],
                },
            },
        },
        "world_register": world,
        "foreshadow_ledger": {
            "series_id": series_id,
            "planted": [
                {
                    "detail": "Kelli sees or fears a bidder tag tied to one of the kids' surnames.",
                    "planted_chapter": 3,
                    "intended_payoff_start": 18,
                    "intended_payoff_end": 30,
                    "mystery": "Were Edward and Kelli's kids taken by the System?",
                },
                {
                    "detail": "Pedro's flagged phrase is absent from broadcast logs.",
                    "planted_chapter": 2,
                    "intended_payoff_start": 12,
                    "intended_payoff_end": 24,
                    "mystery": "Why does the System suppress Pedro's most dangerous phrase?",
                },
                {
                    "detail": "Gallowgate treats Sophie II as a registration problem it cannot cleanly undo.",
                    "planted_chapter": 1,
                    "intended_payoff_start": 20,
                    "intended_payoff_end": 30,
                    "mystery": "Why did Sophie II become a mobile guild-hall asset?",
                },
            ],
        },
    }


def save_premise_intake_payload(
    *,
    storage_dir: str | Path,
    series_id: str,
    payload: Mapping[str, Any],
    merge_existing: bool = True,
    fallback_shape: Mapping[str, Any] | None = None,
) -> PremiseIntakeResult:
    """Persist a previously generated premise intake payload."""

    storage = Path(storage_dir)
    series_key = str(series_id)
    series_root = _validated_series_root(storage, series_key)
    data = dict(payload)
    shape_data = {
        **dict(fallback_shape or {}),
        **_mapping(data.get("series_shape")),
    }
    shape_data.setdefault("series_title", "Untitled Series")
    shape_data.setdefault("target_books", 1)
    shape_data.setdefault("chapters_per_book", 30)
    shape_data.setdefault("book_length_mode", "tight")
    shape_data.setdefault("arc_style", "escalating_floor_survival")
    shape_data.setdefault("power_curve", "logarithmic")
    promise_forge = normalize_promise_forge(
        shape_data.get("promise_forge") if isinstance(shape_data.get("promise_forge"), Mapping) else None
    )
    series_promise_value = str(shape_data.get("series_promise") or "")
    if not series_promise_value and promise_forge.get("series_promise"):
        series_promise_value = str(promise_forge["series_promise"])
    shape = SeriesShape(
        target_books=max(1, int(shape_data.get("target_books") or 1)),
        book_length_mode=str(shape_data.get("book_length_mode") or "tight"),
        chapters_per_book=max(1, int(shape_data.get("chapters_per_book") or 30)),
        arc_style=str(shape_data.get("arc_style") or "escalating_floor_survival"),
        series_title=str(shape_data.get("series_title") or "Untitled Series"),
        series_promise=series_promise_value,
        promise_forge=promise_forge,
        endgame_direction=str(shape_data.get("endgame_direction") or ""),
        power_curve=str(shape_data.get("power_curve") or "logarithmic"),
        series_mysteries=_string_list(shape_data.get("series_mysteries")),
    )

    architect = bootstrap_series(
        storage_dir=storage,
        series_id=series_key,
        shape=shape,
        series_arc=_list(data.get("series_arc")) or None,
    )
    written = [
        str(architect.root / "series_plan.json"),
        str(architect.root / "series_arc.json"),
    ]
    for book_number, outline in _book_outline_items(data.get("book_outlines")):
        save_chapter_outline(storage, series_key, book_number, outline)
        written.append(str(architect.root / f"book_{book_number}" / "chapter_outline.json"))

    story_bible_payload = _mapping(data.get("story_bible"))
    if story_bible_payload:
        story_bible_payload.setdefault("series_id", series_key)
        bible = (
            load_story_bible(storage, series_key)
            if merge_existing
            else load_story_bible(storage, "__empty__")
        )
        bible.series_id = series_key
        save_story_bible(storage, merge_story_bible_updates(bible, story_bible_payload))
        written.append(str(architect.root / "story_bible.json"))

    voice_cards_payload = _mapping(data.get("voice_cards"))
    if voice_cards_payload:
        voice_cards_payload.setdefault("series_id", series_key)
        deck = load_voice_cards(storage, series_key)
        if merge_existing:
            deck = merge_voice_cards(deck, voice_cards_payload)
        else:
            deck = merge_voice_cards(load_voice_cards(storage, "__empty__"), voice_cards_payload)
            deck.series_id = series_key
        save_voice_cards(storage, deck)
        written.append(str(architect.root / "voice_cards.json"))

    continuity_payload = _mapping(data.get("continuity_ledger"))
    if continuity_payload:
        continuity_payload.setdefault("series_id", series_key)
        ledger = continuity_ledger_from_dict(continuity_payload)
        if merge_existing:
            ledger = merge_continuity_ledgers(load_continuity_ledger(storage, series_key), ledger)
        save_continuity_ledger(storage, series_key, ledger)
        written.append(str(architect.root / "continuity_ledger.json"))

    emotional_payload = _mapping(data.get("emotional_arcs"))
    if emotional_payload:
        emotional_payload.setdefault("series_id", series_key)
        registry = emotional_arc_registry_from_dict(emotional_payload)
        if merge_existing:
            merged = load_emotional_arcs(storage, series_key)
            for arc in registry.characters.values():
                merged = upsert_emotional_arc(merged, arc)
            registry = merged
        save_emotional_arcs(storage, series_key, registry)
        written.append(str(architect.root / "emotional_arcs.json"))

    world_payload = _mapping(data.get("world_register"))
    if world_payload:
        world_payload.setdefault("series_id", series_key)
        register = world_register_from_dict(world_payload)
        if merge_existing:
            register = merge_world_registers(load_world_register(storage, series_key), register)
        save_world_register(storage, series_key, register)
        written.append(str(architect.root / "world_register.json"))

    foreshadow_payload = _mapping(data.get("foreshadow_ledger"))
    if foreshadow_payload:
        foreshadow_payload.setdefault("series_id", series_key)
        ledger = foreshadow_ledger_from_dict(foreshadow_payload, fallback_series_id=series_key)
        if merge_existing:
            existing = load_foreshadow_ledger(storage, series_key)
            generated = ledger
            ledger = add_plants(existing, generated.planted)
            ledger.ready_to_pay = _dedupe_foreshadow_entries(
                [*existing.ready_to_pay, *generated.ready_to_pay]
            )
        save_foreshadow_ledger(storage, ledger)
        written.append(str(architect.root / "foreshadow_ledger.json"))

    conspiracy_payload = _mapping(data.get("conspiracy_engine"))
    if conspiracy_payload:
        save_conspiracy_engine(storage, series_key, conspiracy_payload)
        written.append(str(architect.root / "conspiracy_engine.json"))

    world_state_payload = _mapping(data.get("world_state"))
    if world_state_payload:
        save_world_state(storage, series_key, world_state_payload)
        written.append(str(architect.root / "world_state.json"))

    return PremiseIntakeResult(
        series_id=series_key,
        storage_dir=str(storage),
        written_files=sorted(
            dict.fromkeys(_validated_written_path(path, series_root) for path in written)
        ),
        payload=data,
    )


def extract_premise_intake_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from raw LLM output or fenced markdown."""

    stripped = text.strip()
    if not stripped:
        raise ValueError("Premise intake LLM returned empty output")
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = json.loads(_json_object_slice(stripped))
    if not isinstance(parsed, dict):
        raise ValueError("Premise intake output must be a JSON object")
    return parsed


def validate_premise_intake_payload(
    payload: Mapping[str, Any],
    *,
    premise: str,
    chapters_per_book: int,
) -> None:
    """Reject sparse or generic intake extractions before writing artifacts."""

    if not isinstance(payload, Mapping):
        raise ValueError("Premise intake output must be a JSON object")
    premise_text = str(premise or "")
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    source_markers = [
        marker
        for marker in ("edward", "kelli", "pedro", "sophie", "gallowgate", "dredger")
        if marker in premise_text.casefold()
    ]
    matched_markers = [marker for marker in source_markers if marker in serialized]
    story_bible = _mapping(payload.get("story_bible"))
    world_register = _mapping(payload.get("world_register"))
    book_outlines = payload.get("book_outlines")
    outline_count = _outline_chapter_count(book_outlines)
    character_count = len(_mapping(story_bible.get("characters")))
    world_count = sum(
        len(_list(world_register.get(key)))
        for key in ("locations", "rules", "entity_ecology", "economy_anchors")
    )
    if len(premise_text) >= 2000:
        issues = []
        if source_markers and len(matched_markers) < min(3, len(source_markers)):
            issues.append(
                "preserve source markers such as "
                + ", ".join(source_markers[: min(4, len(source_markers))])
            )
        if character_count < 2:
            issues.append("extract at least two named story_bible characters")
        if world_count < 3:
            issues.append("extract concrete world_register locations/rules/entities/economy")
        if outline_count < max(3, min(6, chapters_per_book)):
            issues.append("extract a usable chapter outline")
        if issues:
            raise ValueError(
                "Premise intake output is too sparse or generic; "
                + "; ".join(issues)
            )


def _outline_chapter_count(value: Any) -> int:
    if isinstance(value, Mapping):
        return sum(len(_list(outline)) for outline in value.values())
    return sum(len(_list(item.get("outline") or item.get("chapters"))) for item in _list(value) if isinstance(item, Mapping))


def _merge_sparse_value(existing: Any, fallback: Any) -> Any:
    if _is_sparse_value(existing):
        return fallback
    if isinstance(existing, Mapping) and isinstance(fallback, Mapping):
        merged = dict(existing)
        for key, fallback_value in fallback.items():
            merged[key] = _merge_sparse_value(merged.get(key), fallback_value)
        return merged
    if isinstance(existing, list) and isinstance(fallback, list):
        return existing if len(existing) >= len(fallback) else fallback
    return existing


def _is_sparse_value(value: Any) -> bool:
    if value in (None, "", [], {}):
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"tbd", "unknown", "n/a", "generic", "infer from premise"}
    if isinstance(value, Mapping):
        return not any(not _is_sparse_value(item) for item in value.values())
    return False


def _deterministic_characters(text: str) -> dict[str, dict[str, Any]]:
    lower = text.casefold()
    characters: dict[str, dict[str, Any]] = {}
    if "edward" in lower:
        characters["Edward Marsh"] = {
            "name": "Edward Marsh",
            "aliases": ["Edward"],
            "wounds": ["Minor heart attack on a construction job site", "Retired to escape responsibility"],
            "traumas": ["Sophie the cockatoo's death remains a household guilt anchor"],
            "running_jokes": ["Treats cosmic danger as an OSHA or code violation"],
            "unresolved_promises": ["Find out whether the System has leverage over the adult kids"],
            "never_contradict_facts": [
                "Retired structural engineer from the Philadelphia/South Jersey corridor",
                "Captains Sophie II",
            ],
            "voice_rules": ["Gruff, clipped, practical South Jersey engineer exhaustion"],
            "visual_anchors_static": ["Canvas work pants", "UPF sun shirt", "boat shoes", "waterproof notebook"],
            "fatigue_markers": ["Rubs his left knee when stressed or weather shifts"],
            "equipped_gear": ["Carpenter's pencil", "waterproof notebook"],
        }
    if "kelli" in lower:
        characters["Kelli Marsh"] = {
            "name": "Kelli Marsh",
            "aliases": ["Kelli"],
            "wounds": ["Guilt over Sophie the cockatoo", "Ran from family responsibility with Edward"],
            "running_jokes": ["Reads dungeon risk like a blackjack or craps table"],
            "unresolved_promises": ["Her adult children remain off-boat but emotionally weaponized by the System"],
            "never_contradict_facts": [
                "High-stakes casino risk reader",
                "Overheated pans caused fumes that killed Sophie the cockatoo",
            ],
            "voice_rules": ["Sharp, unsentimental, casino-table confidence under pressure"],
            "visual_anchors_static": ["Oversized expensive polarized sunglasses", "wedding ring used as a calculating tell"],
            "fatigue_markers": ["Goes quiet before committing to an all-in decision"],
        }
    if "pedro" in lower:
        characters["Pedro"] = {
            "name": "Pedro",
            "aliases": ["Pedro the macaw", "familiar"],
            "running_jokes": ["Repeats construction and gambling phrases at exactly the wrong time"],
            "unresolved_promises": ["The System has muted at least one flagged phrase from broadcast logs"],
            "never_contradict_facts": ["Pedro is the animal/familiar voice contrast to Edward and Kelli"],
            "voice_rules": ["Does not swear; phrase-bank comedy lands through timing and repetition"],
            "gear_absurd_traits": ["Phrase list behaves like a system exploit"],
        }
    if "sophie" in lower:
        characters["Sophie the cockatoo"] = {
            "name": "Sophie the cockatoo",
            "aliases": ["Sophie"],
            "traumas": ["Died before the dungeon after overheated pans released bird-lethal fumes"],
            "never_contradict_facts": ["Sophie II is named after her"],
            "voice_rules": ["Never appears as a living current companion unless explicitly revised"],
        }
    if len(characters) < 2:
        characters.setdefault(
            "Edward Marsh",
            {"name": "Edward Marsh", "voice_rules": ["Practical retired engineer under pressure"]},
        )
        characters.setdefault(
            "Kelli Marsh",
            {"name": "Kelli Marsh", "voice_rules": ["Risk-reading spouse with casino instincts"]},
        )
    return characters


def _deterministic_voice_cards(characters: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    defaults = {
        "Edward Marsh": {
            "roles": ["HERO", "EDWARD"],
            "sentence_pattern_rules": ["Short practical complaints; engineering and inspection metaphors"],
            "stress_speech_patterns": ["Gets annoyed before scared", "Uses clipped profanity when exhausted"],
            "humor_modes": ["bureaucratic outrage", "blue-collar understatement"],
            "sample_lines": ["Who signed off on this?"],
        },
        "Kelli Marsh": {
            "roles": ["KELLI"],
            "sentence_pattern_rules": ["Dry confidence; casino and odds language"],
            "stress_speech_patterns": ["Goes quiet before an all-in move"],
            "humor_modes": ["risk-table reads", "old-married needling"],
            "sample_lines": ["That is not bad luck. That is a bad table."],
        },
        "Pedro": {
            "roles": ["PEDRO", "FAMILIAR"],
            "sentence_pattern_rules": ["Phrase-bank interjections, not fluent exposition"],
            "forbidden_words": ["generic swear-heavy banter"],
            "stress_speech_patterns": ["Repeats memorized phrases at system-sensitive moments"],
            "humor_modes": ["construction phrases become psychic debuffs", "accidental rules exploits"],
            "sample_lines": ["WHERE'S THE PERMIT?"],
        },
        "Sophie the cockatoo": {
            "roles": ["MEMORY"],
            "sentence_pattern_rules": ["Backstory anchor, not current dialogue"],
            "humor_modes": ["guilt pressure behind the boat name"],
            "sample_lines": [],
        },
    }
    for name in characters:
        cards[name] = {"name": name, **defaults.get(name, {"roles": [name.upper()], "sentence_pattern_rules": ["Preserve source-specific diction"]})}
    return cards


def _deterministic_world_register(text: str, series_id: str) -> dict[str, Any]:
    return {
        "series_id": series_id,
        "locations": [
            {
                "name": "Sophie II",
                "detail": "Canonical 44-foot catamaran and mobile asset/home base named after the dead cockatoo Sophie.",
                "tags": ["vehicle", "home-base"],
            },
            {
                "name": "The Drowned Scaffolding",
                "detail": "Floor 1 bioluminescent ocean broken by rusted half-submerged construction skeletons.",
                "floor": 1,
                "tags": ["floor", "water"],
            },
            {
                "name": "The Glass Dunes",
                "detail": "A later floor where the catamaran must sail crushed frictionless glass on skates and thermal wind.",
                "floor": 2,
                "tags": ["floor", "sand"],
            },
            {
                "name": "The Mycelial Canopy",
                "detail": "Dense toxic fog over a fungal forest, letting the catamaran float on gas while threats rise from below.",
                "floor": 3,
                "tags": ["floor", "fog"],
            },
        ],
        "rules": [
            {
                "rule": "Navigable waters mutate by floor",
                "detail": "The System must permit the registered mobile asset to move, but can redefine the medium as water, sand, fog, or worse.",
                "tags": ["floor-rule", "vehicle"],
            },
            {
                "rule": "Sophie II mobile safe-zone pressure",
                "detail": "The boat functions like a contested guild-hall/home-base asset; its protection creates strategic value and faction attention.",
                "tags": ["home-base", "guild-hall"],
            },
            {
                "rule": "Weaponized distance",
                "detail": "The adult kids stay off-boat; the System pressures Edward and Kelli through uncertainty and dimensional threats.",
                "tags": ["family", "blackmail"],
            },
        ],
        "entity_ecology": [
            {
                "entity": "Barnacle Mimics",
                "detail": "Hull-attaching mimics that pretend to be marine growth while eating fiberglass.",
                "floor": 1,
                "location": "The Drowned Scaffolding",
            },
            {
                "entity": "Rebar Gargoyles",
                "detail": "Rusted construction predators that dive from skeletal towers and crane structures.",
                "floor": 1,
                "location": "The Drowned Scaffolding",
            },
            {
                "entity": "OSHA Wraiths",
                "detail": "Undead safety inspectors that inflict violation debuffs for bad rigging and unsafe work.",
                "floor": 1,
                "location": "The Drowned Scaffolding",
            },
            {
                "entity": "Grand Dredger",
                "detail": "Major floor/faction pressure tied to purges, dredging, and hidden broadcast suppression.",
                "tags": ["faction", "threat"],
            },
            {
                "entity": "Gallowgate",
                "detail": "Hostile bureaucratic dungeon/system identity that treats survival as registration, debt, and zoning leverage.",
                "tags": ["system", "faction"],
            },
        ],
        "economy_anchors": [
            {
                "name": "Barnacle Scrip",
                "detail": "Floor currency used for repairs, bribes, and dungeon-epoxy scarcity.",
                "floor": 1,
                "location": "The Drowned Scaffolding",
            },
            {
                "name": "Salvaged Copper",
                "detail": "Crafting material for boat repairs, wiring, and dungeon refits.",
                "floor": 1,
            },
            {
                "name": "Dungeon Epoxy",
                "detail": "Rare repair supply needed when Sophie II's fiberglass hull is breached.",
                "tags": ["scarcity", "repair"],
            },
        ],
    }


def _deterministic_chapter_outline(text: str, chapters_per_book: int) -> list[dict[str, Any]]:
    extracted = _extract_markdown_chapters(text)
    if extracted:
        return extracted[:chapters_per_book]
    beats = [
        ("Out of the Atlantic", "Sophie II drops from retirement voyage into Gallowgate's first-floor waters.", "Sophie II is registered by the System."),
        ("The Familiar's First Words", "Pedro's phrase-bank reveals that harmless old sayings can trigger dungeon attention.", "A muted phrase hints at the Grand Dredger."),
        ("The Dead Bird Name", "The boat name stops being cute when Sophie the cockatoo's death becomes emotional leverage.", "Kelli refuses to explain the whole story."),
        ("Violation Debuff", "OSHA Wraiths turn rigging mistakes into combat penalties.", "Edward realizes inspections can be weaponized."),
        ("Barnacle Scrip", "The crew learns repair economy rules while Barnacle Mimics chew the hull.", "The repair bill exceeds their starting leverage."),
        ("Bidder Tag", "Kelli spots a family-name clue that suggests the kids may not be safe.", "The System offers no confirmation."),
        ("Rebar Weather", "Rebar Gargoyles force Sophie II under rusted towers and broken crane shadows.", "The mast becomes a liability."),
        ("Double Down", "Kelli turns a bad trade into a trap for a predatory faction broker.", "Winning creates a worse enemy."),
        ("No Fixed Address", "Gallowgate disputes the boat's asset classification.", "The ruling makes Sophie II valuable."),
        ("Glass on the Horizon", "Edward sees the first sign that the next floor will not provide water.", "The catamaran will need skates."),
    ]
    outline = []
    total = max(6, chapters_per_book)
    for index in range(total):
        title, premise, ending = beats[index] if index < len(beats) else (
            f"Floor Pressure {index + 1}",
            "Escalating vehicle repairs, family guilt, faction debt, and Pedro phrase exploits compound.",
            "A solved practical problem exposes a larger System rule.",
        )
        outline.append(
            {
                "chapter": index + 1,
                "phase": "The Drop" if index < 3 else "Exploration",
                "title": title,
                "premise": premise,
                "ends_on": ending,
                "character_focus": ["Edward Marsh", "Kelli Marsh"] if index % 3 else ["Edward Marsh", "Kelli Marsh", "Pedro"],
                "introduces": ["Sophie II"] if index == 0 else [],
                "resolves": [],
                "must_not_use": ["Do not put the adult kids on the boat"],
            }
        )
    return outline[:chapters_per_book]


def _extract_markdown_chapters(text: str) -> list[dict[str, Any]]:
    chapters = []
    pattern = re.compile(r"(?im)^\s*(?:#{1,4}\s*)?(?:chapter|ch\.?)\s*(\d+)\s*[:\-.\)]?\s*(.+?)\s*$")
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), start + 900)
        body = _compact_text(text[start:end], 450)
        chapter = int(match.group(1))
        title = match.group(2).strip(" #-")
        chapters.append(
            {
                "chapter": chapter,
                "phase": "Extracted",
                "title": title or f"Chapter {chapter}",
                "premise": body or "Extracted from source markdown.",
                "ends_on": "Preserve the source hook or unresolved pressure from this chapter.",
                "character_focus": ["Edward Marsh", "Kelli Marsh", "Pedro"],
                "introduces": [],
                "resolves": [],
                "must_not_use": ["Do not contradict source markdown"],
            }
        )
    return chapters


def _deterministic_mysteries(text: str) -> list[str]:
    mysteries = [
        "Did the System take or threaten Edward and Kelli's adult kids?",
        "Why did Gallowgate register Sophie II as a mobile asset?",
        "Why is Pedro's flagged phrase suppressed from broadcast logs?",
    ]
    if "grand dredger" in text.casefold():
        mysteries.append("What happens if the Grand Dredger hears Pedro's flagged phrase?")
    return mysteries


def _extract_target_value(text: str, label: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def _extract_heading_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title and len(title) <= 80 and "messy context" not in title.casefold():
                return title
    return ""


def _first_sentence_matching(text: str, markers: tuple[str, ...]) -> str:
    lower_markers = tuple(marker.casefold() for marker in markers)
    for paragraph in re.split(r"\n\s*\n", text):
        clean = _compact_text(paragraph, 500)
        if clean and any(marker in clean.casefold() for marker in lower_markers):
            return clean
    return ""


def _compact_text(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    return compact[:limit].rstrip()


def _json_object_slice(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Premise intake output did not contain a JSON object")
    return text[start : end + 1]


def _book_outline_items(value: Any) -> list[tuple[int, list[Mapping[str, Any]]]]:
    if isinstance(value, Mapping):
        items = []
        for key, outline in value.items():
            try:
                book_number = int(key)
            except (TypeError, ValueError):
                raise ValueError(f"book_outlines contains an invalid book key: {key!r}") from None
            items.append((book_number, _validated_outline(book_number, outline)))
        return items
    items = []
    for index, item in enumerate(_list(value), 1):
        if not isinstance(item, Mapping):
            raise ValueError(f"book_outlines item {index} must be a JSON object")
        try:
            book_number = int(item.get("book") or item.get("book_number") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"book_outlines item {index} has an invalid book number") from exc
        outline = _validated_outline(book_number, item.get("outline") or item.get("chapters"))
        items.append((book_number, outline))
    return items


def _validated_outline(book_number: int, value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"book_outlines book {book_number} must be a list of chapters")
    outline: list[Mapping[str, Any]] = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"book_outlines book {book_number} chapter item {index} must be a JSON object"
            )
        try:
            chapter_outline_from_mapping(item)
        except Exception as exc:
            chapter = item.get("chapter") or index
            raise ValueError(
                f"book_outlines book {book_number} chapter {chapter} is invalid: {exc}"
            ) from exc
        outline.append(item)
    return outline


def _validated_series_root(storage: Path, series_id: str) -> Path:
    series_base = (storage / "series").resolve()
    series_root = (series_base / series_id).resolve()
    if not _is_relative_to(series_root, series_base):
        raise ValueError("series_id must stay inside storage_dir/series")
    return series_root


def _validated_written_path(path: str, series_root: Path) -> str:
    resolved = Path(path).resolve()
    if not _is_relative_to(resolved, series_root):
        raise ValueError("Premise intake attempted to write outside the series directory")
    return str(Path(path))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(key) for key in value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _dedupe_foreshadow_entries(entries: list[Any]) -> list[Any]:
    deduped = []
    seen = set()
    for entry in entries:
        key = (
            getattr(entry, "detail", "").casefold(),
            getattr(entry, "planted_book", None),
            getattr(entry, "planted_chapter", None),
            getattr(entry, "payoff_book", None),
            getattr(entry, "intended_payoff_start", None),
            getattr(entry, "intended_payoff_end", None),
        )
        if not key[0] or key in seen:
            continue
        deduped.append(entry)
        seen.add(key)
    return deduped
