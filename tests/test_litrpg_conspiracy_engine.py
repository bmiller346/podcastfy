from podcastfy.litrpg.conspiracy_engine import ConspiracyEngine
from podcastfy.litrpg.conspiracy_engine import build_conspiracy_chapter_context
from podcastfy.litrpg.conspiracy_engine import save_conspiracy_engine
from podcastfy.litrpg.series_architect import BookPlan
from podcastfy.litrpg.series_architect import SeriesArchitect
from podcastfy.litrpg.series_architect import SeriesShape
from podcastfy.litrpg.series_architect import bootstrap_series
from podcastfy.litrpg.series_architect import format_chapter_contract_context
from podcastfy.litrpg.world_state import build_scene_brief


def _conspiracy_state():
    return {
        "truth_document": {
            "classification": "EYES_ONLY - never inject into prose generation context",
            "actual_reality": {
                "system_true_architect": "escaped crawlers built the trap",
                "who_knows_what": {
                    "hero": [
                        "knows: floors are manufactured",
                        "does_not_know: sponsor profit mechanism",
                    ],
                    "reader": ["suspects: system is not neutral"],
                },
            },
        },
        "revelation_ladder": {
            "system_anomaly": {
                "truth": "escaped crawlers built the trap",
                "current_reader_knowledge": "something is wrong with the system",
                "next_hint_window": "ch_18_to_22",
                "hint_type_next": "environmental anomaly",
                "earliest_partial_reveal": "book_3",
                "full_reveal": "book_6",
                "DO_NOT_ACCELERATE": True,
            }
        },
        "reader_position": {
            "confirmed_knows": ["floors are manufactured"],
            "strongly_suspects": ["system is not neutral"],
            "correctly_suspects_but_has_wrong_reason": ["sponsor is evil"],
            "must_not_know_yet": ["who built the system"],
        },
        "factions": {
            "corporate_equivalent": {
                "name": "GlowCo",
                "true_goal": "TRUTH_DOC_ONLY: farm failed exits",
                "apparent_goal": "profit from dungeon broadcast rights",
                "operational_rules": [
                    "cannot directly intervene in crawler decisions",
                    "profit requires crawlers to reach floor 6",
                ],
                "vulnerabilities": ["unionized crawlers break the pricing model"],
                "current_moves": [
                    {"book": 1, "action": "establish sponsor relationships", "carl_awareness": "none"}
                ],
            }
        },
    }


def test_conspiracy_context_never_exposes_truth_document():
    context = build_conspiracy_chapter_context(
        _conspiracy_state(),
        book_number=1,
        chapter_number=20,
        pov_character="hero",
    )

    assert "truth_document" not in context
    assert context["character_knowledge"]["knowledge"] == [
        "knows: floors are manufactured",
        "does_not_know: sponsor profit mechanism",
    ]
    assert context["allowed_conspiracy_hints"][0]["hint_type"] == "environmental anomaly"
    assert "escaped crawlers built the trap" not in str(context)
    assert "true_goal" not in context["faction_constraints"]["corporate_equivalent"]
    assert "reader must not confirm: who built the system" in context["forbidden_revelations"]


def test_series_architect_queries_standalone_conspiracy_engine(tmp_path):
    bootstrap_series(
        storage_dir=tmp_path,
        series_id="no-fixed-address",
        shape=SeriesShape(target_books=6, chapters_per_book=24, series_mysteries=["system_anomaly"]),
        series_arc=[
            BookPlan(
                book=1,
                role="First floor survival",
                major_change="They survive the tutorial.",
                power_ceiling="level 8",
                chapter_count=24,
                arc_style="escalating_floor_survival",
                must_preserve=["system_anomaly"],
            )
        ],
    )
    save_conspiracy_engine(tmp_path, "no-fixed-address", _conspiracy_state())

    contract = SeriesArchitect(tmp_path, "no-fixed-address").get_chapter_contract(
        book_number=1,
        chapter_number=20,
    )
    context = format_chapter_contract_context(contract)

    assert contract["conspiracy"]["allowed_conspiracy_hints"][0]["mystery_id"] == "system_anomaly"
    assert "escaped crawlers built the trap" not in str(contract)
    assert "Allowed conspiracy hints" in context
    assert "Forbidden conspiracy revelations" in context


def test_scene_brief_adds_reader_position_to_forbidden_revelations(tmp_path):
    engine = ConspiracyEngine(tmp_path, "paper-cuts")
    engine.write(_conspiracy_state())
    conspiracy_context = engine.get_chapter_context(book_number=1, chapter_number=4)

    brief = build_scene_brief(
        world_state={"series_id": "paper-cuts"},
        chapter_contract={"conspiracy": conspiracy_context},
    )

    assert "reader must not confirm: who built the system" in brief.to_dict()["forbidden"]
