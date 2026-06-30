"""Quarantine records for failed chapter attempts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class QuarantineRecord:
    status: str
    series_id: str
    book_number: int
    chapter_number: int
    attempt: int
    reason: str
    violation_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rewrite_instruction: str = ""
    rewrite_attempts: int = 0
    max_rewrite_attempts: int = 3
    scarcity_audit: dict[str, Any] = field(default_factory=dict)
    chapter: dict[str, Any] = field(default_factory=dict)
    parts: list[dict[str, Any]] = field(default_factory=list)
    combined_script: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chapter_quarantine_dir(
    storage_dir: str | Path,
    series_id: str,
    book_number: int,
) -> Path:
    """Return the chapter quarantine directory for a series book."""

    return (
        Path(storage_dir)
        / "series"
        / str(series_id)
        / f"book_{int(book_number):d}"
        / "quarantine"
    )


def next_quarantine_attempt_path(
    storage_dir: str | Path,
    series_id: str,
    book_number: int,
    chapter_number: int,
) -> Path:
    """Return the next deterministic quarantine attempt path."""

    directory = chapter_quarantine_dir(storage_dir, series_id, book_number)
    pattern = f"chapter_{int(chapter_number):03d}_attempt_*.json"
    attempts = []
    for path in directory.glob(pattern):
        stem = path.stem.rsplit("_attempt_", 1)
        if len(stem) != 2:
            continue
        try:
            attempts.append(int(stem[1]))
        except ValueError:
            continue
    attempt = max(attempts, default=0) + 1
    return directory / f"chapter_{int(chapter_number):03d}_attempt_{attempt:03d}.json"


def write_quarantine_record(path: str | Path, record: QuarantineRecord | Mapping[str, Any]) -> Path:
    """Write a quarantine record as deterministic JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = quarantine_record_to_dict(record)
    with output_path.open("w", encoding="utf-8") as record_file:
        json.dump(payload, record_file, ensure_ascii=True, indent=2, sort_keys=True)
        record_file.write("\n")
    return output_path


def build_rewrite_instruction(
    scarcity_audit: Mapping[str, Any],
    chapter_contract: Mapping[str, Any] | None = None,
    scarcity_registry: Mapping[str, Any] | None = None,
) -> str:
    """Build deterministic rewrite instructions from scarcity failure data."""

    registry = dict(scarcity_registry or {})
    registry_items = registry.get("items") if isinstance(registry.get("items"), Sequence) else []
    forbidden_now = _registry_names_locked_for_payoff(registry_items)
    allowed_hints = _registry_names_allowed_for_hint(registry_items)
    lines = [
        "Rewrite required: scarcity audit failed.",
        "Preserve the chapter's usable continuity and character work, but remove or defer forbidden scarcity payoffs.",
    ]
    violations = _string_list(scarcity_audit.get("violations"))
    warnings = _string_list(scarcity_audit.get("warnings"))
    spent = _string_list(scarcity_audit.get("spent_mysteries"))
    if violations:
        lines.append("Violation notes:")
        lines.extend(f"- {item}" for item in violations)
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in warnings)
    if spent:
        lines.append("Spent mysteries to unspend:")
        lines.extend(f"- {item}" for item in spent)
    if forbidden_now:
        lines.append("Forbidden now:")
        lines.extend(f"- {item}" for item in forbidden_now)
    if allowed_hints:
        lines.append("Allowed hints:")
        lines.extend(f"- {item}" for item in allowed_hints)
    contract = dict(chapter_contract or {})
    if contract:
        lines.append(
            "Chapter timing: "
            f"book {contract.get('book') or 'unknown'}, "
            f"chapter {contract.get('chapter') or 'unknown'}, "
            f"phase {contract.get('phase') or 'unknown'}."
        )
    lines.append(
        "Do not reveal, explain, reward, upgrade, resolve, or name locked material; use only permitted hints and earned resources."
    )
    return "\n".join(lines)


def quarantine_record_to_dict(record: QuarantineRecord | Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized quarantine record dictionary."""

    if isinstance(record, QuarantineRecord):
        payload = record.to_dict()
    else:
        payload = dict(record)
    payload.setdefault("status", "quarantined")
    payload.setdefault("series_id", "")
    payload["book_number"] = int(payload.get("book_number") or 1)
    payload["chapter_number"] = int(payload.get("chapter_number") or 1)
    payload["attempt"] = int(payload.get("attempt") or 1)
    payload.setdefault("reason", "scarcity_audit_failed")
    payload["violation_notes"] = _string_list(payload.get("violation_notes"))
    payload["warnings"] = _string_list(payload.get("warnings"))
    payload.setdefault("rewrite_instruction", "")
    payload["rewrite_attempts"] = int(payload.get("rewrite_attempts") or 0)
    payload["max_rewrite_attempts"] = int(payload.get("max_rewrite_attempts") or 3)
    payload["scarcity_audit"] = dict(payload.get("scarcity_audit") or {})
    payload["chapter"] = dict(payload.get("chapter") or {})
    parts = payload.get("parts")
    payload["parts"] = [dict(part) for part in parts if isinstance(part, Mapping)] if isinstance(parts, list) else []
    payload.setdefault("combined_script", "")
    payload["created_at"] = str(payload.get("created_at") or _utc_now())
    return payload


def _registry_names_locked_for_payoff(items: Sequence[Any]) -> list[str]:
    names = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if int(item.get("payoff_allowed_at_book") or 999) > 1:
            names.append(name)
    return _dedupe(names)


def _registry_names_allowed_for_hint(items: Sequence[Any]) -> list[str]:
    names = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if name and int(item.get("hint_allowed_at_book") or 1) <= 1:
            names.append(name)
    return _dedupe(names)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _dedupe(values: Sequence[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        result.append(value)
        seen.add(key)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
