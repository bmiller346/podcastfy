from podcastfy.litrpg.rhythm import build_prose_rhythm_prompt
from podcastfy.litrpg.rhythm import build_reader_proxy_prompt
from podcastfy.litrpg.rhythm import classify_target_rhythm
from podcastfy.litrpg.rhythm import parse_verdict_and_scores


def test_classify_target_rhythm_uses_contract_tempo_values():
    target = classify_target_rhythm(
        {
            "tension": 9,
            "absurdity": 2,
            "creativity": 4,
        }
    )

    assert target.tempo == "fast"
    assert "short punchy sentences" in target.sentence_rhythm
    assert "never deflate injury or stakes" in target.humor_timing
    assert "lean paragraphs" in target.density_length_discipline


def test_prose_rhythm_prompt_includes_tempo_values():
    prompt = build_prose_rhythm_prompt(
        "Paragraph one.\n\nParagraph two.",
        {
            "tempo": "slow",
            "sentence_rhythm": "long-short-long pressure waves",
            "humor_timing": "deadpan button after dread",
            "density_length_discipline": "180 words max per paragraph",
        },
        "LitRPG",
    )

    assert '"tempo": "slow"' in prompt
    assert "long-short-long pressure waves" in prompt
    assert "deadpan button after dread" in prompt
    assert "180 words max per paragraph" in prompt
    assert "paragraph_fixes" in prompt


def test_reader_proxy_prompt_requires_dcc_litrpg_lateral_intelligence():
    prompt = build_reader_proxy_prompt(
        "<HERO>I spend the cursed coupon.</HERO>",
        {"tension": 8, "creativity": 8, "absurdity": 8},
        "LitRPG",
    )

    assert "DCC/LitRPG lateral intelligence" in prompt
    assert "established mechanics, inventory, spatial rules" in prompt
    assert "cooldowns, or system loopholes" in prompt
    assert "binge-worthiness" in prompt
    assert "next-chapter desire" in prompt


def test_reader_proxy_prompt_uses_generic_story_wording_for_non_litrpg():
    prompt = build_reader_proxy_prompt(
        "The baker found the receipt in the flour bin.",
        {"tension": 4, "creativity": 6, "absurdity": 3},
        "cozy mystery",
    )

    assert "cozy mystery story chapter" in prompt
    assert "generic story cleverness and lateral intelligence" in prompt
    assert "generic story logic for cozy mystery" in prompt
    assert "game mechanics" in prompt
    assert "DCC/LitRPG" not in prompt
    assert "XP" not in prompt
    assert "loot" not in prompt


def test_parse_verdict_and_scores_accepts_embedded_json():
    parsed = parse_verdict_and_scores(
        'Result:\n{"verdict": "REVISE", "scores": {"tempo_match": "7/10", "flow": 8}}'
    )

    assert parsed == {
        "verdict": "revise",
        "scores": {"tempo_match": 7, "flow": 8},
    }
