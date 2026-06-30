import json

from podcastfy.litrpg.chapter_contract_integrator import assemble_chapter_contract
from podcastfy.litrpg.chapter_contract_integrator import format_integrated_chapter_context
from podcastfy.litrpg.premise_intake import build_premise_intake_prompt
from podcastfy.litrpg.premise_intake import save_premise_intake_payload
from podcastfy.litrpg.promise_forge import build_hook_brief_prompt
from podcastfy.litrpg.promise_forge import build_promise_forge_prompt
from podcastfy.litrpg.promise_forge import format_promise_forge_context
from podcastfy.litrpg.promise_forge import validate_promise_forge_specificity
from podcastfy.litrpg.series_architect import SeriesShape
from podcastfy.litrpg.series_architect import bootstrap_series
from podcastfy.litrpg.series_architect import load_series_shape


def test_series_shape_round_trips_promise_forge_through_series_plan(tmp_path):
    forge = _promise_forge()

    bootstrap_series(
        storage_dir=tmp_path,
        series_id="knotty-buoy",
        shape=SeriesShape(
            target_books=1,
            chapters_per_book=3,
            series_title="The Knotty Buoy",
            promise_forge=forge,
        ),
    )

    root = tmp_path / "series" / "knotty-buoy"
    stored = json.loads((root / "series_plan.json").read_text(encoding="utf-8"))
    loaded = load_series_shape(tmp_path, "knotty-buoy")

    assert stored["promise_forge"]["founding_injustice"] == forge["founding_injustice"]
    assert stored["series_promise"] == forge["series_promise"]
    assert loaded.promise_forge["reader_buy_button_image"] == forge["reader_buy_button_image"]
    assert loaded.series_promise == forge["series_promise"]
    assert not (root / "promise_forge.json").exists()


def test_save_premise_intake_payload_preserves_series_shape_promise_forge(tmp_path):
    forge = _promise_forge()

    result = save_premise_intake_payload(
        storage_dir=tmp_path,
        series_id="knotty-buoy",
        payload={
            "series_shape": {
                "series_title": "The Knotty Buoy",
                "chapters_per_book": 1,
                "series_promise": "",
                "promise_forge": forge,
            }
        },
    )

    loaded = load_series_shape(tmp_path, "knotty-buoy")
    stored = json.loads((tmp_path / "series" / "knotty-buoy" / "series_plan.json").read_text(encoding="utf-8"))

    assert loaded.promise_forge["originality_locks"] == forge["originality_locks"]
    assert stored["series_promise"] == forge["series_promise"]
    assert any(path.endswith("series_plan.json") for path in result.written_files)
    assert not any(path.endswith("promise_forge.json") for path in result.written_files)
    assert not (tmp_path / "series" / "knotty-buoy" / "promise_forge.json").exists()


def test_format_promise_forge_context_is_compact_source_labeled_and_keeps_originality_locks():
    context = format_promise_forge_context(_promise_forge())

    assert context.startswith("[promise_forge]")
    assert len(context.splitlines()) <= 9
    assert "founding injustice:" in context
    assert "originality locks:" in context
    assert "do not replicate DCC's comedic cadence" in context
    assert "{" not in context


def test_generic_founding_injustice_fails_specificity_validation():
    result = validate_promise_forge_specificity(
        promise_forge={
            "founding_injustice": "The protagonist is forced to accept responsibility.",
            "permanent_constraint": "The dungeon follows them.",
            "reader_buy_button_image": "A hero sees a system window.",
        },
        raw_premise="Kelli Marsh sails Sophie II with Pedro and Edward.",
    )

    assert result["passed"] is False
    assert any("generic" in issue for issue in result["issues"])


def test_premise_specific_founding_injustice_passes_specificity_validation():
    result = validate_promise_forge_specificity(
        promise_forge=_promise_forge(),
        raw_premise=(
            "Kelli Marsh, Edward Marsh, Pedro, and Sophie II are trapped after "
            "Kelli's old chore-board authority becomes binding party commands."
        ),
    )

    assert result["passed"] is True
    assert "founding_injustice" in result["matched_anchors"]


def test_no_promise_forge_json_created_by_premise_intake(tmp_path):
    save_premise_intake_payload(
        storage_dir=tmp_path,
        series_id="no-extra-file",
        payload={
            "series_shape": {
                "series_title": "No Extra File",
                "chapters_per_book": 1,
                "promise_forge": _promise_forge(),
            }
        },
    )

    assert list((tmp_path / "series" / "no-extra-file").glob("promise_forge.json")) == []


def test_hook_brief_and_promise_forge_schemas_are_present_in_prompts():
    hook_prompt = build_hook_brief_prompt(raw_context="Kelli, Sophie II, and chore-board authority.")
    forge_prompt = build_promise_forge_prompt(raw_premise="Kelli, Sophie II, and chore-board authority.")
    intake_prompt = build_premise_intake_prompt(
        premise="Kelli, Sophie II, and chore-board authority.",
        series_id="knotty-buoy",
    )

    for key in (
        "logline",
        "back_cover_seed",
        "founding_injustice_candidate",
        "permanent_constraint_candidate",
        "specificity_anchors",
        "do_not_smooth_out",
    ):
        assert f'"{key}"' in hook_prompt
    for key in (
        "founding_injustice",
        "permanent_constraint",
        "series_promise",
        "must_not_become",
        "originality_locks",
        "source_brief",
    ):
        assert f'"{key}"' in forge_prompt
    assert "series_shape.promise_forge" in intake_prompt
    assert "must not imitate DCC" in intake_prompt


def test_chapter_contract_integrator_includes_promise_forge_context():
    integrated = assemble_chapter_contract(
        chapter_contract={"book": 1, "chapter": 1, "promise_forge": _promise_forge()},
    )
    context = format_integrated_chapter_context(integrated)

    assert "[promise_forge]" in context
    assert "originality locks:" in context


def _promise_forge():
    return {
        "founding_injustice": "The system turns Kelli's old chore-board authority into binding party commands aboard Sophie II.",
        "permanent_constraint": "Kelli's household command habits become enforceable raid orders whenever Sophie II is registered as home base.",
        "comedic_signal": "Old-married chore arguments become lethal system bureaucracy.",
        "series_promise": "A retired family crew survives by weaponizing unfair domestic paperwork.",
        "reader_buy_button_image": "Kelli points at Sophie II's chore board and the dungeon obeys before Edward can object.",
        "must_recur": ["Sophie II's chore board", "old-married command friction"],
        "must_not_become": ["generic dungeon survival", "family drama with stats pasted on"],
        "originality_locks": [
            "do not use DCC character names, class names, faction names, or system voice",
            "do not replicate DCC's comedic cadence",
            "the founding injustice must come from this family and boat premise",
        ],
        "source_brief": {
            "specificity_anchors": ["Kelli", "Sophie II", "chore-board authority"],
            "do_not_smooth_out": ["old chores become binding commands"],
        },
    }
