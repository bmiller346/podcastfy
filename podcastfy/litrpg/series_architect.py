"""Series-level planning contracts for long-form local audio stories."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.showrunner import (
    ABSURDITY_DIRECTIVES,
    CREATIVITY_DIRECTIVES,
    TENSION_DIRECTIVES,
)

SERIES_PLAN_FILENAME = "series_plan.json"
SERIES_ARC_FILENAME = "series_arc.json"
BOOK_PLAN_FILENAME = "book_plan.json"
TEMPO_MAP_FILENAME = "tempo_map.json"
CHAPTER_OUTLINE_FILENAME = "chapter_outline.json"


@dataclass(slots=True)
class SeriesShape:
    target_books: int = 1
    book_length_mode: str = "standard"
    chapters_per_book: int = 60
    arc_style: str = "escalating_floor_survival"
    series_title: str = "Untitled Series"
    series_promise: str = ""
    endgame_direction: str = ""
    power_curve: str = "linear"
    series_mysteries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BookPlan:
    book: int
    role: str
    major_change: str
    power_ceiling: str
    chapter_count: int
    arc_style: str
    must_resolve: list[str] = field(default_factory=list)
    must_preserve: list[str] = field(default_factory=list)
    character_targets: dict[str, str] = field(default_factory=dict)
    faction_targets: list[str] = field(default_factory=list)
    floor_range: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChapterBeat:
    chapter: int
    phase: str
    tension: int
    creativity: int
    absurdity: int
    act: int
    directives: list[str] = field(default_factory=list)
    must_not_spend: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChapterOutlineEntry:
    chapter: int
    phase: str = ""
    title: str = ""
    premise: str = ""
    ends_on: str = ""
    character_focus: list[str] = field(default_factory=list)
    introduces: list[str] = field(default_factory=list)
    resolves: list[str] = field(default_factory=list)
    must_not_use: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ARC_GEOMETRIES: dict[str, list[dict[str, Any]]] = {
    "escalating_floor_survival": [
        {"phase": "The Drop", "weight": 0.10, "tension": 8, "creativity": 4, "absurdity": 7},
        {"phase": "The Bivouac", "weight": 0.10, "tension": 3, "creativity": 2, "absurdity": 4},
        {"phase": "Exploration", "weight": 0.22, "tension": 5, "creativity": 8, "absurdity": 6},
        {"phase": "Mid-Boss", "weight": 0.12, "tension": 8, "creativity": 3, "absurdity": 5},
        {"phase": "The Setback", "weight": 0.14, "tension": 4, "creativity": 5, "absurdity": 3},
        {"phase": "The Build", "weight": 0.18, "tension": 6, "creativity": 9, "absurdity": 8},
        {"phase": "The Apex", "weight": 0.11, "tension": 10, "creativity": 2, "absurdity": 9},
        {"phase": "The Loot", "weight": 0.03, "tension": 2, "creativity": 8, "absurdity": 5},
    ],
    "social_faction_expansion": [
        {"phase": "Public Pressure", "weight": 0.10, "tension": 6, "creativity": 4, "absurdity": 4},
        {"phase": "Alliance Bivouac", "weight": 0.12, "tension": 3, "creativity": 4, "absurdity": 3},
        {"phase": "Faction Contact", "weight": 0.18, "tension": 5, "creativity": 7, "absurdity": 5},
        {"phase": "Social Trap", "weight": 0.14, "tension": 8, "creativity": 3, "absurdity": 4},
        {"phase": "Reputation Setback", "weight": 0.14, "tension": 4, "creativity": 5, "absurdity": 2},
        {"phase": "Alliance Build", "weight": 0.20, "tension": 5, "creativity": 8, "absurdity": 5},
        {"phase": "Public Apex", "weight": 0.09, "tension": 9, "creativity": 3, "absurdity": 6},
        {"phase": "New Terms", "weight": 0.03, "tension": 2, "creativity": 7, "absurdity": 4},
    ],
    "deep_dungeon_descent": [
        {"phase": "Threshold", "weight": 0.08, "tension": 7, "creativity": 5, "absurdity": 5},
        {"phase": "Survey", "weight": 0.12, "tension": 3, "creativity": 5, "absurdity": 3},
        {"phase": "Mystery Spiral", "weight": 0.24, "tension": 5, "creativity": 8, "absurdity": 4},
        {"phase": "Subsurface Threat", "weight": 0.12, "tension": 8, "creativity": 4, "absurdity": 4},
        {"phase": "Lost Bearing", "weight": 0.16, "tension": 4, "creativity": 6, "absurdity": 2},
        {"phase": "Pattern Build", "weight": 0.16, "tension": 6, "creativity": 8, "absurdity": 5},
        {"phase": "Depth Apex", "weight": 0.09, "tension": 10, "creativity": 3, "absurdity": 6},
        {"phase": "Unearthed", "weight": 0.03, "tension": 2, "creativity": 7, "absurdity": 3},
    ],
}


def series_dir(storage_dir: str | Path, series_id: str) -> Path:
    return Path(storage_dir) / "series" / str(series_id)


def book_dir(storage_dir: str | Path, series_id: str, book_number: int) -> Path:
    return series_dir(storage_dir, series_id) / f"book_{book_number}"


def save_series_shape(storage_dir: str | Path, series_id: str, shape: SeriesShape | Mapping[str, Any]) -> None:
    _write_json(series_dir(storage_dir, series_id) / SERIES_PLAN_FILENAME, series_shape_from_mapping(shape).to_dict())


def load_series_shape(storage_dir: str | Path, series_id: str) -> SeriesShape:
    path = series_dir(storage_dir, series_id) / SERIES_PLAN_FILENAME
    return series_shape_from_mapping(_read_json(path))


def series_shape_from_mapping(value: SeriesShape | Mapping[str, Any]) -> SeriesShape:
    if isinstance(value, SeriesShape):
        return value
    data = dict(value)
    return SeriesShape(
        target_books=max(1, int(data.get("target_books") or 1)),
        book_length_mode=str(data.get("book_length_mode") or "standard"),
        chapters_per_book=max(1, int(data.get("chapters_per_book") or 60)),
        arc_style=str(data.get("arc_style") or "escalating_floor_survival"),
        series_title=str(data.get("series_title") or "Untitled Series"),
        series_promise=str(data.get("series_promise") or ""),
        endgame_direction=str(data.get("endgame_direction") or ""),
        power_curve=str(data.get("power_curve") or "linear"),
        series_mysteries=_string_list(data.get("series_mysteries")),
    )


def book_plan_from_mapping(value: BookPlan | Mapping[str, Any], *, shape: SeriesShape | None = None) -> BookPlan:
    if isinstance(value, BookPlan):
        return value
    data = dict(value)
    return BookPlan(
        book=max(1, int(data.get("book") or 1)),
        role=str(data.get("role") or ""),
        major_change=str(data.get("major_change") or ""),
        power_ceiling=str(data.get("power_ceiling") or ""),
        chapter_count=max(1, int(data.get("chapter_count") or (shape.chapters_per_book if shape else 60))),
        arc_style=str(data.get("arc_style") or (shape.arc_style if shape else "escalating_floor_survival")),
        must_resolve=_string_list(data.get("must_resolve")),
        must_preserve=_string_list(data.get("must_preserve")),
        character_targets={str(k): str(v) for k, v in dict(data.get("character_targets") or {}).items()},
        faction_targets=_string_list(data.get("faction_targets")),
        floor_range=[int(item) for item in _string_list(data.get("floor_range")) if str(item).lstrip("-").isdigit()],
    )


def save_series_arc(storage_dir: str | Path, series_id: str, arc: Sequence[BookPlan | Mapping[str, Any]]) -> None:
    shape = load_series_shape(storage_dir, series_id)
    plans = [book_plan_from_mapping(item, shape=shape).to_dict() for item in arc]
    _write_json(series_dir(storage_dir, series_id) / SERIES_ARC_FILENAME, plans)


def load_series_arc(storage_dir: str | Path, series_id: str) -> list[BookPlan]:
    shape = load_series_shape(storage_dir, series_id)
    raw = _read_json(series_dir(storage_dir, series_id) / SERIES_ARC_FILENAME)
    if not isinstance(raw, list):
        raise ValueError("series_arc.json must contain a JSON list")
    return [book_plan_from_mapping(item, shape=shape) for item in raw if isinstance(item, Mapping)]


def save_book_plan(storage_dir: str | Path, series_id: str, plan: BookPlan | Mapping[str, Any]) -> None:
    shape = load_series_shape(storage_dir, series_id)
    book_plan = book_plan_from_mapping(plan, shape=shape)
    _write_json(book_dir(storage_dir, series_id, book_plan.book) / BOOK_PLAN_FILENAME, book_plan.to_dict())


def load_book_plan(storage_dir: str | Path, series_id: str, book_number: int) -> BookPlan:
    path = book_dir(storage_dir, series_id, book_number) / BOOK_PLAN_FILENAME
    if path.exists():
        return book_plan_from_mapping(_read_json(path), shape=load_series_shape(storage_dir, series_id))
    for plan in load_series_arc(storage_dir, series_id):
        if plan.book == book_number:
            return plan
    raise FileNotFoundError(f"No book plan found for book {book_number}")


def length_mode_for_chapters(chapter_count: int) -> str:
    if chapter_count <= 34:
        return "tight"
    if chapter_count >= 66:
        return "epic"
    return "standard"


def generate_tempo_map(book_plan: BookPlan | Mapping[str, Any]) -> list[ChapterBeat]:
    plan = book_plan_from_mapping(book_plan)
    phases = _adjusted_geometry(plan.arc_style, length_mode_for_chapters(plan.chapter_count))
    counts = _phase_counts(plan.chapter_count, [float(phase["weight"]) for phase in phases])
    beats: list[ChapterBeat] = []
    chapter = 1
    for act, (phase, count) in enumerate(zip(phases, counts), 1):
        for index in range(count):
            beat = _phase_beat(phase, index=index, count=count)
            beats.append(
                ChapterBeat(
                    chapter=chapter,
                    phase=str(phase["phase"]),
                    tension=beat["tension"],
                    creativity=beat["creativity"],
                    absurdity=beat["absurdity"],
                    act=act,
                    directives=_directives(beat["tension"], beat["creativity"], beat["absurdity"], plan.must_preserve),
                    must_not_spend=list(plan.must_preserve),
                )
            )
            chapter += 1
    return beats


def save_tempo_map(storage_dir: str | Path, series_id: str, book_number: int, tempo: Sequence[ChapterBeat | Mapping[str, Any]]) -> None:
    items = [beat.to_dict() if isinstance(beat, ChapterBeat) else dict(beat) for beat in tempo]
    _write_json(book_dir(storage_dir, series_id, book_number) / TEMPO_MAP_FILENAME, items)


def load_tempo_map(storage_dir: str | Path, series_id: str, book_number: int) -> list[ChapterBeat]:
    path = book_dir(storage_dir, series_id, book_number) / TEMPO_MAP_FILENAME
    if not path.exists():
        plan = load_book_plan(storage_dir, series_id, book_number)
        tempo = generate_tempo_map(plan)
        save_tempo_map(storage_dir, series_id, book_number, tempo)
        return tempo
    raw = _read_json(path)
    if not isinstance(raw, list):
        raise ValueError("tempo_map.json must contain a JSON list")
    return [_chapter_beat_from_mapping(item) for item in raw if isinstance(item, Mapping)]


def save_chapter_outline(storage_dir: str | Path, series_id: str, book_number: int, outline: Sequence[ChapterOutlineEntry | Mapping[str, Any]]) -> None:
    items = [
        entry.to_dict() if isinstance(entry, ChapterOutlineEntry) else chapter_outline_from_mapping(entry).to_dict()
        for entry in outline
    ]
    _write_json(book_dir(storage_dir, series_id, book_number) / CHAPTER_OUTLINE_FILENAME, items)


def load_chapter_outline(storage_dir: str | Path, series_id: str, book_number: int) -> list[ChapterOutlineEntry]:
    path = book_dir(storage_dir, series_id, book_number) / CHAPTER_OUTLINE_FILENAME
    if not path.exists():
        return []
    raw = _read_json(path)
    if not isinstance(raw, list):
        raise ValueError("chapter_outline.json must contain a JSON list")
    return [chapter_outline_from_mapping(item) for item in raw if isinstance(item, Mapping)]


def chapter_outline_from_mapping(value: ChapterOutlineEntry | Mapping[str, Any]) -> ChapterOutlineEntry:
    if isinstance(value, ChapterOutlineEntry):
        return value
    data = dict(value)
    return ChapterOutlineEntry(
        chapter=max(1, int(data.get("chapter") or 1)),
        phase=str(data.get("phase") or ""),
        title=str(data.get("title") or ""),
        premise=str(data.get("premise") or ""),
        ends_on=str(data.get("ends_on") or ""),
        character_focus=_string_list(data.get("character_focus")),
        introduces=_string_list(data.get("introduces")),
        resolves=_string_list(data.get("resolves")),
        must_not_use=_string_list(data.get("must_not_use")),
    )


class SeriesArchitect:
    """Read top-down series plans and return per-chapter generation contracts."""

    def __init__(self, storage_dir: str | Path, series_id: str) -> None:
        self.storage_dir = Path(storage_dir)
        self.series_id = str(series_id)

    @property
    def root(self) -> Path:
        return series_dir(self.storage_dir, self.series_id)

    def available(self) -> bool:
        return (self.root / SERIES_PLAN_FILENAME).exists()

    def get_chapter_contract(self, *, book_number: int = 1, chapter_number: int = 1) -> dict[str, Any]:
        shape = load_series_shape(self.storage_dir, self.series_id)
        book_plan = load_book_plan(self.storage_dir, self.series_id, book_number)
        beat = _find_chapter_beat(load_tempo_map(self.storage_dir, self.series_id, book_number), chapter_number)
        outline = _find_outline_entry(load_chapter_outline(self.storage_dir, self.series_id, book_number), chapter_number)
        contract: dict[str, Any] = {
            "book": book_number,
            "chapter": chapter_number,
            "series_title": shape.series_title,
            "series_promise": shape.series_promise,
            "endgame_direction": shape.endgame_direction,
            "power_curve": shape.power_curve,
            "phase": beat.phase,
            "act": beat.act,
            "tension": beat.tension,
            "creativity": beat.creativity,
            "absurdity": beat.absurdity,
            "directives": list(beat.directives),
            "must_not_spend": list(beat.must_not_spend),
            "power_ceiling": book_plan.power_ceiling,
            "book_role": book_plan.role,
            "major_change": book_plan.major_change,
            "must_resolve": list(book_plan.must_resolve),
            "must_preserve": list(book_plan.must_preserve),
            "character_targets": dict(book_plan.character_targets),
            "faction_targets": list(book_plan.faction_targets),
            "floor_range": list(book_plan.floor_range),
            "chapter_count": book_plan.chapter_count,
            "arc_style": book_plan.arc_style,
        }
        if outline is not None:
            contract.update(
                {
                    "title": outline.title,
                    "premise": outline.premise,
                    "ends_on": outline.ends_on,
                    "character_focus": list(outline.character_focus),
                    "introduces": list(outline.introduces),
                    "resolves": list(outline.resolves),
                    "must_not_use": list(outline.must_not_use),
                }
            )
        return contract


def format_chapter_contract_context(contract: Mapping[str, Any]) -> str:
    lines = [
        "Chapter Contract:",
        f"- Series: {contract.get('series_title') or 'Untitled Series'}",
        f"- Book {contract.get('book')} / Chapter {contract.get('chapter')}: {contract.get('phase')}",
        (
            "- Targets: "
            f"tension {contract.get('tension')}, "
            f"creativity {contract.get('creativity')}, "
            f"absurdity {contract.get('absurdity')}"
        ),
        f"- Book role: {contract.get('book_role') or 'unspecified'}",
        f"- Power ceiling: {contract.get('power_ceiling') or 'unspecified'}",
    ]
    if contract.get("title"):
        lines.append(f"- Outline title: {contract['title']}")
    if contract.get("premise"):
        lines.append(f"- Outline premise: {contract['premise']}")
    if contract.get("ends_on"):
        lines.append(f"- Ends on: {contract['ends_on']}")
    for key, label in (
        ("directives", "Directives"),
        ("must_not_spend", "Do not spend"),
        ("must_resolve", "Must resolve this book"),
        ("must_preserve", "Must preserve this book"),
        ("must_not_use", "Do not use this chapter"),
        ("character_focus", "Character focus"),
        ("introduces", "Introduces"),
        ("resolves", "Resolves"),
    ):
        values = _string_list(contract.get(key))
        if values:
            lines.append(f"- {label}:")
            lines.extend(f"  - {value}" for value in values)
    return "\n".join(lines)


def bootstrap_series(
    *,
    storage_dir: str | Path,
    series_id: str,
    shape: SeriesShape | Mapping[str, Any],
    series_arc: Sequence[BookPlan | Mapping[str, Any]] | None = None,
) -> SeriesArchitect:
    shape_obj = series_shape_from_mapping(shape)
    save_series_shape(storage_dir, series_id, shape_obj)
    if series_arc is None:
        series_arc = _default_series_arc(shape_obj)
    save_series_arc(storage_dir, series_id, series_arc)
    for plan in load_series_arc(storage_dir, series_id):
        save_book_plan(storage_dir, series_id, plan)
        save_tempo_map(storage_dir, series_id, plan.book, generate_tempo_map(plan))
    return SeriesArchitect(storage_dir, series_id)


def build_series_arc_prompt(
    *,
    shape: SeriesShape | Mapping[str, Any],
    character_summary: str = "",
    series_mysteries: Sequence[str] | None = None,
) -> str:
    shape_obj = series_shape_from_mapping(shape)
    mysteries = list(series_mysteries or shape_obj.series_mysteries)
    return f"""Generate a multi-book story architecture contract.

