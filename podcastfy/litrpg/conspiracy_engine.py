"""Standalone conspiracy-layer controls for long-form LitRPG planning."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

CONSPIRACY_ENGINE_FILENAME = "conspiracy_engine.json"
CONSPIRACY_ENGINE_SCHEMA_VERSION = 1


class ConspiracyEngine:
    """Expose only chapter-safe conspiracy context to downstream generators."""

    def __init__(self, storage_dir: str | Path, series_id: str) -> None:
        self.storage_dir = Path(storage_dir)
        self.series_id = str(series_id or "default-series")

    @property
    def root(self) -> Path:
        return conspiracy_dir(self.storage_dir, self.series_id)

    def available(self) -> bool:
        return conspiracy_engine_path(self.storage_dir, self.series_id).exists()

    def read(self) -> dict[str, Any]:
        return load_conspiracy_engine(self.storage_dir, self.series_id)

    def write(self, state: Mapping[str, Any]) -> Path:
        return save_conspiracy_engine(self.storage_dir, self.series_id, state)

    def get_chapter_context(
        self,
        *,
        book_number: int = 1,
        chapter_number: int = 1,
        pov_character: str = "",
    ) -> dict[str, Any]:
        """Return the safe subset that may be merged into chapter contracts."""

        state = self.read()
        return build_conspiracy_chapter_context(
            state,
            book_number=book_number,
            chapter_number=chapter_number,
            pov_character=pov_character,
        )

    def build_prose_context(
        self,
        *,
        pov_character: str,
        chapter_contract: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the prose-facing conspiracy view without exposing truth_document."""

        contract = dict(chapter_contract or {})
        book_number = int(contract.get("book") or 1)
        chapter_number = int(contract.get("chapter") or 1)
        chapter_context = self.get_chapter_context(
            book_number=book_number,
            chapter_number=chapter_number,
            pov_character=pov_character,
        )
        return {
            "character_knowledge": chapter_context.get("character_knowledge", {}),
            "reader_position": chapter_context.get("reader_position", {}),
            "allowed_conspiracy_hints": chapter_context.get("allowed_conspiracy_hints", []),
            "forbidden_revelations": chapter_context.get("forbidden_revelations", []),
            "faction_constraints": chapter_context.get("faction_constraints", {}),
        }


def conspiracy_dir(storage_dir: str | Path, series_id: str) -> Path:
    return Path(storage_dir) / "series" / str(series_id)


def conspiracy_engine_path(storage_dir: str | Path, series_id: str) -> Path:
    return conspiracy_dir(storage_dir, series_id) / CONSPIRACY_ENGINE_FILENAME


def load_conspiracy_engine(storage_dir: str | Path, series_id: str) -> dict[str, Any]:
    path = conspiracy_engine_path(storage_dir, series_id)
    if not path.exists():
        return normalize_conspiracy_engine({"series_id": series_id})
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return normalize_conspiracy_engine({"series_id": series_id})
    return normalize_conspiracy_engine({**payload, "series_id": series_id})


def save_conspiracy_engine(storage_dir: str | Path, series_id: str, state: Mapping[str, Any]) -> Path:
    path = conspiracy_engine_path(storage_dir, series_id)
    payload = normalize_conspiracy_engine({**dict(state), "series_id": series_id})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def normalize_conspiracy_engine(data: Mapping[str, Any] | None) -> dict[str, Any]:
    source = copy.deepcopy(dict(data or {}))
    return {
        "schema_version": int(source.get("schema_version") or CONSPIRACY_ENGINE_SCHEMA_VERSION),
        "series_id": str(source.get("series_id") or "default-series"),
        "truth_document": _mapping(source.get("truth_document")),
        "revelation_ladder": _mapping(source.get("revelation_ladder")),
        "reader_position": _normalize_reader_position(source.get("reader_position")),
        "factions": _mapping(source.get("factions")),
        "metadata": _mapping(source.get("metadata")),
    }


def build_conspiracy_chapter_context(
    state: Mapping[str, Any] | None,
    *,
    book_number: int = 1,
    chapter_number: int = 1,
    pov_character: str = "",
) -> dict[str, Any]:
    normalized = normalize_conspiracy_engine(state or {})
    reader_position = _normalize_reader_position(normalized.get("reader_position"))
    allowed_hints = _allowed_hints(
        normalized.get("revelation_ladder"),
        book_number=book_number,
        chapter_number=chapter_number,
    )
    forbidden = _forbidden_revelations(
        normalized,
        book_number=book_number,
        chapter_number=chapter_number,
    )
    return {
        "reader_position": reader_position,
        "character_knowledge": _pov_knowledge(normalized.get("truth_document"), pov_character),
        "allowed_conspiracy_hints": allowed_hints,
        "forbidden_revelations": forbidden,
        "faction_constraints": _safe_faction_constraints(normalized.get("factions")),
    }


