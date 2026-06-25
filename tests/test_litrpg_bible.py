import json

from podcastfy.litrpg.bible import BIBLE_SCHEMA_VERSION, CharacterBibleEntry
from podcastfy.litrpg.bible import StoryBible, format_story_bible_summary
from podcastfy.litrpg.bible import load_story_bible, merge_story_bible_updates
from podcastfy.litrpg.bible import save_story_bible, story_bible_path


def test_load_story_bible_returns_default_when_missing(tmp_path):
    bible = load_story_bible(tmp_path, "ember-keep")

    assert bible == StoryBible(series_id="ember-keep")
    assert bible.schema_version == BIBLE_SCHEMA_VERSION
    assert bible.characters == {}
    assert story_bible_path(tmp_path, "ember-keep") == (
        tmp_path / "series" / "ember-keep" / "story_bible.json"
    )


def test_story_bible_round_trip_persistence(tmp_path):
    bible = StoryBible(
        series_id="ember-keep",
        premise="A failed clerk survives a dungeon reality show.",
        never_contradict_facts=["Mara cannot read system glyphs without pain."],
        unresolved_threads=["The sponsor contract is unsigned."],
        timeline_notes=["Episode 1: Mara woke under the arena floor."],
        characters={
            "Mara": CharacterBibleEntry(
                name="Mara",
                aliases=["The Stapler Witch"],
                wounds=["Afraid of being laughed out of rooms."],
                visual_anchors_static=["Permanent toner scar across left eyebrow."],
                current_injuries=["Limping from copier mimic bite."],
                equipped_gear=["Stapler shield (jammed)."],
                gear_absurd_traits=["Inventory pouch smells like microwaved fish."],
                description_rules=["Describe exhaustion physically before naming emotion."],
                running_jokes=["Invents office crimes under stress."],
                favorite_insults=["Budget necromancer"],
                never_contradict_facts=["Mara refuses to kneel to the System."],
                voice_rules=["Dry, clipped, more scared than she admits."],
            )
        },
    )

    save_story_bible(tmp_path, bible)
    loaded = load_story_bible(tmp_path, "ember-keep")

    assert loaded == bible
    raw = (tmp_path / "series" / "ember-keep" / "story_bible.json").read_text(
        encoding="utf-8"
    )
    assert raw.endswith("\n")
    raw_bible = json.loads(raw)
    assert raw_bible["schema_version"] == BIBLE_SCHEMA_VERSION
    assert raw_bible["characters"]["Mara"]["voice_rules"] == [
        "Dry, clipped, more scared than she admits."
    ]
    assert raw_bible["characters"]["Mara"]["current_injuries"] == [
        "Limping from copier mimic bite."
    ]


def test_merge_story_bible_updates_keeps_existing_facts_and_deduplicates():
    bible = StoryBible(
        series_id="ember-keep",
        premise="Original premise.",
        never_contradict_facts=["The arena is underground."],
        characters={
            "Mara": CharacterBibleEntry(
                name="Mara",
                aliases=["Stapler Witch"],
                wounds=["Fears public humiliation."],
                voice_rules=["Dry under pressure."],
            )
        },
    )

    updated = merge_story_bible_updates(
        bible,
        {
            "series_id": "ember-keep",
            "premise": "",
            "never_contradict_facts": [
                "The arena is underground.",
                "Sponsors can alter loot tables.",
            ],
            "characters": {
                "Mara": {
                    "name": "Mara",
                    "wounds": [],
                    "visual_anchors": {
                        "dynamic": ["Tie worn like a defeated battle standard."]
                    },
                    "physical_degradation": {
                        "current_injuries": ["Limping from copier mimic bite."],
                        "fatigue_markers": ["Hands shake after system announcements."],
                    },
                    "gear_silhouette": {
                        "equipped": ["Stapler shield (jammed)."],
                        "absurd_traits": ["Helmet fogs when lying."],
                    },
                    "description_rules": [
                        "Never describe gear without current disrepair."
                    ],
                    "traumas": ["The tutorial boss wore her manager's voice."],
                    "voice_rules": [
                        "dry under pressure.",
                        "Never sounds fully comfortable with praise.",
                    ],
                },
                "Vex": {
                    "name": "Vex",
                    "rivalries": ["Mara"],
                    "favorite_insults": ["Paper-armored clerk"],
                },
            },
        },
    )

    assert updated is bible
    assert updated.premise == "Original premise."
    assert updated.never_contradict_facts == [
        "The arena is underground.",
        "Sponsors can alter loot tables.",
    ]
    assert updated.characters["Mara"].wounds == ["Fears public humiliation."]
    assert updated.characters["Mara"].traumas == [
        "The tutorial boss wore her manager's voice."
    ]
    assert updated.characters["Mara"].voice_rules == [
        "Dry under pressure.",
        "Never sounds fully comfortable with praise.",
    ]
    assert updated.characters["Mara"].visual_anchors_dynamic == [
        "Tie worn like a defeated battle standard."
    ]
    assert updated.characters["Mara"].current_injuries == [
        "Limping from copier mimic bite."
    ]
    assert updated.characters["Mara"].equipped_gear == ["Stapler shield (jammed)."]
    assert updated.characters["Mara"].gear_absurd_traits == ["Helmet fogs when lying."]
    assert updated.characters["Vex"].rivalries == ["Mara"]


def test_format_story_bible_summary_is_compact_prompt_context():
    bible = StoryBible(
        series_id="ember-keep",
        premise="A failed clerk survives a dungeon reality show.",
        never_contradict_facts=["Mara cannot read system glyphs without pain."],
        unresolved_threads=["The sponsor contract is unsigned."],
        timeline_notes=["Episode 1: Mara woke under the arena floor."],
        characters={
            "Mara": CharacterBibleEntry(
                name="Mara",
                wounds=["Afraid of being laughed out of rooms."],
                visual_anchors_static=["Permanent toner scar across left eyebrow."],
                current_injuries=["Limping from copier mimic bite."],
                equipped_gear=["Stapler shield (jammed)."],
                gear_absurd_traits=["Inventory pouch smells like microwaved fish."],
                description_rules=["Show emotion through posture before naming it."],
                running_jokes=["Invents office crimes under stress."],
                rivalries=["Vex"],
                unresolved_promises=["Promised Jin she would not use blood magic."],
                favorite_insults=["Budget necromancer"],
                never_contradict_facts=["Mara refuses to kneel to the System."],
                voice_rules=["Dry, clipped, more scared than she admits."],
            )
        },
    )

    summary = format_story_bible_summary(bible)

    assert summary.startswith("Story Bible (ember-keep)")
    assert "Premise: A failed clerk survives a dungeon reality show." in summary
    assert "Never contradict: Mara cannot read system glyphs without pain." in summary
    assert "Mara: facts: Mara refuses to kneel to the System." in summary
    assert "voice: Dry, clipped, more scared than she admits." in summary
    assert "visual: Permanent toner scar across left eyebrow." in summary
    assert "body: Limping from copier mimic bite." in summary
    assert "gear: Stapler shield (jammed)." in summary
    assert "description: Show emotion through posture before naming it." in summary
