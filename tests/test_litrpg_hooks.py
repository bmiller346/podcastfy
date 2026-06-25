from podcastfy.litrpg.hooks import build_hook_context
from podcastfy.litrpg.hooks import hook_type_for_contract


def test_hook_type_tracks_tempo_and_phase():
    assert hook_type_for_contract({"phase": "The Apex", "tension": 9}) == "action_cliffhanger"
    assert hook_type_for_contract({"phase": "The Bivouac", "tension": 2}) == "tonal_reframe"
    assert hook_type_for_contract({"phase": "The Setback", "tension": 5}) == "emotional_cost"
    assert hook_type_for_contract({"phase": "Exploration", "tension": 5}) == "revelation_question"


def test_hook_context_carries_prior_chapter_obligation():
    context = build_hook_context(
        contract={"phase": "The Bivouac", "tension": 2},
        previous_hook_context="The elevator opened with no one inside.",
    )

    assert "Hook Engine" in context
    assert "tonal_reframe" in context
    assert "The elevator opened with no one inside." in context
