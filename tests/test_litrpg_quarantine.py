import json

from podcastfy.litrpg.quarantine import build_rewrite_instruction
from podcastfy.litrpg.quarantine import chapter_quarantine_dir
from podcastfy.litrpg.quarantine import next_quarantine_attempt_path
from podcastfy.litrpg.quarantine import quarantine_record_to_dict
from podcastfy.litrpg.quarantine import write_quarantine_record


def test_quarantine_path_and_record_shape_are_deterministic(tmp_path):
    path = next_quarantine_attempt_path(tmp_path, "paper-cuts", 1, 12)
    record = quarantine_record_to_dict(
        {
            "series_id": "paper-cuts",
            "book_number": 1,
            "chapter_number": 12,
            "attempt": 1,
            "violation_notes": ["Sponsor identity revealed early."],
            "scarcity_audit": {"passed": False},
            "chapter": {"title": "The Copier Has Teeth"},
            "parts": [{"part_id": "cold-open"}],
            "combined_script": "<SYSTEM>bad reveal</SYSTEM>",
        }
    )

    assert chapter_quarantine_dir(tmp_path, "paper-cuts", 1) == (
        tmp_path / "series" / "paper-cuts" / "book_1" / "quarantine"
    )
    assert path == (
        tmp_path
        / "series"
        / "paper-cuts"
        / "book_1"
        / "quarantine"
        / "chapter_012_attempt_001.json"
    )
    assert record["status"] == "quarantined"
    assert record["reason"] == "scarcity_audit_failed"
    assert record["max_rewrite_attempts"] == 3

    write_quarantine_record(path, record)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["violation_notes"] == ["Sponsor identity revealed early."]
    assert loaded["parts"][0]["part_id"] == "cold-open"


def test_next_quarantine_attempt_path_increments_existing_attempts(tmp_path):
    first = next_quarantine_attempt_path(tmp_path, "paper-cuts", 1, 12)
    write_quarantine_record(first, {"series_id": "paper-cuts", "chapter_number": 12})

    second = next_quarantine_attempt_path(tmp_path, "paper-cuts", 1, 12)

    assert second.name == "chapter_012_attempt_002.json"


def test_build_rewrite_instruction_names_violations_and_allowed_hints():
    instruction = build_rewrite_instruction(
        {
            "violations": ["Named the sponsor."],
            "warnings": ["Token total increased without trade."],
            "spent_mysteries": ["Sponsor identity"],
        },
        {"book": 1, "chapter": 12, "phase": "The Apex"},
        {
            "items": [
                {
                    "name": "Sponsor identity",
                    "hint_allowed_at_book": 1,
                    "payoff_allowed_at_book": 3,
                }
            ]
        },
    )

    assert "Rewrite required" in instruction
    assert "Named the sponsor." in instruction
    assert "Sponsor identity" in instruction
    assert "book 1, chapter 12" in instruction
