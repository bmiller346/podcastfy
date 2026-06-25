"""Character voice card storage and prompt context helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VOICE_CARDS_FILENAME = "voice_cards.json"
VOICE_CARDS_SCHEMA_VERSION = 1


@dataclass(slots=True)
class VoiceCard:
    """Dialogue and narration constraints for one character voice."""

    name: str
    roles: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    sentence_pattern_rules: list[str] = field(default_factory=list)
    forbidden_words: list[str] = field(default_factory=list)
    stress_speech_patterns: list[str] = field(default_factory=list)
    humor_modes: list[str] = field(default_factory=list)
    absurdity_mode: str = ""
    sample_lines: list[str] = field(default_factory=list)
    drift_checks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VoiceCardDeck:
    """Serializable collection of voice cards for a series."""

    series_id: str
    schema_version: int = VOICE_CARDS_SCHEMA_VERSION
    cards: dict[str, VoiceCard] = field(default_factory=dict)


def voice_cards_path(storage_dir: str | Path, series_id: str) -> Path:
    """Return the per-series voice card path under a LitRPG storage root."""

    return Path(storage_dir) / "series" / str(series_id) / VOICE_CARDS_FILENAME


def load_voice_cards(storage_dir: str | Path, series_id: str) -> VoiceCardDeck:
    """Load voice cards, returning an empty deck when no file exists."""

    path = voice_cards_path(storage_dir, series_id)
    if not path.exists():
        return VoiceCardDeck(series_id=str(series_id))

    with path.open("r", encoding="utf-8") as cards_file:
        data = json.load(cards_file)
    if not isinstance(data, dict):
        return VoiceCardDeck(series_id=str(series_id))
    return voice_card_deck_from_dict(data, fallback_series_id=str(series_id))


def save_voice_cards(storage_dir: str | Path, deck: VoiceCardDeck) -> None:
    """Persist voice cards as deterministic, human-readable JSON."""

    path = voice_cards_path(storage_dir, deck.series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as cards_file:
        json.dump(asdict(deck), cards_file, ensure_ascii=True, indent=2, sort_keys=True)
        cards_file.write("\n")


def voice_card_deck_from_dict(
    data: dict[str, Any], fallback_series_id: str = "default-series"
) -> VoiceCardDeck:
    """Build a voice card deck from loose JSON."""

    cards = data.get("cards") or data.get("voice_cards") or {}
    if isinstance(cards, list):
        card_entries = {
            str(item.get("name") or ""): voice_card_from_dict(item)
            for item in cards
            if isinstance(item, dict) and str(item.get("name") or "")
        }
    elif isinstance(cards, dict):
        card_entries = {
            str(key): voice_card_from_dict(value, fallback_name=str(key))
            for key, value in cards.items()
            if isinstance(value, dict)
        }
    else:
        card_entries = {}

    return VoiceCardDeck(
        series_id=str(data.get("series_id") or fallback_series_id),
        schema_version=int(data.get("schema_version") or VOICE_CARDS_SCHEMA_VERSION),
        cards=card_entries,
    )


def voice_card_from_dict(data: dict[str, Any], fallback_name: str = "") -> VoiceCard:
    """Build a voice card from loose JSON."""

    return VoiceCard(
        name=str(data.get("name") or fallback_name),
        roles=_string_list(data.get("roles")),
        aliases=_string_list(data.get("aliases")),
        sentence_pattern_rules=_string_list(data.get("sentence_pattern_rules")),
        forbidden_words=_string_list(data.get("forbidden_words")),
        stress_speech_patterns=_string_list(data.get("stress_speech_patterns")),
        humor_modes=_string_list(data.get("humor_modes")),
        absurdity_mode=str(data.get("absurdity_mode") or "").strip(),
        sample_lines=_string_list(data.get("sample_lines")),
        drift_checks=_string_list(data.get("drift_checks")),
    )


def merge_voice_cards(
    deck: VoiceCardDeck, updates: VoiceCardDeck | dict[str, Any]
) -> VoiceCardDeck:
    """Return a merged deck without mutating the input deck or update payload."""

    merged = voice_card_deck_from_dict(asdict(deck), fallback_series_id=deck.series_id)
    update_deck = (
        updates
        if isinstance(updates, VoiceCardDeck)
        else voice_card_deck_from_dict(updates, fallback_series_id=deck.series_id)
    )

    for _, update_card in update_deck.cards.items():
        existing_key = _find_card_key(merged, update_card)
        if existing_key is None:
            merged.cards[update_card.name] = voice_card_from_dict(asdict(update_card))
            continue
        merged.cards[existing_key] = _merge_voice_card(
            merged.cards[existing_key], update_card
        )

    return merged


def format_voice_card_context(
    deck: VoiceCardDeck,
    relevant_roles: list[str] | tuple[str, ...] | None = None,
    relevant_names: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Return compact prompt context for matching roles or character names."""

    role_filter = {role.casefold() for role in _string_list(relevant_roles)}
    name_filter = {name.casefold() for name in _string_list(relevant_names)}
    cards = [
        card
        for card in deck.cards.values()
        if not role_filter and not name_filter
        or _card_matches(card, role_filter, name_filter)
    ]
    if not cards:
        return ""

    lines = [f"Voice Cards ({deck.series_id})"]
    for card in cards:
        facts = _card_context_facts(card)
        if facts:
            lines.append(f"{card.name}: " + " | ".join(facts))
    return "\n".join(lines)


