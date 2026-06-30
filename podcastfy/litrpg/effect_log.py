"""Append-only effect log helpers for expensive LitRPG operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from dataclasses import field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


EFFECT_LOG_FILENAME = "effect_log.jsonl"
EFFECT_STATUSES = {"planned", "running", "committed", "failed", "skipped"}


@dataclass(frozen=True, slots=True)
class EffectLogEntry:
    effect_id: str
    idempotency_key: str
    series_id: str
    book_number: int
    chapter_number: int
    stage: str
    provider: str = ""
    model: str = ""
    input_hash: str = ""
    output_hash: str = ""
    estimated_cost_usd: float = 0.0
    status: str = "committed"
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def effect_log_path(storage_dir: str | Path, series_id: str) -> Path:
    """Return the per-series effect log path."""

    return Path(storage_dir) / "series" / str(series_id) / EFFECT_LOG_FILENAME


def stable_hash(value: Any) -> str:
    """Return a stable sha256 hash for JSON-like values or strings."""

    if isinstance(value, str):
        data = value
    else:
        data = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def make_idempotency_key(
    *,
    series_id: str,
    book_number: int,
    chapter_number: int,
    stage: str,
    input_hash: str,
    provider: str = "",
    model: str = "",
) -> str:
    """Build a deterministic idempotency key."""

    payload = {
        "series_id": str(series_id),
        "book_number": int(book_number),
        "chapter_number": int(chapter_number),
        "stage": str(stage),
        "input_hash": str(input_hash),
        "provider": str(provider),
        "model": str(model),
    }
    return stable_hash(payload)


def append_effect_log_entry(path: str | Path, entry: EffectLogEntry | Mapping[str, Any]) -> EffectLogEntry:
    """Append one effect log entry to JSONL and return the normalized entry."""

    normalized = _coerce_entry(entry)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as log_file:
        json.dump(normalized.to_dict(), log_file, ensure_ascii=True, sort_keys=True)
        log_file.write("\n")
    return normalized


def read_effect_log(path: str | Path) -> list[EffectLogEntry]:
    """Read effect log entries, ignoring blank lines."""

    log_path = Path(path)
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, Mapping):
            entries.append(_coerce_entry(payload))
    return entries


def find_committed_effect(path: str | Path, idempotency_key: str) -> EffectLogEntry | None:
    """Return the latest committed effect with a matching idempotency key."""

    for entry in reversed(read_effect_log(path)):
        if entry.idempotency_key == idempotency_key and entry.status == "committed":
            return entry
    return None


def should_skip_effect(
    path: str | Path,
    *,
    idempotency_key: str,
    policy: str = "",
) -> bool:
    """Return true only when skip_committed policy finds a committed effect."""

    return policy == "skip_committed" and find_committed_effect(path, idempotency_key) is not None


def build_effect_log_entry(
    *,
    series_id: str,
    book_number: int,
    chapter_number: int,
    stage: str,
    input_payload: Any,
    output_payload: Any,
    provider: str = "",
    model: str = "",
    estimated_cost_usd: float = 0.0,
    status: str = "committed",
    metadata: Mapping[str, Any] | None = None,
) -> EffectLogEntry:
    """Build a normalized effect log entry from input/output payloads."""

    input_hash = stable_hash(input_payload)
    output_hash = stable_hash(output_payload)
    idempotency_key = make_idempotency_key(
        series_id=series_id,
        book_number=book_number,
        chapter_number=chapter_number,
        stage=stage,
        input_hash=input_hash,
        provider=provider,
        model=model,
    )
    return EffectLogEntry(
        effect_id=stable_hash(
            {
                "idempotency_key": idempotency_key,
                "output_hash": output_hash,
                "status": status,
            }
        ),
        idempotency_key=idempotency_key,
        series_id=str(series_id),
        book_number=int(book_number),
        chapter_number=int(chapter_number),
        stage=str(stage),
        provider=str(provider),
        model=str(model),
        input_hash=input_hash,
        output_hash=output_hash,
        estimated_cost_usd=float(estimated_cost_usd),
        status=status,
        created_at=_utc_now(),
        metadata=dict(metadata or {}),
    )


def _coerce_entry(value: EffectLogEntry | Mapping[str, Any]) -> EffectLogEntry:
    if isinstance(value, EffectLogEntry):
        return value
    data = dict(value)
    status = str(data.get("status") or "committed")
    if status not in EFFECT_STATUSES:
        raise ValueError(f"Unsupported effect status: {status}")
    return EffectLogEntry(
        effect_id=str(data.get("effect_id") or stable_hash(data)),
        idempotency_key=str(data.get("idempotency_key") or ""),
        series_id=str(data.get("series_id") or ""),
        book_number=int(data.get("book_number") or 1),
        chapter_number=int(data.get("chapter_number") or 1),
        stage=str(data.get("stage") or ""),
        provider=str(data.get("provider") or ""),
        model=str(data.get("model") or ""),
        input_hash=str(data.get("input_hash") or ""),
        output_hash=str(data.get("output_hash") or ""),
        estimated_cost_usd=float(data.get("estimated_cost_usd") or 0.0),
        status=status,
        created_at=str(data.get("created_at") or _utc_now()),
        metadata=dict(data.get("metadata") or {}),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
