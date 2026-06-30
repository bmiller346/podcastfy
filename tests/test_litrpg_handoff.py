import json

from podcastfy.litrpg.effect_log import append_effect_log_entry
from podcastfy.litrpg.effect_log import build_effect_log_entry
from podcastfy.litrpg.effect_log import effect_log_path
from podcastfy.litrpg.handoff import generate_book_handoff


def test_generate_book_handoff_contains_deterministic_sections_and_entries(tmp_path):
    series_root = tmp_path / "series" / "paper-cuts"
    book_root = series_root / "book_1"
    quarantine_root = book_root / "quarantine"
    quarantine_root.mkdir(parents=True)

    (series_root / "series_plan.json").write_text(
        json.dumps(
            {
                "series_title": "Paper Cuts",
                "series_mysteries": ["HR System origin"],
            }
        ),
        encoding="utf-8",
    )
    (book_root / "book_plan.json").write_text(
        json.dumps(
            {
                "role": "First floor survival",
                "power_ceiling": "level 10",
                "must_preserve": ["Grand Dredger identity"],
            }
        ),
        encoding="utf-8",
    )
    (book_root / "chapter_outline.json").write_text(
        json.dumps([{"chapter": 1, "summary": "The copier bites back."}]),
        encoding="utf-8",
    )
    (book_root / "chapter_001.json").write_text(
        json.dumps(
            {
                "chapter": {
                    "number": 1,
                    "title": "The Copier Has Teeth",
                    "scarcity_registry": {
                        "items": [{"name": "Executive floor door"}],
                    },
                },
                "render": {"ready": True},
                "hook_review": "Open Chapter 2 on the toner spill.",
                "scarcity_audit": {"spent_mysteries": ["Copier hunger"]},
                "visual_state_update": "Edward's sleeve is shredded.",
                "render_feedback": [
                    {
                        "segment_id": "chapter_001_part_001",
                        "attempt": 1,
                        "score": 0.44,
                        "verdict": "needs_review",
                        "human_review_required": True,
                    },
                    {
                        "segment_id": "chapter_001_part_002",
                        "attempt": 1,
                        "score": 0.91,
                        "verdict": "accepted",
                        "human_review_required": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (quarantine_root / "chapter_002_attempt_001.json").write_text(
        json.dumps(
            {
                "status": "quarantined",
                "chapter_number": 2,
                "attempt": 1,
                "reason": "scarcity_audit_failed",
                "violation_notes": ["Named the Grand Dredger too early"],
                "rewrite_instruction": "Remove the explicit identity reveal.",
                "scarcity_audit": {"spent_mysteries": ["Grand Dredger identity"]},
            }
        ),
        encoding="utf-8",
    )
    append_effect_log_entry(
        effect_log_path(tmp_path, "paper-cuts"),
        build_effect_log_entry(
            series_id="paper-cuts",
            book_number=1,
            chapter_number=1,
            stage="chapter_generation",
            input_payload={"chapter": 1},
            output_payload={"status": "committed"},
            provider="fake",
            model="unit",
        ),
    )

    path = generate_book_handoff(tmp_path, "paper-cuts", 1)
    text = path.read_text(encoding="utf-8")

    assert path == book_root / "HANDOFF.md"
    assert "## Book status" in text
    assert "## Approved chapters" in text
    assert "Chapter 1: The Copier Has Teeth" in text
    assert "Named the Grand Dredger too early" in text
    assert "HR System origin" in text
    assert "Copier hunger" in text
    assert "Edward's sleeve is shredded" in text
    assert "## Render feedback" in text
    assert "Score range: 0.44-0.91; average 0.68" in text
    assert "chapter_001_part_001 score 0.44 verdict needs_review" in text
    assert "chapter_generation: committed (fake unit)" in text
    assert "Fix Chapter 2 quarantine" in text


def test_handoff_recommends_audio_review_when_feedback_requires_it(tmp_path):
    series_root = tmp_path / "series" / "paper-cuts"
    book_root = series_root / "book_1"
    book_root.mkdir(parents=True)
    (series_root / "series_plan.json").write_text(
        json.dumps({"series_title": "Paper Cuts"}),
        encoding="utf-8",
    )
    (book_root / "book_plan.json").write_text(json.dumps({}), encoding="utf-8")
    (book_root / "chapter_outline.json").write_text(json.dumps([{"chapter": 2}]), encoding="utf-8")
    (book_root / "chapter_001.json").write_text(
        json.dumps(
            {
                "chapter": {"number": 1, "title": "Rendered"},
                "render": {"ready": True},
                "render_feedback": [
                    {
                        "segment_id": "chapter_001_part_001",
                        "attempt": 1,
                        "score": 0.99,
                        "verdict": "accepted",
                        "human_review_required": False,
                    },
                    {
                        "segment_id": "chapter_001_part_002",
                        "attempt": 1,
                        "score": 0.0,
                        "verdict": "directive_invalid",
                        "human_review_required": True,
                        "directive_valid": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    path = generate_book_handoff(tmp_path, "paper-cuts", 1)
    text = path.read_text(encoding="utf-8")

    assert "Invalid directives:" in text
    assert "chapter_001_part_002 score 0.00 verdict directive_invalid" in text
    assert "Review audio for Chapter 1 chapter_001_part_002" in text


def test_handoff_does_not_treat_high_score_feedback_as_blocker(tmp_path):
    series_root = tmp_path / "series" / "paper-cuts"
    book_root = series_root / "book_1"
    book_root.mkdir(parents=True)
    (series_root / "series_plan.json").write_text(json.dumps({}), encoding="utf-8")
    (book_root / "book_plan.json").write_text(json.dumps({}), encoding="utf-8")
    (book_root / "chapter_outline.json").write_text(json.dumps([{"chapter": 2}]), encoding="utf-8")
    (book_root / "chapter_001.json").write_text(
        json.dumps(
            {
                "chapter": {"number": 1, "title": "Rendered"},
                "render_feedback": [
                    {
                        "segment_id": "chapter_001_part_001",
                        "attempt": 1,
                        "score": 0.96,
                        "verdict": "accepted",
                        "human_review_required": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    path = generate_book_handoff(tmp_path, "paper-cuts", 1)
    text = path.read_text(encoding="utf-8")

    assert "All recorded audio feedback is accepted." in text
    assert "Prepare Chapter 2" in text
