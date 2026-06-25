import json

from podcastfy.litrpg.bible import load_story_bible
from podcastfy.litrpg.continuity import load_continuity_ledger, load_world_register
from podcastfy.litrpg.foreshadowing import load_foreshadow_ledger
from podcastfy.litrpg.premise_intake import extract_premise_intake_json
from podcastfy.litrpg.premise_intake import run_premise_intake
from podcastfy.litrpg.series_architect import SeriesArchitect, load_chapter_outline
from podcastfy.litrpg.task import run_litrpg_task_data
from podcastfy.litrpg.voice_cards import load_voice_cards


class FakePremiseLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        return "```json\n" + json.dumps(self.payload) + "\n```"


def test_extract_premise_intake_json_accepts_fenced_output():
    parsed = extract_premise_intake_json('Here:\n```json\n{"series_shape": {"target_books": 1}}\n```')

    assert parsed["series_shape"]["target_books"] == 1


def test_run_premise_intake_writes_story_engine_artifacts(tmp_path):
    payload = _payload()
    llm = FakePremiseLLM(payload)

    result = run_premise_intake(
        storage_dir=tmp_path,
        series_id="knotty-buoy",
        premise="Edward and Kelli survive a dungeon on a catamaran.",
        llm=llm,
        target_books=1,
        chapters_per_book=3,
        series_title="The Knotty Buoy",
    )

    assert llm.calls[0]["stage"] == "premise_intake"
    assert "Series Architect intake tool" in llm.calls[0]["prompt"]
    assert any(path.endswith("story_bible.json") for path in result.written_files)
    assert any(path.endswith("chapter_outline.json") for path in result.written_files)

    contract = SeriesArchitect(tmp_path, "knotty-buoy").get_chapter_contract(
        book_number=1,
        chapter_number=2,
    )
    assert contract["series_title"] == "The Knotty Buoy"
    assert contract["title"] == "The Familiar's First Words"
    assert contract["character_focus"] == ["Kelli Marsh", "Pedro"]

    bible = load_story_bible(tmp_path, "knotty-buoy")
    assert bible.characters["Edward Marsh"].voice_rules == [
        "Gruff South Jersey pragmatism under cosmic pressure."
    ]
    assert "The Knotty Buoy is a mobile guild hall" in bible.never_contradict_facts

    voice_cards = load_voice_cards(tmp_path, "knotty-buoy")
    assert "Pedro" in voice_cards.cards
    assert "construction phrases become psychic debuffs" in voice_cards.cards["Pedro"].humor_modes

    continuity = load_continuity_ledger(tmp_path, "knotty-buoy")
    assert continuity.running_gags[0].text == "Edward treats cosmic apocalypse like a code inspection."

    world = load_world_register(tmp_path, "knotty-buoy")
    assert world.locations[0].name == "The Knotty Buoy"
    assert world.entity_ecology[0].entity == "Barnacle Mimics"

    foreshadow = load_foreshadow_ledger(tmp_path, "knotty-buoy")
    assert foreshadow.planted[0].mystery == "System Architects grievance"

    outline = load_chapter_outline(tmp_path, "knotty-buoy", 1)
    assert [entry.title for entry in outline] == [
        "Out of the Atlantic",
        "The Familiar's First Words",
        "Decompression",
    ]


def test_litrpg_task_supports_premise_intake_mode(tmp_path):
    result = run_litrpg_task_data(
        {
            "mode": "premise_intake",
            "series_id": "knotty-buoy",
            "storage_dir": "library",
            "premise": "Dump all notes here.",
            "target_books": 1,
            "chapters_per_book": 3,
            "series_title": "The Knotty Buoy",
        },
        base_dir=tmp_path,
        llm=FakePremiseLLM(_payload()),
    )

    assert result["series_id"] == "knotty-buoy"
    assert (tmp_path / "library" / "series" / "knotty-buoy" / "series_plan.json").exists()


