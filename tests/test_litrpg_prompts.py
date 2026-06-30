from podcastfy.litrpg.prompts import build_audio_script_prompt
from podcastfy.litrpg.prompts import build_series_anchor_block


def test_series_anchor_block_compresses_plans_locks_and_scarcity():
    block = build_series_anchor_block(
        series_plan={
            "series_title": "The Knotty Buoy",
            "series_mysteries": ["Grand Dredger patron"],
        },
        book_plan={
            "book": 1,
            "role": "Floor 1 survival",
            "power_ceiling": "Level 10 and boat repairs only",
            "must_preserve": ["Gallowgate leverage"],
        },
        chapter_contract={
            "chapter": 3,
            "phase": "The Setback",
            "tension": 7,
            "must_not_spend": ["Kelli's exact location"],
        },
        allowed_hints=["Receipt language can look older than the System."],
        reveal_locks=["Kelli's exact location: reveal book 2, payoff book 3"],
        scarcity_constraints=["Tokens are finite until trade earns more."],
    )

    assert "Series Anchor Block:" in block
    assert "The Knotty Buoy" in block
    assert "Floor 1 survival" in block
    assert "The Setback / 7" in block
    assert "Level 10 and boat repairs only" in block
    assert "Series mysteries: Grand Dredger patron; Gallowgate leverage" in block
    assert "Forbidden now:" in block
    assert "Kelli's exact location" in block
    assert "Receipt language can look older than the System." in block
    assert "hints may foreshadow locked material" in block


def test_legacy_audio_script_prompt_includes_anchor_and_policy_blocks():
    prompt = build_audio_script_prompt(
        outline="Scene 1: Edward bargains with a hostile vending machine.",
        episode_number=1,
        minutes=12,
        tone="bureaucratic dread comedy",
        series_anchor_block="Series Anchor Block:\n- Forbidden now: Grand Dredger patron",
    )

    assert "Series Anchor Block" in prompt
    assert "Grand Dredger patron" in prompt
    assert "Scarcity lock" in prompt
    assert "Mystery lock discipline" in prompt
    assert "TTS-friendly role block constraints" in prompt
