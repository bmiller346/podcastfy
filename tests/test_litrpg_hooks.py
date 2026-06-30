from podcastfy.litrpg.hooks import build_hook_context
from podcastfy.litrpg.hooks import build_hook_contract
from podcastfy.litrpg.hooks import format_ending_hook_obligations
from podcastfy.litrpg.hooks import format_mystery_lock
from podcastfy.litrpg.hooks import hook_type_for_contract


def test_hook_type_tracks_tempo_and_phase():
    assert hook_type_for_contract({"phase": "The Apex", "tension": 9}) == "action_cliffhanger"
    assert hook_type_for_contract({"phase": "The Bivouac", "tension": 2}) == "tonal_reframe"
    assert hook_type_for_contract({"phase": "The Setback", "tension": 5}) == "emotional_cost"
    assert hook_type_for_contract({"phase": "Rules Discovery", "tension": 5}) == "rules_revelation"
    assert hook_type_for_contract({"phase": "Guild Reputation", "tension": 5}) == "social_faction_consequence"
    assert hook_type_for_contract({"phase": "Plan Betrayal", "tension": 5}) == "plan_reversal"


def test_hook_context_carries_prior_chapter_obligation():
    context = build_hook_context(
        contract={"phase": "The Bivouac", "tension": 2},
        previous_hook_context="The elevator opened with no one inside.",
    )

    assert "Hook Engine" in context
    assert "tonal_reframe" in context
    assert "The elevator opened with no one inside." in context


def test_hook_contract_formats_immediate_cliffhanger_obligations():
    hook = build_hook_contract(
        contract={
            "hook_type": "action_cliffhanger",
            "last_image": "The vending machine lunges with its coin slot open.",
            "open_question": "Who paid it to hunt Edward?",
            "implied_cost": "Edward must spend his last token or lose Kelli's trail.",
        }
    )
    formatted = format_ending_hook_obligations(hook)

    assert hook.ending_hook_type == "action_cliffhanger"
    assert hook.reveal_timing == "immediate"
    assert "immediate cliffhanger" in formatted
    assert "The vending machine lunges" in formatted
    assert "Who paid it to hunt Edward?" in formatted
    assert "Edward must spend his last token" in formatted
    assert "Open the next chapter inside the unresolved danger" in formatted


def test_hook_contract_formats_long_arc_mystery_lock_without_payoff():
    hook = build_hook_contract(
        contract={
            "hook_type": "quiet_dread",
            "reveal_timing": "long_arc",
            "last_image": "Pedro's receipt prints a name nobody said aloud.",
            "mystery_lock": {
                "question": "Why can Pedro's phrases alter system rules?",
                "locked_until": "Chapter 24",
                "forbidden_payoff": "Do not reveal Pedro's source or name the sponsor yet.",
            },
        }
    )
    formatted = format_ending_hook_obligations(hook)
    lock = format_mystery_lock(hook)

    assert hook.reveal_timing == "long_arc"
    assert "long-arc mystery plant" in formatted
    assert "Carry the mystery forward without paying it off" in formatted
    assert "Why can Pedro's phrases alter system rules?" in lock
    assert "Locked until: Chapter 24" in lock
    assert "Do not reveal Pedro's source" in lock