def _payload():
    return {
        "series_shape": {
            "target_books": 1,
            "book_length_mode": "tight",
            "chapters_per_book": 3,
            "arc_style": "escalating_floor_survival",
            "series_title": "The Knotty Buoy",
            "series_promise": "A retired couple survives cosmic dungeon nonsense with union logic.",
            "endgame_direction": "The System Architects are forced into arbitration.",
            "power_curve": "logarithmic",
            "series_mysteries": ["System Architects grievance"],
        },
        "series_arc": [
            {
                "book": 1,
                "role": "Origin and first floor survival",
                "major_change": "Edward and Kelli accept the catamaran is now a base.",
                "power_ceiling": "level 10",
                "chapter_count": 3,
                "arc_style": "escalating_floor_survival",
                "must_resolve": ["first floor boss"],
                "must_preserve": ["System Architects grievance"],
                "character_targets": {"Edward Marsh": "acts before complaining stops working"},
                "faction_targets": ["Gallowgate faction"],
                "floor_range": [1, 2],
            }
        ],
        "book_outlines": {
            "1": [
                {
                    "chapter": 1,
                    "phase": "The Drop",
                    "title": "Out of the Atlantic",
                    "premise": "The ocean folds and the catamaran drops into the dungeon.",
                    "ends_on": "Edward tries to close the System notification.",
                    "character_focus": ["Edward Marsh", "Kelli Marsh"],
                    "introduces": ["The Knotty Buoy"],
                    "resolves": [],
                    "must_not_use": ["System Architects grievance"],
                },
                {
                    "chapter": 2,
                    "phase": "The Drop",
                    "title": "The Familiar's First Words",
                    "premise": "Pedro becomes an eldritch familiar.",
                    "ends_on": "Pedro liquefies a jellyfish with a labor-cost insult.",
                    "character_focus": ["Kelli Marsh", "Pedro"],
                    "introduces": ["Pedro magic"],
                    "resolves": [],
                    "must_not_use": ["System Architects grievance"],
                },
                {
                    "chapter": 3,
                    "phase": "The Loot",
                    "title": "Decompression",
                    "premise": "The System rewards them for unauthorized demolition.",
                    "ends_on": "Edward says they need a bigger bilge pump.",
                    "character_focus": ["Edward Marsh", "Pedro"],
                    "introduces": ["Floor 2"],
                    "resolves": ["first floor boss"],
                    "must_not_use": [],
                },
            ]
        },
        "story_bible": {
            "series_id": "knotty-buoy",
            "premise": "A retired South Jersey couple survives a dungeon on a catamaran.",
            "never_contradict_facts": ["The Knotty Buoy is a mobile guild hall"],
            "characters": {
                "Edward Marsh": {
                    "name": "Edward Marsh",
                    "voice_rules": ["Gruff South Jersey pragmatism under cosmic pressure."],
                    "equipped_gear": ["rusted crowbar"],
                }
            },
        },
        "voice_cards": {
            "series_id": "knotty-buoy",
            "cards": {
                "Pedro": {
                    "name": "Pedro",
                    "roles": ["PEDRO"],
                    "humor_modes": ["construction phrases become psychic debuffs"],
                }
            },
        },
        "continuity_ledger": {
            "series_id": "knotty-buoy",
            "running_gags": [
                {
                    "text": "Edward treats cosmic apocalypse like a code inspection.",
                    "chapter": 1,
                    "characters": ["Edward Marsh"],
                    "tags": ["system"],
                }
            ],
        },
        "emotional_arcs": {
            "series_id": "knotty-buoy",
            "characters": {
                "Edward Marsh": {
                    "character": "Edward Marsh",
                    "wound": "Retirement did not fix the marriage.",
                    "current_coping_mode": "repairs the boat instead of talking",
                    "relationships": {"Kelli Marsh": "brittle loyalty"},
                }
            },
        },
        "world_register": {
            "series_id": "knotty-buoy",
            "locations": [
                {
                    "name": "The Knotty Buoy",
                    "detail": "catamaran mapped as a mobile guild hall",
                    "floor": 1,
                }
            ],
            "entity_ecology": [
                {
                    "entity": "Barnacle Mimics",
                    "detail": "eat fiberglass hulls",
                    "floor": 1,
                    "location": "coral shelf",
                }
            ],
        },
        "foreshadow_ledger": {
            "series_id": "knotty-buoy",
            "planted": [
                {
                    "detail": "The System Architects notice unauthorized demolition.",
                    "planted_book": 1,
                    "planted_chapter": 3,
                    "payoff_book": 2,
                    "intended_payoff_start": 4,
                    "intended_payoff_end": 8,
                    "mystery": "System Architects grievance",
                }
            ],
        },
    }