def _normalize_reader_position(value: Any) -> dict[str, list[str]]:
    data = _mapping(value)
    return {
        "confirmed_knows": _string_list(data.get("confirmed_knows")),
        "strongly_suspects": _string_list(data.get("strongly_suspects")),
        "correctly_suspects_but_has_wrong_reason": _string_list(
            data.get("correctly_suspects_but_has_wrong_reason")
        ),
        "must_not_know_yet": _string_list(data.get("must_not_know_yet")),
    }


def _allowed_hints(
    ladder: Any,
    *,
    book_number: int,
    chapter_number: int,
) -> list[dict[str, Any]]:
    hints = []
    for mystery_id, payload in _mapping(ladder).items():
        item = _mapping(payload)
        if not item:
            continue
        if not _chapter_in_window(chapter_number, item.get("next_hint_window")):
            continue
        hint = {
            "mystery_id": str(mystery_id),
            "hint_type": str(item.get("hint_type_next") or "subtle anomaly"),
            "current_reader_knowledge": str(item.get("current_reader_knowledge") or ""),
        }
        if item.get("DO_NOT_ACCELERATE") is True:
            hint["do_not_accelerate"] = True
        hints.append(hint)
    return hints


def _forbidden_revelations(
    state: Mapping[str, Any],
    *,
    book_number: int,
    chapter_number: int,
) -> list[str]:
    forbidden = []
    reader = _normalize_reader_position(state.get("reader_position"))
    forbidden.extend(f"reader must not confirm: {item}" for item in reader["must_not_know_yet"])
    for mystery_id, payload in _mapping(state.get("revelation_ladder")).items():
        item = _mapping(payload)
        if item.get("DO_NOT_ACCELERATE") is True:
            reveal = str(item.get("full_reveal") or item.get("earliest_partial_reveal") or "").strip()
            if reveal and _book_before(book_number, reveal):
                forbidden.append(f"{mystery_id}: do not reveal before {reveal}")
            truth = str(item.get("truth") or "").strip()
            if truth and not _book_at_or_after(book_number, item.get("full_reveal")):
                forbidden.append(f"{mystery_id}: do not state the ladder truth")
        if not _chapter_in_window(chapter_number, item.get("next_hint_window")):
            hint_type = str(item.get("hint_type_next") or "").strip()
            if hint_type:
                forbidden.append(f"{mystery_id}: no unscheduled {hint_type} hint")
    return _dedupe(forbidden)


def _pov_knowledge(truth_document: Any, pov_character: str) -> dict[str, list[str]]:
    truth = _mapping(truth_document)
    who_knows = _mapping(_mapping(truth.get("actual_reality")).get("who_knows_what"))
    candidates = [pov_character, str(pov_character).lower(), str(pov_character).strip().replace(" ", "_").lower()]
    for key in candidates:
        if key and key in who_knows:
            return {"pov": str(pov_character), "knowledge": _string_list(who_knows[key])}
    return {"pov": str(pov_character), "knowledge": []}


def _safe_faction_constraints(factions: Any) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for faction_id, payload in _mapping(factions).items():
        faction = _mapping(payload)
        if not faction:
            continue
        safe[str(faction_id)] = {
            "name": str(faction.get("name") or faction_id),
            "apparent_goal": str(faction.get("apparent_goal") or ""),
            "operational_rules": _string_list(faction.get("operational_rules")),
            "vulnerabilities": _string_list(faction.get("vulnerabilities")),
            "current_moves": _safe_current_moves(faction.get("current_moves")),
        }
    return safe


def _safe_current_moves(value: Any) -> list[dict[str, Any]]:
    moves = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return moves
    for item in value:
        move = _mapping(item)
        if move:
            moves.append(
                {
                    "book": move.get("book"),
                    "action": str(move.get("action") or ""),
                    "carl_awareness": str(move.get("carl_awareness") or move.get("pov_awareness") or ""),
                }
            )
    return moves


def _chapter_in_window(chapter_number: int, window: Any) -> bool:
    if window in (None, ""):
        return True
    text = str(window).strip().lower()
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if not numbers:
        return False
    if len(numbers) == 1:
        return chapter_number == numbers[0]
    return min(numbers[0], numbers[1]) <= chapter_number <= max(numbers[0], numbers[1])


def _book_before(book_number: int, marker: Any) -> bool:
    target = _book_marker(marker)
    return target is not None and book_number < target


def _book_at_or_after(book_number: int, marker: Any) -> bool:
    target = _book_marker(marker)
    return target is not None and book_number >= target


def _book_marker(marker: Any) -> int | None:
    if marker in (None, ""):
        return None
    text = str(marker).strip().lower()
    if text.startswith("book_") or text.startswith("book "):
        match = re.search(r"\d+", text)
        return int(match.group(0)) if match else None
    if text.isdigit():
        return int(text)
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(item) for item in value.values() if str(item or "").strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _dedupe(values: Sequence[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result