def _merge_voice_card(existing: VoiceCard, update: VoiceCard) -> VoiceCard:
    merged = voice_card_from_dict(asdict(existing))
    if update.name and update.name != merged.name:
        _extend_unique(merged.aliases, [update.name])
    _extend_unique(merged.roles, update.roles)
    _extend_unique(merged.aliases, update.aliases)
    _extend_unique(merged.sentence_pattern_rules, update.sentence_pattern_rules)
    _extend_unique(merged.forbidden_words, update.forbidden_words)
    _extend_unique(merged.stress_speech_patterns, update.stress_speech_patterns)
    _extend_unique(merged.humor_modes, update.humor_modes)
    if update.absurdity_mode:
        merged.absurdity_mode = update.absurdity_mode
    _extend_unique(merged.sample_lines, update.sample_lines)
    _extend_unique(merged.drift_checks, update.drift_checks)
    return merged


def _find_card_key(deck: VoiceCardDeck, update_card: VoiceCard) -> str | None:
    names = {update_card.name.casefold(), *[alias.casefold() for alias in update_card.aliases]}
    for key, card in deck.cards.items():
        existing_names = {key.casefold(), card.name.casefold()}
        existing_names.update(alias.casefold() for alias in card.aliases)
        if names & existing_names:
            return key
    return None


def _card_matches(
    card: VoiceCard, role_filter: set[str], name_filter: set[str]
) -> bool:
    names = {card.name.casefold(), *[alias.casefold() for alias in card.aliases]}
    roles = {role.casefold() for role in card.roles}
    return bool((name_filter and names & name_filter) or (role_filter and roles & role_filter))


def _card_context_facts(card: VoiceCard) -> list[str]:
    facts: list[str] = []
    for label, values in [
        ("sentence patterns", card.sentence_pattern_rules),
        ("forbidden words", card.forbidden_words),
        ("stress speech", card.stress_speech_patterns),
        ("humor", card.humor_modes),
        ("samples", card.sample_lines),
        ("drift checks", card.drift_checks),
    ]:
        if values:
            facts.append(f"{label}: " + "; ".join(_compact_items(values, limit=3)))
    if card.absurdity_mode:
        facts.append(f"absurdity: {card.absurdity_mode}")
    return facts


def _compact_items(items: list[str], limit: int) -> list[str]:
    compact = [item for item in items if item][:limit]
    if len(items) > limit:
        compact.append(f"+{len(items) - limit} more")
    return compact


def _extend_unique(target: list[str], values: list[str]) -> None:
    seen = {item.casefold() for item in target}
    for value in values:
        normalized = value.strip()
        if not normalized or normalized.casefold() in seen:
            continue
        target.append(normalized)
        seen.add(normalized.casefold())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