Return only JSON: a list of {shape_obj.target_books} book objects.
Each object must include: book, role, major_change, power_ceiling, chapter_count, arc_style,
must_resolve, must_preserve, character_targets, faction_targets, floor_range.

Series shape:
{json.dumps(shape_obj.to_dict(), indent=2)}

Character summary:
{character_summary or "No character summary supplied."}

Series mysteries and reveals to preserve until assigned books:
{json.dumps(mysteries, indent=2)}

Rules:
- Do not resolve the endgame before the final book.
- Assign long-term mysteries to must_preserve until their reveal book.
- Keep power progression {shape_obj.power_curve}.
- Use arc_style {shape_obj.arc_style} unless a book has a strong reason to vary.
"""


def _default_series_arc(shape: SeriesShape) -> list[BookPlan]:
    plans = []
    for book in range(1, shape.target_books + 1):
        final_book = book == shape.target_books
        plans.append(
            BookPlan(
                book=book,
                role="Final confrontation and revelation" if final_book else f"Book {book} escalation",
                major_change=shape.endgame_direction if final_book else f"The series promise complicates in book {book}.",
                power_ceiling=_power_ceiling(book, shape),
                chapter_count=shape.chapters_per_book,
                arc_style=shape.arc_style,
                must_resolve=[shape.endgame_direction] if final_book and shape.endgame_direction else [],
                must_preserve=[] if final_book else list(shape.series_mysteries),
                floor_range=[book, book + 2],
            )
        )
    return plans


def _power_ceiling(book: int, shape: SeriesShape) -> str:
    if shape.power_curve == "logarithmic":
        return f"level {max(5, int(10 * (book ** 0.75)))}"
    return f"level {book * 10}"


def _adjusted_geometry(arc_style: str, length_mode: str) -> list[dict[str, Any]]:
    phases = [dict(item) for item in ARC_GEOMETRIES.get(arc_style, ARC_GEOMETRIES["escalating_floor_survival"])]
    if length_mode == "tight":
        for phase in phases:
            if phase["phase"] in {"The Bivouac", "The Loot", "Survey", "New Terms", "Alliance Bivouac"}:
                phase["weight"] *= 0.65
            if phase["phase"] in {"The Drop", "The Apex", "Mid-Boss", "Public Apex", "Depth Apex"}:
                phase["weight"] *= 1.15
    elif length_mode == "epic":
        for phase in phases:
            if phase["phase"] in {"Exploration", "The Build", "Mystery Spiral", "Alliance Build", "Faction Contact"}:
                phase["weight"] *= 1.25
            if phase["phase"] in {"The Setback", "Lost Bearing", "Reputation Setback"}:
                phase["weight"] *= 1.15
    total = sum(float(phase["weight"]) for phase in phases)
    for phase in phases:
        phase["weight"] = float(phase["weight"]) / total
    return phases


def _phase_counts(total_chapters: int, weights: Sequence[float]) -> list[int]:
    if total_chapters <= 0:
        return [0 for _ in weights]
    if total_chapters < len(weights):
        counts = [0 for _ in weights]
        if total_chapters == 1:
            counts[0] = 1
            return counts
        last_index = len(weights) - 1
        for chapter_index in range(total_chapters):
            phase_index = round(chapter_index * last_index / (total_chapters - 1))
            counts[phase_index] += 1
        return counts
    raw = [max(1, int(total_chapters * weight)) for weight in weights]
    while sum(raw) < total_chapters:
        index = max(range(len(raw)), key=lambda idx: (total_chapters * weights[idx]) - raw[idx])
        raw[index] += 1
    while sum(raw) > total_chapters:
        index = max((idx for idx, value in enumerate(raw) if value > 1), key=lambda idx: raw[idx])
        raw[index] -= 1
    return raw


def _phase_beat(phase: Mapping[str, Any], *, index: int, count: int) -> dict[str, int]:
    progress = index / max(1, count - 1)
    tension = int(phase["tension"])
    if progress > 0.66:
        tension = min(10, tension + 1)
    if progress < 0.20 and count > 2:
        tension = max(1, tension - 1)
    return {
        "tension": tension,
        "creativity": int(phase["creativity"]),
        "absurdity": int(phase["absurdity"]),
    }


def _directives(tension: int, creativity: int, absurdity: int, must_preserve: Sequence[str]) -> list[str]:
    directives = [
        TENSION_DIRECTIVES[_tension_key(tension)],
        CREATIVITY_DIRECTIVES[_creativity_key(creativity)],
        ABSURDITY_DIRECTIVES[_absurdity_key(absurdity)],
    ]
    if must_preserve:
        directives.append("SCARCITY: Do not reveal, resolve, explain, or spend preserved mysteries in this chapter.")
    return directives


def _chapter_beat_from_mapping(data: Mapping[str, Any]) -> ChapterBeat:
    return ChapterBeat(
        chapter=max(1, int(data.get("chapter") or 1)),
        phase=str(data.get("phase") or ""),
        tension=int(data.get("tension") or 5),
        creativity=int(data.get("creativity") or 5),
        absurdity=int(data.get("absurdity") or 5),
        act=int(data.get("act") or 1),
        directives=_string_list(data.get("directives")),
        must_not_spend=_string_list(data.get("must_not_spend")),
    )


def _find_chapter_beat(beats: Sequence[ChapterBeat], chapter_number: int) -> ChapterBeat:
    for beat in beats:
        if beat.chapter == chapter_number:
            return beat
    if not beats:
        raise ValueError("Tempo map is empty")
    return beats[-1]


def _find_outline_entry(outline: Sequence[ChapterOutlineEntry], chapter_number: int) -> ChapterOutlineEntry | None:
    for entry in outline:
        if entry.chapter == chapter_number:
            return entry
    return None


def _tension_key(value: int) -> str:
    if value >= 8:
        return "high"
    if value <= 4:
        return "low"
    return "mid"


def _creativity_key(value: int) -> str:
    if value <= 3:
        return "locked"
    if value >= 8:
        return "open"
    return "normal"


def _absurdity_key(value: int) -> str:
    if value >= 8:
        return "high"
    if value <= 4:
        return "low"
    return "mid"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(key) for key in value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
