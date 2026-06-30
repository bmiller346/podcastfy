import json

from podcastfy.litrpg.bible import load_story_bible
from podcastfy.litrpg.continuity import load_continuity_ledger, load_world_register
from podcastfy.litrpg.foreshadowing import load_foreshadow_ledger
from podcastfy.litrpg.premise_intake import build_premise_intake_prompt
from podcastfy.litrpg.premise_intake import build_premise_intake_repair_prompt
from podcastfy.litrpg.premise_intake import extract_premise_intake_json
from podcastfy.litrpg.premise_intake import run_premise_intake
from podcastfy.litrpg.premise_intake import save_premise_intake_payload
from podcastfy.litrpg.premise_intake import validate_premise_intake_payload
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


class SequencePremiseLLM:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        payload = self.payloads.pop(0)
        return "```json\n" + json.dumps(payload) + "\n```"


class RawSequencePremiseLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        return self.outputs.pop(0)


def test_extract_premise_intake_json_accepts_fenced_output():
    parsed = extract_premise_intake_json('Here:\n```json\n{"series_shape": {"target_books": 1}}\n```')

    assert parsed["series_shape"]["target_books"] == 1


def test_extract_premise_intake_json_accepts_plain_json():
    parsed = extract_premise_intake_json('{"series_shape": {"series_title": "Plain"}}')

    assert parsed["series_shape"]["series_title"] == "Plain"


def test_build_premise_intake_prompt_requires_story_architecture_artifacts():
    prompt = build_premise_intake_prompt(
        premise="Edward, Kelli, Pedro, and The Knotty Buoy face Gallowgate.",
        series_id="knotty-buoy",
        chapters_per_book=30,
        series_title="The Knotty Buoy",
    )

    assert "Return ONLY a JSON object" in prompt
    assert "voice_cards: object compatible with VoiceCardDeck" in prompt
    assert "diction, sentence rhythm, taboo phrases" in prompt
    assert "Visual continuity is mandatory" in prompt
    assert "dynamic degradation" in prompt
    assert "use ends_on for the final image" in prompt
    assert "foreshadow_ledger plants" in prompt
    assert "payoff windows" in prompt
    assert "faction agendas" in prompt
    assert "currencies, trade goods, costs, scarcity" in prompt
    assert '"chapters_per_book": 30' in prompt
    assert "Edward, Kelli, Pedro" in prompt


def test_build_premise_intake_repair_prompt_targets_failed_sections():
    prompt = build_premise_intake_repair_prompt(
        premise="Edward, Kelli, Pedro, Sophie II, and Gallowgate.",
        series_id="knotty-buoy",
        chapters_per_book=30,
        validation_error="world_register was empty",
        previous_payload={"world_register": {"locations": []}},
    )

    assert "world_register was empty" in prompt
    assert "full corrected JSON object" in prompt
    assert "Sophie II" in prompt
    assert "vehicle/base mechanics" in prompt


def test_save_premise_intake_payload_repairs_partial_payload(tmp_path):
    result = save_premise_intake_payload(
        storage_dir=tmp_path,
        series_id="partial-series",
        payload={
            "book_outlines": {
                "1": [
                    {
                        "chapter": 1,
                        "title": "First Wake",
                        "premise": "The system message arrives.",
                    }
                ]
            }
        },
        fallback_shape={
            "series_title": "Fallback Title",
            "target_books": 1,
            "chapters_per_book": 1,
            "series_promise": "Fallback promise.",
        },
    )

    contract = SeriesArchitect(tmp_path, "partial-series").get_chapter_contract(
        book_number=1,
        chapter_number=1,
    )

    assert result.series_id == "partial-series"
    assert contract["series_title"] == "Fallback Title"
    assert contract["title"] == "First Wake"
    assert any(path.endswith("series_arc.json") for path in result.written_files)


def test_save_premise_intake_payload_allows_missing_optional_ledgers(tmp_path):
    result = save_premise_intake_payload(
        storage_dir=tmp_path,
        series_id="no-ledgers",
        payload={"series_shape": {"series_title": "No Ledgers", "chapters_per_book": 1}},
    )

    assert (tmp_path / "series" / "no-ledgers" / "series_plan.json").exists()
    assert not (tmp_path / "series" / "no-ledgers" / "continuity_ledger.json").exists()
    assert any(path.endswith("series_plan.json") for path in result.written_files)


def test_save_premise_intake_payload_reports_bad_outline_shape(tmp_path):
    try:
        save_premise_intake_payload(
            storage_dir=tmp_path,
            series_id="bad-outline",
            payload={"book_outlines": {"1": [{"chapter": "two"}]}},
        )
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive clarity.
        raise AssertionError("Expected bad outline to raise")

    assert "book 1 chapter two" in message


