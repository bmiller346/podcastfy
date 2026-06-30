"""Scarcity and mystery timing registry for story-economy constraints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ScarcityItem:
    """One protected resource, mystery, reveal, or payoff window."""

    name: str
    kind: str = "mystery"
    source: str = ""
    hint_allowed_at_book: int = 1
    reveal_allowed_at_book: int = 999
    payoff_allowed_at_book: int = 999
    forbidden_payoff: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScarcityDecision:
    """Deterministic decision for using one scarcity item in a book."""

    name: str
    book: int
    hint_allowed: bool
    reveal_allowed: bool
    payoff_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScarcityRegistry:
    """Normalized constraints from architecture, foreshadowing, and hook locks."""

    items: list[ScarcityItem] = field(default_factory=list)
    scarcity_constraints: list[str] = field(default_factory=list)

    @classmethod
    def from_sources(
        cls,
        *,
        series_mysteries: Sequence[Any] | None = None,
        must_preserve: Sequence[Any] | None = None,
        must_not_spend: Sequence[Any] | None = None,
        foreshadow_ledger: Mapping[str, Any] | None = None,
        hook_locks: Sequence[Any] | Mapping[str, Any] | None = None,
        scarcity_constraints: Sequence[Any] | None = None,
        current_book: int = 1,
    ) -> "ScarcityRegistry":
        items: list[ScarcityItem] = []
        items.extend(
            _items_from_strings(
                series_mysteries,
                kind="series_mystery",
                source="series_mysteries",
                hint_book=1,
                reveal_book=current_book + 1,
                payoff_book=current_book + 1,
            )
        )
        items.extend(
            _items_from_strings(
                must_preserve,
                kind="preserve",
                source="must_preserve",
                hint_book=1,
                reveal_book=current_book + 1,
                payoff_book=current_book + 1,
            )
        )
        items.extend(
            _items_from_strings(
                must_not_spend,
                kind="must_not_spend",
                source="must_not_spend",
                hint_book=1,
                reveal_book=current_book + 1,
                payoff_book=current_book + 1,
            )
        )
        items.extend(_items_from_foreshadow_ledger(foreshadow_ledger))
        items.extend(_items_from_hook_locks(hook_locks, current_book=current_book))
        return cls(
            items=_dedupe_items(items),
            scarcity_constraints=_dedupe_texts(scarcity_constraints or []),
        )

    @classmethod
    def from_task(cls, task: Mapping[str, Any]) -> "ScarcityRegistry":
        contract = _mapping_or_empty(task.get("chapter_contract"))
        book_plan = _mapping_or_empty(task.get("book_plan"))
        series_plan = _mapping_or_empty(task.get("series_plan") or task.get("series_shape"))
        current_book = _int_or_default(
            task.get("book_number") or contract.get("book") or book_plan.get("book"),
            1,
        )
        return cls.from_sources(
            series_mysteries=_first_sequence(
                task.get("series_mysteries"),
                series_plan.get("series_mysteries"),
            ),
            must_preserve=[
                *_sequence_or_empty(task.get("must_preserve")),
                *_sequence_or_empty(book_plan.get("must_preserve")),
                *_sequence_or_empty(contract.get("must_preserve")),
            ],
            must_not_spend=[
                *_sequence_or_empty(task.get("must_not_spend")),
                *_sequence_or_empty(contract.get("must_not_spend")),
            ],
            foreshadow_ledger=_mapping_or_none(task.get("foreshadow_ledger")),
            hook_locks=task.get("hook_locks") or contract.get("mystery_lock"),
            scarcity_constraints=[
                *_sequence_or_empty(task.get("scarcity_constraints")),
                *_sequence_or_empty(contract.get("scarcity_constraints")),
                *_sequence_or_empty(book_plan.get("scarcity_constraints")),
            ],
            current_book=current_book,
        )

    def decision_for(self, name: str, *, book: int) -> ScarcityDecision:
        item = self._find(name)
        if item is None:
            return ScarcityDecision(
                name=str(name),
                book=book,
                hint_allowed=True,
                reveal_allowed=True,
                payoff_allowed=True,
                reason="No scarcity lock is registered for this item.",
            )
        hint = book >= item.hint_allowed_at_book
        reveal = book >= item.reveal_allowed_at_book
        payoff = book >= item.payoff_allowed_at_book
        if not hint:
            reason = f"Hints are locked until book {item.hint_allowed_at_book}."
        elif not reveal:
            reason = f"Hints allowed; reveal locked until book {item.reveal_allowed_at_book}."
        elif not payoff:
            reason = f"Reveal allowed; payoff locked until book {item.payoff_allowed_at_book}."
        else:
            reason = "Hint, reveal, and payoff are allowed for this book."
        return ScarcityDecision(
            name=item.name,
            book=book,
            hint_allowed=hint,
            reveal_allowed=reveal,
            payoff_allowed=payoff,
            reason=reason,
        )

    def can_hint(self, name: str, *, book: int) -> bool:
        return self.decision_for(name, book=book).hint_allowed

    def can_reveal(self, name: str, *, book: int) -> bool:
        return self.decision_for(name, book=book).reveal_allowed

    def can_payoff(self, name: str, *, book: int) -> bool:
        return self.decision_for(name, book=book).payoff_allowed

    def to_anchor_payload(self, *, book: int) -> dict[str, Any]:
        forbidden_now = [
            item.name
            for item in self.items
            if not self.decision_for(item.name, book=book).payoff_allowed
        ]
        allowed_hints = [
            item.name
            for item in self.items
            if self.decision_for(item.name, book=book).hint_allowed
        ]
        reveal_locks = [
            _lock_line(item)
            for item in self.items
            if not self.decision_for(item.name, book=book).reveal_allowed
        ]
        payoff_locks = [
            _lock_line(item)
            for item in self.items
            if not self.decision_for(item.name, book=book).payoff_allowed
        ]
        return {
            "forbidden_mysteries": forbidden_now,
            "forbidden_now": forbidden_now,
            "allowed_hints": allowed_hints,
            "reveal_locks": reveal_locks,
            "payoff_locks": payoff_locks,
            "scarcity_constraints": list(self.scarcity_constraints),
            "hint_allowed_at_book": [
                f"{item.name}: book {item.hint_allowed_at_book}" for item in self.items
            ],
            "reveal_allowed_at_book": [
                f"{item.name}: book {item.reveal_allowed_at_book}" for item in self.items
            ],
            "payoff_allowed_at_book": [
                f"{item.name}: book {item.payoff_allowed_at_book}" for item in self.items
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "scarcity_constraints": list(self.scarcity_constraints),
        }

    def _find(self, name: str) -> ScarcityItem | None:
        wanted = str(name or "").strip().casefold()
        for item in self.items:
            if item.name.casefold() == wanted:
                return item
        return None


def _items_from_strings(
    values: Sequence[Any] | None,
    *,
    kind: str,
    source: str,
    hint_book: int,
    reveal_book: int,
    payoff_book: int,
) -> list[ScarcityItem]:
    return [
        ScarcityItem(
            name=text,
            kind=kind,
            source=source,
            hint_allowed_at_book=hint_book,
            reveal_allowed_at_book=reveal_book,
            payoff_allowed_at_book=payoff_book,
        )
        for text in _dedupe_texts(values or [])
    ]


def _items_from_foreshadow_ledger(ledger: Mapping[str, Any] | None) -> list[ScarcityItem]:
    if not ledger:
        return []
    items = []
    for source_key in ("planted", "ready_to_pay"):
        for entry in _sequence_or_empty(ledger.get(source_key)):
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("mystery") or entry.get("detail") or "").strip()
            if not name:
                continue
            payoff_book = _int_or_default(entry.get("payoff_book") or entry.get("book"), 1)
            planted_book = _int_or_default(entry.get("planted_book"), 1)
            status = str(entry.get("status") or source_key)
            reveal_book = payoff_book if status != "ready_to_pay" else min(payoff_book, planted_book)
            items.append(
                ScarcityItem(
                    name=name,
                    kind="foreshadow",
                    source=f"foreshadow_ledger.{source_key}",
                    hint_allowed_at_book=planted_book,
                    reveal_allowed_at_book=reveal_book,
                    payoff_allowed_at_book=payoff_book,
                    notes=str(entry.get("detail") or ""),
                )
            )
    return items


def _items_from_hook_locks(
    hook_locks: Sequence[Any] | Mapping[str, Any] | None,
    *,
    current_book: int,
) -> list[ScarcityItem]:
    values: list[Any]
    if hook_locks is None:
        return []
    if isinstance(hook_locks, Mapping):
        values = [hook_locks]
    elif isinstance(hook_locks, (str, bytes)):
        values = [str(hook_locks)]
    else:
        values = list(hook_locks)
    items: list[ScarcityItem] = []
    for lock in values:
        if isinstance(lock, Mapping):
            name = str(lock.get("question") or lock.get("mystery") or lock.get("detail") or "").strip()
            if not name:
                continue
            items.append(
                ScarcityItem(
                    name=name,
                    kind="hook_lock",
                    source="hook_locks",
                    hint_allowed_at_book=_int_or_default(lock.get("hint_allowed_at_book"), 1),
                    reveal_allowed_at_book=_int_or_default(
                        lock.get("reveal_allowed_at_book"),
                        current_book + 1,
                    ),
                    payoff_allowed_at_book=_int_or_default(
                        lock.get("payoff_allowed_at_book"),
                        current_book + 1,
                    ),
                    forbidden_payoff=str(lock.get("forbidden_payoff") or ""),
                )
            )
        else:
            text = str(lock or "").strip()
            if text:
                items.append(
                    ScarcityItem(
                        name=text,
                        kind="hook_lock",
                        source="hook_locks",
                        hint_allowed_at_book=1,
                        reveal_allowed_at_book=current_book + 1,
                        payoff_allowed_at_book=current_book + 1,
                    )
                )
    return items


def _dedupe_items(items: Sequence[ScarcityItem]) -> list[ScarcityItem]:
    by_name: dict[str, ScarcityItem] = {}
    for item in items:
        key = item.name.casefold()
        existing = by_name.get(key)
        if existing is None:
            by_name[key] = item
            continue
        by_name[key] = ScarcityItem(
            name=existing.name,
            kind=existing.kind,
            source=", ".join(_dedupe_texts([existing.source, item.source])),
            hint_allowed_at_book=min(existing.hint_allowed_at_book, item.hint_allowed_at_book),
            reveal_allowed_at_book=max(existing.reveal_allowed_at_book, item.reveal_allowed_at_book),
            payoff_allowed_at_book=max(existing.payoff_allowed_at_book, item.payoff_allowed_at_book),
            forbidden_payoff=existing.forbidden_payoff or item.forbidden_payoff,
            notes=existing.notes or item.notes,
        )
    return [by_name[key] for key in sorted(by_name)]


def _lock_line(item: ScarcityItem) -> str:
    text = (
        f"{item.name}: reveal book {item.reveal_allowed_at_book}, "
        f"payoff book {item.payoff_allowed_at_book}"
    )
    if item.forbidden_payoff:
        text += f", forbidden payoff: {item.forbidden_payoff}"
    return text


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _first_sequence(*values: Any) -> Sequence[Any]:
    for value in values:
        sequence = _sequence_or_empty(value)
        if sequence:
            return sequence
    return []


def _sequence_or_empty(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    if isinstance(value, Sequence):
        return list(value)
    return []


def _int_or_default(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _dedupe_texts(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        result.append(text)
        seen.add(key)
    return result
