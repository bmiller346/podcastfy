"""Foreshadow ledger storage and prompt context helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FORESHADOW_LEDGER_FILENAME = "foreshadow_ledger.json"
FORESHADOW_SCHEMA_VERSION = 1
STATUS_PLANTED = "planted"
STATUS_READY = "ready_to_pay"
STATUS_PAID = "paid"


@dataclass(slots=True)
class ForeshadowEntry:
    """A planted mystery or promise with an intended payoff window."""

    detail: str
    planted_chapter: int
    intended_payoff_start: int
    intended_payoff_end: int
    mystery: str
    status: str = STATUS_PLANTED
    planted_book: int = 1
    payoff_book: int = 1
    paid_chapter: int | None = None


@dataclass(slots=True)
class ForeshadowLedger:
    """Serializable foreshadow state for a series."""

    series_id: str
    schema_version: int = FORESHADOW_SCHEMA_VERSION
    planted: list[ForeshadowEntry] = field(default_factory=list)
    ready_to_pay: list[ForeshadowEntry] = field(default_factory=list)


def foreshadow_ledger_path(storage_dir: str | Path, series_id: str) -> Path:
    """Return the per-series foreshadow ledger path under a LitRPG storage root."""

    return Path(storage_dir) / "series" / str(series_id) / FORESHADOW_LEDGER_FILENAME


def load_foreshadow_ledger(storage_dir: str | Path, series_id: str) -> ForeshadowLedger:
    """Load a foreshadow ledger, returning an empty ledger when absent."""

    path = foreshadow_ledger_path(storage_dir, series_id)
    if not path.exists():
        return ForeshadowLedger(series_id=str(series_id))

    with path.open("r", encoding="utf-8") as ledger_file:
        data = json.load(ledger_file)
    if not isinstance(data, dict):
        return ForeshadowLedger(series_id=str(series_id))
    return foreshadow_ledger_from_dict(data, fallback_series_id=str(series_id))


def save_foreshadow_ledger(storage_dir: str | Path, ledger: ForeshadowLedger) -> None:
    """Persist a foreshadow ledger as deterministic, human-readable JSON."""

    path = foreshadow_ledger_path(storage_dir, ledger.series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as ledger_file:
        json.dump(asdict(ledger), ledger_file, ensure_ascii=True, indent=2, sort_keys=True)
        ledger_file.write("\n")


def foreshadow_ledger_from_dict(
    data: dict[str, Any], fallback_series_id: str = "default-series"
) -> ForeshadowLedger:
    """Build a foreshadow ledger from loose JSON."""

    planted = [
        foreshadow_entry_from_dict(item)
        for item in _dict_list(data.get("planted"))
        if str(item.get("detail") or "").strip()
    ]
    ready = [
        foreshadow_entry_from_dict(item)
        for item in _dict_list(data.get("ready_to_pay"))
        if str(item.get("detail") or "").strip()
    ]
    return ForeshadowLedger(
        series_id=str(data.get("series_id") or fallback_series_id),
        schema_version=int(data.get("schema_version") or FORESHADOW_SCHEMA_VERSION),
        planted=_dedupe_entries(planted),
        ready_to_pay=_dedupe_entries(ready),
    )


def foreshadow_entry_from_dict(data: dict[str, Any]) -> ForeshadowEntry:
    """Build a foreshadow entry from loose JSON."""

    payoff_range = data.get("intended_payoff_range")
    if isinstance(payoff_range, (list, tuple)) and len(payoff_range) >= 2:
        start = _int_value(payoff_range[0], 0)
        end = _int_value(payoff_range[1], start)
    else:
        start = _int_value(data.get("intended_payoff_start"), 0)
        end = _int_value(data.get("intended_payoff_end"), start)

    return ForeshadowEntry(
        detail=str(data.get("detail") or "").strip(),
        planted_chapter=_int_value(data.get("planted_chapter"), 0),
        intended_payoff_start=start,
        intended_payoff_end=max(start, end),
        mystery=str(data.get("mystery") or "").strip(),
        status=str(data.get("status") or STATUS_PLANTED).strip() or STATUS_PLANTED,
        planted_book=_int_value(data.get("planted_book"), 1),
        payoff_book=_int_value(data.get("payoff_book"), _int_value(data.get("book"), 1)),
        paid_chapter=(
            _int_value(data.get("paid_chapter"), 0)
            if data.get("paid_chapter") is not None
            else None
        ),
    )


def add_plants(
    ledger: ForeshadowLedger, entries: list[ForeshadowEntry] | list[dict[str, Any]]
) -> ForeshadowLedger:
    """Return a ledger with new planted entries added and deduplicated."""

    updated = foreshadow_ledger_from_dict(asdict(ledger), fallback_series_id=ledger.series_id)
    new_entries = [
        entry if isinstance(entry, ForeshadowEntry) else foreshadow_entry_from_dict(entry)
        for entry in entries
    ]
    updated.planted = _dedupe_entries([*updated.planted, *new_entries])
    updated.ready_to_pay = _dedupe_entries(updated.ready_to_pay)
    return updated


def mark_paid(
    ledger: ForeshadowLedger,
    detail: str,
    paid_chapter: int,
    book: int | None = None,
) -> ForeshadowLedger:
    """Return a ledger with matching entries marked paid."""

    updated = foreshadow_ledger_from_dict(asdict(ledger), fallback_series_id=ledger.series_id)
    wanted = detail.strip().casefold()
    for entry in [*updated.planted, *updated.ready_to_pay]:
        if entry.detail.casefold() != wanted:
            continue
        if book is not None and entry.payoff_book != book:
            continue
        entry.status = STATUS_PAID
        entry.paid_chapter = paid_chapter
    updated.ready_to_pay = [
        entry for entry in updated.ready_to_pay if entry.status != STATUS_PAID
    ]
    return updated


def compute_ready_to_pay(
    ledger: ForeshadowLedger, book: int, chapter: int
) -> ForeshadowLedger:
    """Return a ledger whose ready list reflects entries inside the payoff window."""

    updated = foreshadow_ledger_from_dict(asdict(ledger), fallback_series_id=ledger.series_id)
    ready: list[ForeshadowEntry] = []
    for entry in updated.planted:
        if entry.status == STATUS_PAID:
            continue
        if entry.payoff_book != book:
            continue
        if entry.intended_payoff_start <= chapter <= entry.intended_payoff_end:
            ready_entry = foreshadow_entry_from_dict(asdict(entry))
            ready_entry.status = STATUS_READY
            ready.append(ready_entry)
    updated.ready_to_pay = _dedupe_entries(ready)
    return updated


def format_foreshadow_context(
    ledger: ForeshadowLedger,
    book: int | None = None,
    chapter: int | None = None,
) -> str:
    """Return compact prompt context for planted and ready payoff threads."""

    context_ledger = (
        compute_ready_to_pay(ledger, book, chapter)
        if book is not None and chapter is not None
        else foreshadow_ledger_from_dict(asdict(ledger), fallback_series_id=ledger.series_id)
    )
    lines = [f"Foreshadow Ledger ({context_ledger.series_id})"]
    ready = context_ledger.ready_to_pay
    if ready:
        lines.append("Ready to pay:")
        lines.extend(f"- {_entry_context(entry)}" for entry in ready)

    planted = [entry for entry in context_ledger.planted if entry.status != STATUS_PAID]
    if planted:
        lines.append("Planted:")
        lines.extend(f"- {_entry_context(entry)}" for entry in planted)

    return "\n".join(lines) if len(lines) > 1 else ""


def _entry_context(entry: ForeshadowEntry) -> str:
    return (
        f"{entry.detail} | mystery: {entry.mystery} | planted: "
        f"book {entry.planted_book} chapter {entry.planted_chapter} | payoff: "
        f"book {entry.payoff_book} chapters {entry.intended_payoff_start}-"
        f"{entry.intended_payoff_end} | status: {entry.status}"
    )


def _dedupe_entries(entries: list[ForeshadowEntry]) -> list[ForeshadowEntry]:
    deduped: list[ForeshadowEntry] = []
    seen: set[tuple[Any, ...]] = set()
    for entry in entries:
        key = _entry_key(entry)
        if key in seen:
            continue
        deduped.append(foreshadow_entry_from_dict(asdict(entry)))
        seen.add(key)
    return deduped


def _entry_key(entry: ForeshadowEntry) -> tuple[Any, ...]:
    return (
        entry.detail.casefold(),
        entry.mystery.casefold(),
        entry.planted_book,
        entry.planted_chapter,
        entry.payoff_book,
        entry.intended_payoff_start,
        entry.intended_payoff_end,
    )


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