def test_save_premise_intake_payload_blocks_series_path_traversal(tmp_path):
    try:
        save_premise_intake_payload(
            storage_dir=tmp_path,
            series_id="../escape",
            payload={"series_shape": {"series_title": "Unsafe"}},
        )
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive clarity.
        raise AssertionError("Expected unsafe series_id to raise")

    assert "storage_dir/series" in message
    assert not (tmp_path / "escape").exists()


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


def test_premise_intake_rejects_sparse_long_context_payload():
    premise = (
        "Edward and Kelli sail Sophie II with Pedro while Gallowgate and the "
        "Grand Dredger turn the dungeon into a maritime debt trap. "
        * 40
    )

    try:
        validate_premise_intake_payload(
            {
                "series_shape": {
                    "series_title": "The Knotty Buoy",
                    "series_promise": "TBD: Convert an unstructured premise dump.",
                },
                "story_bible": {"characters": {}},
                "world_register": {"locations": [], "rules": [], "entity_ecology": []},
            },
            premise=premise,
            chapters_per_book=30,
        )
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive clarity.
        raise AssertionError("Expected sparse long-context intake to fail")

    assert "too sparse or generic" in message
    assert "Edward" in message or "edward" in message
    assert "story_bible" in message


def test_run_premise_intake_repairs_sparse_payload_before_saving(tmp_path):
    sparse_payload = {
        "series_shape": {
            "series_title": "The Knotty Buoy",
            "series_promise": "Generic LitRPG challenges.",
        },
        "story_bible": {"characters": {}},
        "world_register": {
            "locations": [{"name": "Sophie II", "detail": "The boat."}],
            "rules": [],
            "entity_ecology": [],
        },
        "book_outlines": {
            "1": [
                {"chapter": 1, "title": "A", "premise": "A"},
                {"chapter": 2, "title": "B", "premise": "B"},
                {"chapter": 3, "title": "C", "premise": "C"},
            ]
        },
    }
    llm = SequencePremiseLLM([sparse_payload, _payload()])

    result = run_premise_intake(
        storage_dir=tmp_path,
        series_id="knotty-buoy",
        premise=(
            "Edward and Kelli sail Sophie II with Pedro while Gallowgate and the "
            "Grand Dredger turn the dungeon into a maritime debt trap. "
            * 40
        ),
        llm=llm,
        target_books=1,
        chapters_per_book=3,
        series_title="The Knotty Buoy",
    )

    assert [call["stage"] for call in llm.calls] == ["premise_intake", "premise_intake_repair"]
    assert "too sparse or generic" in llm.calls[1]["prompt"]
    assert any(path.endswith("world_register.json") for path in result.written_files)
    assert load_world_register(tmp_path, "knotty-buoy").locations[0].name == "The Knotty Buoy"


def test_run_premise_intake_salvages_sparse_output_after_repair_failure(tmp_path):
    sparse_payload = {
        "series_shape": {
            "series_title": "The Knotty Buoy",
            "series_promise": "Generic LitRPG challenges.",
        },
        "story_bible": {"characters": {}},
        "world_register": {"locations": [], "rules": [], "entity_ecology": [], "economy_anchors": []},
        "book_outlines": {"1": []},
    }
    premise = (
        "Target title: The Knotty Buoy\n"
        "Edward Marsh and Kelli Marsh sail Sophie II with Pedro. Sophie II is named "
        "after Sophie the cockatoo, who died when Kelli overheated pans. Gallowgate "
        "and the Grand Dredger turn the dungeon into a maritime debt trap. Floor 1 "
        "is The Drowned Scaffolding with Barnacle Scrip, OSHA Wraiths, Barnacle "
        "Mimics, and Rebar Gargoyles. The kids are off the boat and become guilt pressure. "
        * 18
    )
    llm = SequencePremiseLLM([sparse_payload, sparse_payload])

    result = run_premise_intake(
        storage_dir=tmp_path,
        series_id="the-knotty-buoy",
        premise=premise,
        llm=llm,
        target_books=1,
        chapters_per_book=30,
        series_title="The Knotty Buoy",
    )

    assert [call["stage"] for call in llm.calls] == ["premise_intake"]
    assert any(path.endswith("story_bible.json") for path in result.written_files)
    assert any(path.endswith("world_register.json") for path in result.written_files)
    bible = load_story_bible(tmp_path, "the-knotty-buoy")
    world = load_world_register(tmp_path, "the-knotty-buoy")
    outline = load_chapter_outline(tmp_path, "the-knotty-buoy", 1)

    assert {"Edward Marsh", "Kelli Marsh", "Pedro"}.issubset(bible.characters)
    assert "Sophie II" in bible.never_contradict_facts[0]
    assert len(world.locations) >= 3
    assert any(entity.entity == "OSHA Wraiths" for entity in world.entity_ecology)
    assert len(outline) == 30
    assert result.payload["_intake_metadata"]["fallback_used"] is True
    assert "Skipped AI repair" in result.payload["_intake_metadata"]["fallback_reason"]


