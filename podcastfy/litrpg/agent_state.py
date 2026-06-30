"""Durable agent queue state for LitRPG series operations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


AGENT_STATE_FILENAME = "agent_state.json"
AGENT_STATE_SCHEMA_VERSION = 1
QUEUE_NAMES = ("now", "next", "blocked", "improve", "recurring")


@dataclass(frozen=True, slots=True)
class QueueItem:
    id: str
    kind: str
    summary: str
    source: str
    priority: int = 2
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def agent_state_path(storage_dir: str | Path, series_id: str) -> Path:
    return Path(storage_dir) / "series" / str(series_id) / AGENT_STATE_FILENAME


def default_agent_state(series_id: str) -> dict[str, Any]:
    return {
        "schema_version": AGENT_STATE_SCHEMA_VERSION,
        "series_id": str(series_id),
        "now": [],
        "next": [],
        "blocked": [],
        "improve": [],
        "recurring": [],
        "updated_at": _utc_now(),
    }


def load_agent_state(storage_dir: str | Path, series_id: str) -> dict[str, Any]:
    path = agent_state_path(storage_dir, series_id)
    if not path.exists():
        return default_agent_state(series_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        return default_agent_state(series_id)
    state = default_agent_state(str(payload.get("series_id") or series_id))
    state.update(dict(payload))
    for queue in QUEUE_NAMES:
        state[queue] = dedupe_queue(state.get(queue) or [])
    return state


def save_agent_state(storage_dir: str | Path, state: Mapping[str, Any]) -> Path:
    series_id = str(state.get("series_id") or "default-series")
    path = agent_state_path(storage_dir, series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["updated_at"] = _utc_now()
    with path.open("w", encoding="utf-8") as state_file:
        json.dump(payload, state_file, ensure_ascii=True, indent=2, sort_keys=True)
        state_file.write("\n")
    return path


def add_queue_item(
    state: Mapping[str, Any],
    queue: str,
    item: QueueItem | Mapping[str, Any],
) -> dict[str, Any]:
    if queue not in QUEUE_NAMES:
        raise ValueError(f"Unsupported queue: {queue}")
    updated = _copy_state(state)
    items = list(updated.get(queue) or [])
    items.append(_coerce_item(item).to_dict())
    updated[queue] = dedupe_queue(items)
    updated["updated_at"] = _utc_now()
    return updated


def complete_queue_item(state: Mapping[str, Any], item_id: str) -> dict[str, Any]:
    updated = _copy_state(state)
    wanted = str(item_id)
    for queue in QUEUE_NAMES:
        updated[queue] = [
            item for item in updated.get(queue, []) if str(item.get("id") or "") != wanted
        ]
    updated["updated_at"] = _utc_now()
    return updated


def dedupe_queue(items: list[Any]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        coerced = _coerce_item(item).to_dict()
        existing = by_id.get(coerced["id"])
        if existing is None or coerced["priority"] < existing.get("priority", 2):
            by_id[coerced["id"]] = coerced
    return [by_id[key] for key in sorted(by_id)]


def record_quarantine_blocker(
    state: Mapping[str, Any],
    *,
    series_id: str,
    chapter_number: int,
    quarantine_path: str = "",
    reason: str = "",
) -> dict[str, Any]:
    return add_queue_item(
        state,
        "blocked",
        QueueItem(
            id=f"blocked:chapter:{int(chapter_number)}",
            kind="quarantine_blocker",
            summary=f"Chapter {int(chapter_number)} is blocked by quarantine.",
            source="quarantine",
            priority=1,
            metadata={
                "series_id": series_id,
                "chapter_number": int(chapter_number),
                "quarantine_path": quarantine_path,
                "reason": reason,
            },
        ),
    )


def record_next_chapter_action(
    state: Mapping[str, Any],
    *,
    series_id: str,
    book_number: int,
    chapter_number: int,
    opener: str = "",
) -> dict[str, Any]:
    next_chapter = int(chapter_number) + 1
    return add_queue_item(
        state,
        "next",
        QueueItem(
            id=f"next:chapter:{next_chapter}",
            kind="next_chapter",
            summary=f"Prepare Chapter {next_chapter}.",
            source="chapter_result",
            priority=2,
            metadata={
                "series_id": series_id,
                "book_number": int(book_number),
                "chapter_number": next_chapter,
                "opener": opener,
            },
        ),
    )


def _copy_state(state: Mapping[str, Any]) -> dict[str, Any]:
    copied = default_agent_state(str(state.get("series_id") or "default-series"))
    copied.update(dict(state))
    for queue in QUEUE_NAMES:
        copied[queue] = [dict(item) for item in copied.get(queue, []) if isinstance(item, Mapping)]
    return copied


def _coerce_item(item: QueueItem | Mapping[str, Any]) -> QueueItem:
    if isinstance(item, QueueItem):
        return item
    data = dict(item)
    return QueueItem(
        id=str(data.get("id") or ""),
        kind=str(data.get("kind") or ""),
        summary=str(data.get("summary") or ""),
        source=str(data.get("source") or ""),
        priority=int(data.get("priority") or 2),
        metadata=dict(data.get("metadata") or {}),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
