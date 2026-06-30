"""Promise reporting over the existing foreshadow ledger."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.foreshadowing import ForeshadowLedger
from podcastfy.litrpg.foreshadowing import compute_ready_to_pay
from podcastfy.litrpg.foreshadowing import foreshadow_ledger_from_dict


PROMISE_TYPES = {
    "mystery",
    "emotional_debt",
    "relationship_debt",
    "mechanics_promise",
    "artifact_promise",
    "faction_threat",
    "joke_callback",
}


@dataclass(slots=True)
class PromiseStatus:
    planted_chapter: int
    type: str
    reader_facing_wording: str
    intended_payoff_window: str
    required_setup: list[str]
    current_status: str
    resolution_state: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_promise_report(
    ledger: ForeshadowLedger | Mapping[str, Any],
    *,
    book: int,
    chapter: int,
    extra_promises: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return active, overdue, and ready promises without a second persistence file."""

    source = ledger if isinstance(ledger, ForeshadowLedger) else foreshadow_ledger_from_dict(dict(ledger))
    ready_ledger = compute_ready_to_pay(source, book, chapter)
    promises = [_from_foreshadow(entry) for entry in source.planted]
    promises.extend(_from_extra(item) for item in (extra_promises or []) if isinstance(item, Mapping))
    ready_keys = {item.detail.casefold() for item in ready_ledger.ready_to_pay}
    active = []
    ready = []
    overdue = []
    for promise in promises:
        payload = promise.to_dict()
        if promise.resolution_state in {"paid", "abandoned"}:
            continue
        if promise.reader_facing_wording.casefold() in ready_keys or promise.current_status == "ready_to_pay":
            payload["current_status"] = "ready_to_pay"
            ready.append(payload)
        elif _is_overdue(promise, book=book, chapter=chapter):
            payload["current_status"] = "overdue"
            overdue.append(payload)
        else:
            active.append(payload)
    return {"active": active, "ready_to_pay": ready, "overdue": overdue, "source": "foreshadow_ledger_wrapper"}


def validate_promise_status(promise: Mapping[str, Any]) -> dict[str, Any]:
    missing = [
        key
        for key in (
            "planted_chapter",
            "type",
            "reader_facing_wording",
            "intended_payoff_window",
            "current_status",
            "resolution_state",
        )
        if promise.get(key) in (None, "", [], {})
    ]
    issues = []
    if promise.get("type") not in PROMISE_TYPES:
        issues.append("unsupported promise type")
    return {"passed": not missing and not issues, "missing": missing, "issues": issues}


def _from_foreshadow(entry: Any) -> PromiseStatus:
    return PromiseStatus(
        planted_chapter=int(entry.planted_chapter),
        type="mystery",
        reader_facing_wording=str(entry.detail),
        intended_payoff_window=f"book {entry.payoff_book} chapters {entry.intended_payoff_start}-{entry.intended_payoff_end}",
        required_setup=[str(entry.mystery)] if entry.mystery else [],
        current_status=str(entry.status),
        resolution_state="paid" if str(entry.status) == "paid" else "delayed" if str(entry.status) == "delayed" else "active",
        source="foreshadow_ledger",
    )


def _from_extra(item: Mapping[str, Any]) -> PromiseStatus:
    ptype = str(item.get("type") or "mystery")
    if ptype not in PROMISE_TYPES:
        ptype = "mystery"
    return PromiseStatus(
        planted_chapter=int(item.get("planted_chapter") or 1),
        type=ptype,
        reader_facing_wording=str(item.get("reader_facing_wording") or item.get("detail") or ""),
        intended_payoff_window=str(item.get("intended_payoff_window") or ""),
        required_setup=[str(value) for value in item.get("required_setup") or []],
        current_status=str(item.get("current_status") or "planted"),
        resolution_state=str(item.get("resolution_state") or item.get("paid_delayed_abandoned") or "active"),
        source=str(item.get("source") or "chapter_contract"),
    )


def _is_overdue(promise: PromiseStatus, *, book: int, chapter: int) -> bool:
    text = promise.intended_payoff_window.lower()
    import re

    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if len(numbers) >= 3:
        return book >= numbers[0] and chapter > numbers[-1]
    if len(numbers) >= 2:
        return chapter > numbers[-1]
    return False