def test_run_premise_intake_salvages_malformed_initial_json(tmp_path):
    llm = RawSequencePremiseLLM(['{"series_shape": {"series_title": "The Knotty Buoy",}}'])

    result = run_premise_intake(
        storage_dir=tmp_path,
        series_id="the-knotty-buoy",
        premise=_long_knotty_seed(),
        llm=llm,
        target_books=1,
        chapters_per_book=30,
        series_title="The Knotty Buoy",
    )

    assert [call["stage"] for call in llm.calls] == ["premise_intake"]
    assert result.payload["_intake_metadata"]["fallback_used"] is True
    assert "malformed" in result.payload["_intake_metadata"]["fallback_reason"]
    assert load_story_bible(tmp_path, "the-knotty-buoy").characters["Edward Marsh"].name == "Edward Marsh"


def test_run_premise_intake_salvages_malformed_repair_json(tmp_path):
    sparse_but_not_empty = {
        "series_shape": {"series_title": "The Knotty Buoy"},
        "story_bible": {"characters": {}},
        "world_register": {
            "locations": [{"name": "Sophie II", "detail": "The boat."}],
            "rules": [],
            "entity_ecology": [],
        },
        "book_outlines": {
            "1": [
                {"chapter": 1, "title": "A", "premise": "A"},
                {"chapter": 2, "title": "B", "premise": "B"},
                {"chapter": 3, "title": "C", "premise": "C"},
            ]
        },
    }
    llm = RawSequencePremiseLLM(
        [
            "```json\n" + json.dumps(sparse_but_not_empty) + "\n```",
            '{"world_register": {"locations": [{"name": "Sophie II"}]',
        ]
    )

    result = run_premise_intake(
        storage_dir=tmp_path,
        series_id="the-knotty-buoy",
        premise=_long_knotty_seed(),
        llm=llm,
        target_books=1,
        chapters_per_book=30,
        series_title="The Knotty Buoy",
    )

    assert [call["stage"] for call in llm.calls] == ["premise_intake", "premise_intake_repair"]
    assert result.payload["_intake_metadata"]["fallback_used"] is True
    assert "repair returned malformed JSON" in result.payload["_intake_metadata"]["fallback_reason"]
    assert any(item.entity == "Gallowgate" for item in load_world_register(tmp_path, "the-knotty-buoy").entity_ecology)


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


def test_premise_intake_prefers_source_text_over_short_premise(tmp_path):
    llm = FakePremiseLLM(_payload())

    run_litrpg_task_data(
        {
            "mode": "premise_intake",
            "series_id": "knotty-buoy",
            "storage_dir": "library",
            "premise": "Short browser summary.",
            "source_text": "Full markdown source with Edward, Kelli, Pedro, Sophie II, and Gallowgate.",
            "target_books": 1,
            "chapters_per_book": 3,
        },
        base_dir=tmp_path,
        llm=llm,
    )

    prompt = llm.calls[0]["prompt"]
    assert "Full markdown source" in prompt
    assert "Short browser summary" not in prompt


def _long_knotty_seed():
    return (
        "Target title: The Knotty Buoy\n"
        "Edward Marsh and Kelli Marsh sail Sophie II with Pedro. Sophie II is named "
        "after Sophie the cockatoo, who died when Kelli overheated pans. Gallowgate "
        "and the Grand Dredger turn the dungeon into a maritime debt trap. Floor 1 "
        "is The Drowned Scaffolding with Barnacle Scrip, OSHA Wraiths, Barnacle "
        "Mimics, and Rebar Gargoyles. The kids are off the boat and become guilt pressure. "
        * 18
    )


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
                },
                "Kelli Marsh": {
                    "name": "Kelli Marsh",
                    "voice_rules": ["Casino-risk clarity with old-married bite."],
                    "relationship_pressure": ["Sophie the cockatoo remains a guilt anchor."],
                },
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
            "rules": [
                {
                    "name": "Mobile Guild Hall Truce",
                    "detail": "The Sophie II is mistakenly protected as a guild hall interior.",
                }
            ],
            "economy_anchors": [
                {
                    "name": "Barnacle Scrip",
                    "detail": "Used for repairs, dungeon epoxy, and maritime fees.",
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
