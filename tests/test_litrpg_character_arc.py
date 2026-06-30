from podcastfy.litrpg.character_arc import CharacterArcEngine
from podcastfy.litrpg.character_arc import build_arc_state_update_prompt
from podcastfy.litrpg.character_arc import build_character_arc_context
from podcastfy.litrpg.character_arc import format_character_arc_context
from podcastfy.litrpg.character_arc import merge_arc_state_delta
from podcastfy.litrpg.continuity import EmotionalArc
from podcastfy.litrpg.continuity import EmotionalArcRegistry
from podcastfy.litrpg.continuity import save_emotional_arcs


def _registry():
    return EmotionalArcRegistry(
        series_id="paper-cuts",
        characters={
            "hero": EmotionalArc(
                character="Hero",
                wound="Believes every promotion is a trap.",
                current_coping_mode="alphabetizes terror",
                relationships={
                    "System": "mutual contempt",
                    "Mara": "trusts her plans, not her optimism",
                },
                last_significant_emotional_event="Admitted the copy room was real.",
            ),
            "mara": EmotionalArc(
                character="Mara",
                wound="Was blamed for the gate collapse.",
                current_coping_mode="dry control",
                relationships={"Hero": "protective irritation"},
            ),
        },
    )


def test_character_arc_context_tracks_pressure_graph_and_locks():
    context = build_character_arc_context(
        _registry(),
        chapter_contract={"character_focus": ["Hero"], "tension": 9},
    )

    assert [item["character"] for item in context["arc_pressure"]] == ["Hero"]
    assert context["arc_pressure"][0]["allowed_shift"] == "stress response may worsen coping mode"
    assert {"source": "Hero", "target": "System", "state": "mutual contempt", "pressure": "conflict pressure"} in context[
        "relationship_graph"
    ]
    assert "Hero: do not resolve wound (Believes every promotion is a trap.)" in context[
        "forbidden_arc_moves"
    ]
    assert "Hero -> System: do not soften conflict without an earned beat" in context[
        "forbidden_arc_moves"
    ]


def test_character_arc_context_allows_explicit_payoff():
    context = build_character_arc_context(
        _registry(),
        chapter_contract={"character_focus": ["Hero"], "resolves": ["Hero wound arc"]},
    )

    assert context["arc_pressure"][0]["allowed_shift"] == "payoff allowed if earned on page"
    assert not any("do not resolve wound" in item for item in context["forbidden_arc_moves"])


def test_character_arc_engine_reads_stored_arcs_and_formats_context(tmp_path):
    save_emotional_arcs(tmp_path, "paper-cuts", _registry())

    context = CharacterArcEngine(tmp_path, "paper-cuts").get_chapter_context(
        chapter_contract={"character_focus": ["Hero"]}
    )
    formatted = format_character_arc_context(context)

    assert "Character arc pressure:" in formatted
    assert "Relationship graph:" in formatted
    assert "Forbidden arc moves:" in formatted
    assert "alphabetizes terror" in formatted


def test_arc_state_update_prompt_and_delta_merge_preserve_existing_arc():
    prompt = build_arc_state_update_prompt(
        final_script="<HERO>I trusted Mara with the badge.</HERO>",
        current_arc_registry=_registry(),
        chapter_contract={"chapter": 3, "character_focus": ["Hero"]},
    )
    merged = merge_arc_state_delta(
        _registry(),
        {
            "character_arc_updates": {
                "Hero": {
                    "character": "Hero",
                    "current_coping_mode": "delegates fear into checklists",
                    "last_significant_emotional_event": "Trusted Mara with the badge.",
                    "relationships": {"Mara": "trusts her under pressure"},
                    "beats": [
                        {
                            "text": "Chose trust over solo control.",
                            "chapter": 3,
                            "characters": ["Hero", "Mara"],
                        }
                    ],
                }
            }
        },
    )

    hero = merged.characters["hero"]
    assert "Output ONLY a JSON object" in prompt
    assert "character_arc_updates" in prompt
    assert "Believes every promotion is a trap" in prompt
    assert hero.wound == "Believes every promotion is a trap."
    assert hero.current_coping_mode == "delegates fear into checklists"
    assert hero.relationships["System"] == "mutual contempt"
    assert hero.relationships["Mara"] == "trusts her under pressure"
    assert hero.last_significant_emotional_event == "Trusted Mara with the badge."
    assert hero.beats[-1].text == "Chose trust over solo control."
