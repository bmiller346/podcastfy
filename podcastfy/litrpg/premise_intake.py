"""Premise intake for bootstrapping LitRPG story-engine state from prose."""

from __future__ import annotations

import json
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
from podcastfy.litrpg.foreshadowing import (
    add_plants,
    foreshadow_ledger_from_dict,
    load_foreshadow_ledger,
    save_foreshadow_ledger,
)
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
- series_arc: list of BookPlan objects.
- book_outlines: object whose keys are book numbers and values are ChapterOutlineEntry lists.
- story_bible: object compatible with StoryBible.
- voice_cards: object compatible with VoiceCardDeck.
- continuity_ledger: object compatible with ContinuityLedger.
- emotional_arcs: object compatible with EmotionalArcRegistry.
- world_register: object compatible with WorldRegister.
- foreshadow_ledger: object compatible with ForeshadowLedger.

Extraction rules:
- If the premise gives a chapter outline, preserve its chapter count and chapter titles.
- Each ChapterOutlineEntry must include a hook-ending field when supported by the
  schema: use ends_on for the final image, open question, reversal, or emotional
  cost that should pull the reader into the next chapter.
- Put long-term mysteries in series_shape.series_mysteries, early book must_preserve,
  and foreshadow_ledger plants. Track planted chapter ranges, payoff windows,
  clue wording, red herrings, and what must not be revealed yet.
- Character sheets should become both story_bible character facts and voice_cards.
  Voice cards must capture diction, sentence rhythm, taboo phrases, favorite
  insults, humor modes, pressure tells, emotional leakage, role tags, and how
  the character sounds different in fear, anger, tenderness, and tactical focus.
- Physical anchors, gear state, wounds, running jokes, and marriage/family pressure go in
  story_bible and emotional_arcs.
- Visual continuity is mandatory: capture static anchors, dynamic degradation,
  current injuries, fatigue markers, gear damage/repairs, base/vehicle damage,
  absurd physical traits, and rules for how bodies or equipment worsen over time.
- Locations, floor rules, faction agendas, mobs, economy, currencies, trade goods, costs, scarcity, and vehicle/base mechanics go in world_register.
  Separate registers for faction agendas, social rank, currencies, trade goods, costs, scarcity,
  dungeon floor rules, entity ecology, home-base systems, and
  institutional voices. Preserve invented names and local idioms.
- Put recurring bits, memorable system achievements, and callback-ready jokes in continuity_ledger.
- Plant 3-8 foreshadow entries for long-term mysteries and later book payoffs.
- Keep all strings concise. Prefer usable production constraints over literary commentary.

Series shape hint:
{json.dumps(shape_hint, indent=2)}

Series id: {series_id}

Premise dump:
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
    raw = llm.generate(prompt=prompt, stage="premise_intake")
    payload = extract_premise_intake_json(str(raw))
    validate_premise_intake_payload(payload, premise=premise, chapters_per_book=chapters_per_book)
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
    shape = SeriesShape(
        target_books=max(1, int(shape_data.get("target_books") or 1)),
        book_length_mode=str(shape_data.get("book_length_mode") or "tight"),
        chapters_per_book=max(1, int(shape_data.get("chapters_per_book") or 30)),
        arc_style=str(shape_data.get("arc_style") or "escalating_floor_survival"),
        series_title=str(shape_data.get("series_title") or "Untitled Series"),
        series_promise=str(shape_data.get("series_promise") or ""),
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
