import json

from podcastfy.litrpg.harness import check_harness_gate
from podcastfy.litrpg.harness import default_harness_config
from podcastfy.litrpg.harness import estimate_stage_cost
from podcastfy.litrpg.harness import load_harness_config


def test_default_harness_config_has_expected_stages():
    config = default_harness_config()

    assert config["schema_version"] == 1
    assert config["stages"]["chapter_generation"]["requires_human_approval"] is True
    assert config["stages"]["chapter_result_write"]["requires_human_approval"] is False
    assert config["stages"]["audio_render"]["requires_human_approval"] is True


def test_load_harness_config_prefers_book_then_series_then_default(tmp_path):
    series_root = tmp_path / "series" / "paper-cuts"
    book_root = series_root / "book_2"
    book_root.mkdir(parents=True)
    series_root.mkdir(exist_ok=True)
    (series_root / "harness_config.json").write_text(
        json.dumps({"stages": {"chapter_generation": {"requires_human_approval": False}}}),
        encoding="utf-8",
    )
    (book_root / "harness_config.json").write_text(
        json.dumps({"stages": {"chapter_generation": {"requires_human_approval": True}}}),
        encoding="utf-8",
    )

    assert load_harness_config(tmp_path, "paper-cuts", 2)["stages"]["chapter_generation"][
        "requires_human_approval"
    ] is True
    assert load_harness_config(tmp_path, "paper-cuts", 1)["stages"]["chapter_generation"][
        "requires_human_approval"
    ] is False
    assert load_harness_config(tmp_path, "missing")["stages"]["audio_render"][
        "requires_human_approval"
    ] is True


def test_estimate_stage_cost_is_nonzero_for_expensive_stages():
    chapter = estimate_stage_cost("chapter_generation", {"target_minutes": 30})
    audio = estimate_stage_cost(
        "audio_render",
        {"target_minutes": 30},
        {"cost_per_minute_usd": 0.02},
    )

    assert chapter > 0
    assert audio == 0.6
    assert estimate_stage_cost("chapter_result_write", {}) == 0.0


def test_check_harness_gate_blocks_until_approved():
    config = {
        "stages": {
            "chapter_generation": {
                "requires_human_approval": True,
                "estimated_cost_usd": 0.25,
            }
        }
    }

    blocked = check_harness_gate("chapter_generation", {}, config, approved=False)
    allowed = check_harness_gate("chapter_generation", {}, config, approved=True)

    assert blocked.allowed is False
    assert blocked.requires_human_approval is True
    assert blocked.estimated_cost_usd == 0.25
    assert "requires human approval" in blocked.reason
    assert allowed.allowed is True
    assert allowed.approved is True
