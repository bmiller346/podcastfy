from podcastfy.litrpg.qa import parse_part_qa_artifacts


def test_parse_part_qa_artifacts_parses_json_scores_and_verdicts():
    parsed = parse_part_qa_artifacts(
        director_tags='{"summary":"tense","cues":[{"role":"HERO"}]}',
        mechanics_audit='{"verdict":"pass","blocking_issues":[],"fixes":[]}',
        tonal_audit=(
            '{"stakes_seriousness":8,"absurdity_pressure":6,'
            '"verdict":"revise","fixes":["sharpen the consequence"]}'
        ),
        showmanship_audit=(
            '{"scores":{"crowd_engagement":9,"brutality":7,"creativity":8,'
            '"humiliation":5,"meme_potential":6,"sponsor_appeal":4},'
            '"verdict":"pass"}'
        ),
    )

    assert parsed["director"]["summary"] == "tense"
    assert parsed["mechanics"]["verdict"] == "pass"
    assert parsed["tonal"]["scores"] == {
        "stakes_seriousness": 8,
        "absurdity_pressure": 6,
    }
    assert parsed["tonal"]["verdict"] == "revise"
    assert parsed["showmanship"]["scores"]["sponsor_appeal"] == 4


def test_parse_part_qa_artifacts_parses_non_json_audit_text():
    parsed = parse_part_qa_artifacts(
        mechanics_audit=(
            "Verdict: BLOCK\n"
            "blocking issues: XP total jumps without an award; potion consumed twice\n"
            "fixes: add the missing SYSTEM award"
        ),
        tonal_audit=(
            "stakes seriousness 7\n"
            "absurdity-pressure: 9\n"
            "verdict - pass"
        ),
        showmanship_audit=(
            "crowd engagement: 8\n"
            "brutality 6\n"
            "creativity=7\n"
            "humiliation: 4\n"
            "meme potential: 5\n"
            "sponsor appeal 3\n"
            "verdict: revise"
        ),
    )

    assert parsed["mechanics"]["verdict"] == "block"
    assert "XP total jumps" in parsed["mechanics"]["blocking_issues"][0]
    assert parsed["tonal"]["scores"]["stakes_seriousness"] == 7
    assert parsed["tonal"]["scores"]["absurdity_pressure"] == 9
    assert parsed["showmanship"]["scores"] == {
        "crowd_engagement": 8,
        "brutality": 6,
        "creativity": 7,
        "humiliation": 4,
        "meme_potential": 5,
        "sponsor_appeal": 3,
    }
    assert parsed["showmanship"]["verdict"] == "revise"
