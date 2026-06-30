"""Typed storage models for LitRPG series state and episode artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


class SchemaValidationError(ValueError):
    """Raised when persisted LitRPG JSON does not satisfy a shared contract."""


@dataclass(slots=True)
class CharacterState:
    name: str
    level: int
    character_class: str
    stats: dict[str, Any] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuestState:
    title: str
    status: str
    notes: str


@dataclass(slots=True)
class SeriesState:
    series_id: str
    title: str
    episode_number: int
    character: CharacterState
    schema_version: int = 1
    quests: list[QuestState] = field(default_factory=list)
    current_location: str = ""
    current_floor: int | None = None
    memory: list[str] = field(default_factory=list)
    mechanics: dict[str, Any] = field(default_factory=dict)
    announcer_notes_log: list[str] = field(default_factory=list)
    pedro_phrases: list[str] = field(default_factory=list)
    crowd_reactions: list[dict[str, Any]] = field(default_factory=list)
    sponsor_reactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChapterContract:
    book: int
    chapter: int
    phase: str
    tension: int
    creativity: int
    absurdity: int
    series_title: str = "Untitled Series"
    series_promise: str = ""
    endgame_direction: str = ""
    power_curve: str = ""
    act: int = 1
    directives: list[str] = field(default_factory=list)
    must_not_spend: list[str] = field(default_factory=list)
    power_ceiling: str = ""
    book_role: str = ""
    major_change: str = ""
    must_resolve: list[str] = field(default_factory=list)
    must_preserve: list[str] = field(default_factory=list)
    character_targets: dict[str, str] = field(default_factory=dict)
    faction_targets: list[str] = field(default_factory=list)
    floor_range: list[int] = field(default_factory=list)
    chapter_count: int = 1
    arc_style: str = ""
    title: str = ""
    premise: str = ""
    ends_on: str = ""
    character_focus: list[str] = field(default_factory=list)
    introduces: list[str] = field(default_factory=list)
    resolves: list[str] = field(default_factory=list)
    must_not_use: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SeriesArcBeat:
    chapter: int
    phase: str
    tension: int
    creativity: int
    absurdity: int
    act: int = 1
    directives: list[str] = field(default_factory=list)
    must_not_spend: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MysteryLock:
    mystery: str
    detail: str
    planted_chapter: int
    intended_payoff_start: int
    intended_payoff_end: int
    planted_book: int = 1
    payoff_book: int = 1
    status: str = "planted"
    paid_chapter: int | None = None
    forbidden_payoff: list[str] = field(default_factory=list)
    reveal_timing: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HookContract:
    category: str
    opening_obligation: str = ""
    ending_hook_type: str = ""
    last_image: str = ""
    open_question: str = ""
    implied_cost: str = ""
    next_chapter_obligation: str = ""
    reveal_timing: str = ""
    forbidden_payoff: list[str] = field(default_factory=list)
    mystery_lock: MysteryLock | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VoiceConstraint:
    role: str
    register: str = ""
    must_do: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    tts_constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorldRegisterEntry:
    kind: str
    name: str
    detail: str
    floor: int | None = None
    phase: str = ""
    location: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EpisodeConfig:
    prompt: str
    minutes: int
    tone: str
    cast: dict[str, Any] = field(default_factory=dict)
    tts_model: str | None = None
    model_version: str | None = None


@dataclass(slots=True)
class ScriptLine:
    role: str
    text: str
    style: str | None = None


@dataclass(slots=True)
class EpisodeBundle:
    series_id: str
    episode_id: str
    episode_number: int
    cache_key: str
    prompt: str
    config: EpisodeConfig
    paths: dict[str, str] = field(default_factory=dict)


def character_state_from_mapping(value: CharacterState | Mapping[str, Any]) -> CharacterState:
    if isinstance(value, CharacterState):
        return value
    data = _mapping(value, "character")
    return CharacterState(
        name=_required_str(data, "name", "character"),
        level=_required_int(data, "level", "character"),
        character_class=_required_str(data, "character_class", "character"),
        stats=_dict(data.get("stats"), "character.stats"),
        skills=_string_list(data.get("skills"), "character.skills"),
        inventory=_string_list(data.get("inventory"), "character.inventory"),
    )


def quest_state_from_mapping(value: QuestState | Mapping[str, Any]) -> QuestState:
    if isinstance(value, QuestState):
        return value
    data = _mapping(value, "quest")
    return QuestState(
        title=_optional_str(data.get("title")),
        status=_optional_str(data.get("status")),
        notes=_optional_str(data.get("notes")),
    )


def series_state_from_mapping(
    value: SeriesState | Mapping[str, Any], *, default_schema_version: int = 1
) -> SeriesState:
    if isinstance(value, SeriesState):
        return value
    data = _mapping(value, "series_state")
    return SeriesState(
        series_id=_required_str(data, "series_id", "series_state"),
        title=_required_str(data, "title", "series_state"),
        episode_number=_required_int(data, "episode_number", "series_state"),
        character=character_state_from_mapping(data.get("character")),
        schema_version=_int(data.get("schema_version", default_schema_version), "series_state.schema_version"),
        quests=[quest_state_from_mapping(item) for item in _mapping_list(data.get("quests"), "series_state.quests")],
        current_location=_optional_str(data.get("current_location")),
        current_floor=_optional_int(data.get("current_floor"), "series_state.current_floor"),
        memory=_string_list(data.get("memory"), "series_state.memory"),
        mechanics=_dict(data.get("mechanics"), "series_state.mechanics"),
        announcer_notes_log=_string_list(data.get("announcer_notes_log"), "series_state.announcer_notes_log"),
        pedro_phrases=_string_list(data.get("pedro_phrases"), "series_state.pedro_phrases"),
        crowd_reactions=_mapping_list(data.get("crowd_reactions"), "series_state.crowd_reactions"),
        sponsor_reactions=_mapping_list(data.get("sponsor_reactions"), "series_state.sponsor_reactions"),
    )


def series_arc_beat_from_mapping(value: SeriesArcBeat | Mapping[str, Any]) -> SeriesArcBeat:
    if isinstance(value, SeriesArcBeat):
        return value
    data = _mapping(value, "series_arc_beat")
    return SeriesArcBeat(
        chapter=max(1, _required_int(data, "chapter", "series_arc_beat")),
        phase=_required_str(data, "phase", "series_arc_beat"),
        tension=_bounded_int(data.get("tension", 5), "series_arc_beat.tension", minimum=1, maximum=10),
        creativity=_bounded_int(data.get("creativity", 5), "series_arc_beat.creativity", minimum=1, maximum=10),
        absurdity=_bounded_int(data.get("absurdity", 5), "series_arc_beat.absurdity", minimum=1, maximum=10),
        act=max(1, _int(data.get("act", 1), "series_arc_beat.act")),
        directives=_string_list(data.get("directives"), "series_arc_beat.directives"),
        must_not_spend=_string_list(data.get("must_not_spend"), "series_arc_beat.must_not_spend"),
    )


def chapter_contract_from_mapping(value: ChapterContract | Mapping[str, Any]) -> ChapterContract:
    if isinstance(value, ChapterContract):
        return value
    data = _mapping(value, "chapter_contract")
    beat = series_arc_beat_from_mapping(data)
    return ChapterContract(
        book=max(1, _required_int(data, "book", "chapter_contract")),
        chapter=beat.chapter,
        phase=beat.phase,
        tension=beat.tension,
        creativity=beat.creativity,
        absurdity=beat.absurdity,
        series_title=_optional_str(data.get("series_title")) or "Untitled Series",
        series_promise=_optional_str(data.get("series_promise")),
        endgame_direction=_optional_str(data.get("endgame_direction")),
        power_curve=_optional_str(data.get("power_curve")),
        act=beat.act,
        directives=beat.directives,
        must_not_spend=beat.must_not_spend,
        power_ceiling=_optional_str(data.get("power_ceiling")),
        book_role=_optional_str(data.get("book_role")),
        major_change=_optional_str(data.get("major_change")),
        must_resolve=_string_list(data.get("must_resolve"), "chapter_contract.must_resolve"),
        must_preserve=_string_list(data.get("must_preserve"), "chapter_contract.must_preserve"),
        character_targets=_str_dict(data.get("character_targets"), "chapter_contract.character_targets"),
        faction_targets=_string_list(data.get("faction_targets"), "chapter_contract.faction_targets"),
        floor_range=[_int(item, "chapter_contract.floor_range") for item in _list(data.get("floor_range"), "chapter_contract.floor_range")],
        chapter_count=max(1, _int(data.get("chapter_count", 1), "chapter_contract.chapter_count")),
        arc_style=_optional_str(data.get("arc_style")),
        title=_optional_str(data.get("title")),
        premise=_optional_str(data.get("premise")),
        ends_on=_optional_str(data.get("ends_on")),
        character_focus=_string_list(data.get("character_focus"), "chapter_contract.character_focus"),
        introduces=_string_list(data.get("introduces"), "chapter_contract.introduces"),
        resolves=_string_list(data.get("resolves"), "chapter_contract.resolves"),
        must_not_use=_string_list(data.get("must_not_use"), "chapter_contract.must_not_use"),
    )


def mystery_lock_from_mapping(value: MysteryLock | Mapping[str, Any]) -> MysteryLock:
    if isinstance(value, MysteryLock):
        return value
    data = _mapping(value, "mystery_lock")
    payoff_range = data.get("intended_payoff_range")
    if isinstance(payoff_range, Sequence) and not isinstance(payoff_range, (str, bytes)) and len(payoff_range) >= 2:
        start = _int(payoff_range[0], "mystery_lock.intended_payoff_range[0]")
        end = _int(payoff_range[1], "mystery_lock.intended_payoff_range[1]")
    else:
        start = _required_int(data, "intended_payoff_start", "mystery_lock")
        end = _required_int(data, "intended_payoff_end", "mystery_lock")
    if end < start:
        raise SchemaValidationError("mystery_lock.intended_payoff_end must be >= intended_payoff_start")
    return MysteryLock(
        mystery=_required_str(data, "mystery", "mystery_lock"),
        detail=_required_str(data, "detail", "mystery_lock"),
        planted_chapter=max(0, _required_int(data, "planted_chapter", "mystery_lock")),
        intended_payoff_start=max(0, start),
        intended_payoff_end=max(0, end),
        planted_book=max(1, _int(data.get("planted_book", 1), "mystery_lock.planted_book")),
        payoff_book=max(1, _int(data.get("payoff_book", data.get("book", 1)), "mystery_lock.payoff_book")),
        status=_optional_str(data.get("status")) or "planted",
        paid_chapter=_optional_int(data.get("paid_chapter"), "mystery_lock.paid_chapter"),
        forbidden_payoff=_string_list(data.get("forbidden_payoff"), "mystery_lock.forbidden_payoff"),
        reveal_timing=_optional_str(data.get("reveal_timing")),
    )


def hook_contract_from_mapping(value: HookContract | Mapping[str, Any]) -> HookContract:
    if isinstance(value, HookContract):
        return value
    data = _mapping(value, "hook_contract")
    raw_lock = data.get("mystery_lock")
    return HookContract(
        category=_required_str(data, "category", "hook_contract"),
        opening_obligation=_optional_str(data.get("opening_obligation")),
        ending_hook_type=_optional_str(data.get("ending_hook_type")),
        last_image=_optional_str(data.get("last_image")),
        open_question=_optional_str(data.get("open_question")),
        implied_cost=_optional_str(data.get("implied_cost")),
        next_chapter_obligation=_optional_str(data.get("next_chapter_obligation")),
        reveal_timing=_optional_str(data.get("reveal_timing")),
        forbidden_payoff=_string_list(data.get("forbidden_payoff"), "hook_contract.forbidden_payoff"),
        mystery_lock=mystery_lock_from_mapping(raw_lock) if raw_lock is not None else None,
    )


def voice_constraint_from_mapping(value: VoiceConstraint | Mapping[str, Any]) -> VoiceConstraint:
    if isinstance(value, VoiceConstraint):
        return value
    data = _mapping(value, "voice_constraint")
    return VoiceConstraint(
        role=_required_str(data, "role", "voice_constraint"),
        register=_optional_str(data.get("register")),
        must_do=_string_list(data.get("must_do"), "voice_constraint.must_do"),
        must_avoid=_string_list(data.get("must_avoid"), "voice_constraint.must_avoid"),
        tts_constraints=_string_list(data.get("tts_constraints"), "voice_constraint.tts_constraints"),
    )


def world_register_entry_from_mapping(value: WorldRegisterEntry | Mapping[str, Any]) -> WorldRegisterEntry:
    if isinstance(value, WorldRegisterEntry):
        return value
    data = _mapping(value, "world_register_entry")
    return WorldRegisterEntry(
        kind=_required_str(data, "kind", "world_register_entry"),
        name=_required_str(data, "name", "world_register_entry"),
        detail=_required_str(data, "detail", "world_register_entry"),
        floor=_optional_int(data.get("floor"), "world_register_entry.floor"),
        phase=_optional_str(data.get("phase")),
        location=_optional_str(data.get("location")),
        tags=_string_list(data.get("tags"), "world_register_entry.tags"),
    )


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{path} must be an object")
    return value


def _dict(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{path} must be an object")
    return dict(value)


def _str_dict(value: Any, path: str) -> dict[str, str]:
    data = _dict(value, path)
    return {str(key): str(item) for key, item in data.items()}


def _list(value: Any, path: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SchemaValidationError(f"{path} must be a list")
    return list(value)


def _mapping_list(value: Any, path: str) -> list[dict[str, Any]]:
    return [dict(_mapping(item, f"{path}[{index}]")) for index, item in enumerate(_list(value, path))]


def _string_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Mapping):
        raise SchemaValidationError(f"{path} must be a list of strings")
    if isinstance(value, Sequence):
        return [str(item).strip() for item in value if str(item).strip()]
    raise SchemaValidationError(f"{path} must be a list of strings")


def _required_str(data: Mapping[str, Any], key: str, path: str) -> str:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    text = _optional_str(data.get(key))
    if not text:
        raise SchemaValidationError(f"{path}.{key} must be a non-empty string")
    return text


def _optional_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _required_int(data: Mapping[str, Any], key: str, path: str) -> int:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    return _int(data.get(key), f"{path}.{key}")


def _int(value: Any, path: str) -> int:
    if isinstance(value, bool):
        raise SchemaValidationError(f"{path} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SchemaValidationError(f"{path} must be an integer") from exc


def _optional_int(value: Any, path: str) -> int | None:
    if value is None or value == "":
        return None
    return _int(value, path)


def _bounded_int(value: Any, path: str, *, minimum: int, maximum: int) -> int:
    number = _int(value, path)
    if not minimum <= number <= maximum:
        raise SchemaValidationError(f"{path} must be between {minimum} and {maximum}")
    return number
