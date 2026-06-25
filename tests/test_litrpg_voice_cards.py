import json

from podcastfy.litrpg.voice_cards import VoiceCard, VoiceCardDeck
from podcastfy.litrpg.voice_cards import format_voice_card_context
from podcastfy.litrpg.voice_cards import load_voice_cards, merge_voice_cards
from podcastfy.litrpg.voice_cards import save_voice_cards, voice_cards_path


def test_voice_cards_round_trip_persistence(tmp_path):
    deck = VoiceCardDeck(
        series_id="ember-keep",
        cards={
            "Mara": VoiceCard(
                name="Mara",
                roles=["protagonist"],
                aliases=["Stapler Witch"],
                sentence_pattern_rules=["Short first sentence, then a dry correction."],
                forbidden_words=["destiny"],
                stress_speech_patterns=["Uses office policy as a shield."],
                humor_modes=["deadpan accounting panic"],
                absurdity_mode="Treat impossible objects like workplace hazards.",
                sample_lines=["No, the printer cult is not a stakeholder."],
                drift_checks=["Never becomes breezy or mystical."],
            )
        },
    )

    save_voice_cards(tmp_path, deck)
    loaded = load_voice_cards(tmp_path, "ember-keep")

    assert loaded == deck
    assert voice_cards_path(tmp_path, "ember-keep") == (
        tmp_path / "series" / "ember-keep" / "voice_cards.json"
    )
    raw = (tmp_path / "series" / "ember-keep" / "voice_cards.json").read_text(
        encoding="utf-8"
    )
    assert raw.endswith("\n")
    assert json.loads(raw)["cards"]["Mara"]["forbidden_words"] == ["destiny"]


def test_merge_voice_cards_dedupes_without_mutating_inputs():
    deck = VoiceCardDeck(
        series_id="ember-keep",
        cards={
            "Mara": VoiceCard(
                name="Mara",
                aliases=["Stapler Witch"],
                forbidden_words=["destiny"],
                humor_modes=["deadpan"],
            )
        },
    )
    updates = {
        "cards": {
            "Stapler Witch": {
                "name": "Stapler Witch",
                "aliases": ["Mara"],
                "forbidden_words": ["Destiny", "chosen one"],
                "humor_modes": ["deadpan", "procedural sarcasm"],
                "absurdity_mode": "Mocks impossible loot as bad procurement.",
            }
        }
    }

    merged = merge_voice_cards(deck, updates)

    assert merged is not deck
    assert deck.cards["Mara"].forbidden_words == ["destiny"]
    assert updates["cards"]["Stapler Witch"]["forbidden_words"] == [
        "Destiny",
        "chosen one",
    ]
    assert merged.cards["Mara"].aliases == ["Stapler Witch", "Mara"]
    assert merged.cards["Mara"].forbidden_words == ["destiny", "chosen one"]
    assert merged.cards["Mara"].humor_modes == ["deadpan", "procedural sarcasm"]
    assert merged.cards["Mara"].absurdity_mode == "Mocks impossible loot as bad procurement."


def test_format_voice_card_context_filters_relevant_roles_and_names():
    deck = VoiceCardDeck(
        series_id="ember-keep",
        cards={
            "Mara": VoiceCard(
                name="Mara",
                roles=["protagonist"],
                sentence_pattern_rules=["Clipped under stress."],
                forbidden_words=["destiny"],
                stress_speech_patterns=["Over-explains rules when frightened."],
                humor_modes=["dry panic"],
                absurdity_mode="Practical complaint before awe.",
                sample_lines=["Absolutely not. That chest has payroll energy."],
                drift_checks=["Do not make her poetic."],
            ),
            "Vex": VoiceCard(
                name="Vex",
                roles=["rival"],
                sentence_pattern_rules=["Grandiose threats."],
            ),
        },
    )

    context = format_voice_card_context(
        deck, relevant_roles=["protagonist"], relevant_names=["Unknown"]
    )

    assert context.startswith("Voice Cards (ember-keep)")
    assert "Mara: sentence patterns: Clipped under stress." in context
    assert "forbidden words: destiny" in context
    assert "stress speech: Over-explains rules when frightened." in context
    assert "humor: dry panic" in context
    assert "absurdity: Practical complaint before awe." in context
    assert "samples: Absolutely not. That chest has payroll energy." in context
    assert "drift checks: Do not make her poetic." in context
    assert "Vex" not in context
