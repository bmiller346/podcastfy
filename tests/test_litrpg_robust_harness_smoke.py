import json

from podcastfy.litrpg.task import run_litrpg_task_data


def test_robust_harness_smoke_covers_gates_quarantine_effects_and_handoff(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_generate(task, *, llm):
        calls.append(int(task.get("chapter_number") or 0))
        chapter_number = int(task.get("chapter_number") or 1)
        if chapter_number == 1:
            return {
                "mode": "chapter",
                "series_id": "paper-cuts",
                "chapter": {"number": 1, "title": "Approved Start"},
                "parts": [],
                "combined_script": "<NARRATOR>Approved.</NARRATOR>",
                "quarantine": {"status": "passed"},
                "scarcity_audit": {"passed": True, "spent_mysteries": []},
            }
        return {
            "mode": "chapter",
            "series_id": "paper-cuts",
            "chapter": {"number": chapter_number, "title": "Bad Reveal"},
            "parts": [{"part_id": "cold-open"}],
            "combined_script": "<SYSTEM>The forbidden answer is named.</SYSTEM>",
            "quarantine": {
                "status": "quarantined",
                "book_number": 1,
                "chapter_number": chapter_number,
                "violation_notes": ["Forbidden answer revealed early"],
                "warnings": [],
                "rewrite_instruction": "Remove the forbidden answer.",
                "rewrite_attempts": 0,
                "max_rewrite_attempts": 3,
                "scarcity_audit": {"passed": False, "quarantine_required": True},
            },
            "scarcity_audit": {"passed": False, "quarantine_required": True},
        }

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_chapter", fake_generate)

    base_task = {
        "mode": "chapter",
        "series_id": "paper-cuts",
        "book_number": 1,
        "storage_dir": "library",
        "harness": {"enabled": True},
        "generation": {"provider": "fake", "model": "unit"},
    }

    blocked_by_gate = run_litrpg_task_data(
        {**base_task, "chapter_number": 1},
        base_dir=tmp_path,
        llm=object(),
    )
    assert blocked_by_gate["status"] == "approval_required"
    assert blocked_by_gate["harness_decision"]["stage"] == "chapter_generation"
    assert calls == []

    approved = run_litrpg_task_data(
        {
            **base_task,
            "chapter_number": 1,
            "approved_stages": ["chapter_generation"],
            "result_path": "chapter_001.json",
        },
        base_dir=tmp_path,
        llm=object(),
    )
    assert approved["quarantine"]["status"] == "passed"
    assert calls == [1]

    quarantined = run_litrpg_task_data(
        {
            **base_task,
            "chapter_number": 2,
            "approved_stages": ["chapter_generation"],
            "result_path": "chapter_002.json",
        },
        base_dir=tmp_path,
        llm=object(),
    )
    quarantine_path = (
        tmp_path
        / "library"
        / "series"
        / "paper-cuts"
        / "book_1"
        / "quarantine"
        / "chapter_002_attempt_001.json"
    )
    assert quarantined["quarantine"]["status"] == "quarantined"
    assert quarantine_path.exists()
    assert json.loads(quarantine_path.read_text(encoding="utf-8"))["rewrite_instruction"] == (
        "Remove the forbidden answer."
    )

    quarantine_dir = tmp_path / "library" / "series" / "paper-cuts" / "book_1" / "quarantine"
    for attempt in (1, 2, 3):
        (quarantine_dir / f"chapter_003_attempt_{attempt:03d}.json").write_text(
            json.dumps({"attempt": attempt}),
            encoding="utf-8",
        )
    blocked = run_litrpg_task_data(
        {
            **base_task,
            "chapter_number": 3,
            "approved_stages": ["chapter_generation"],
            "result_path": "chapter_003.json",
            "generate_handoff": True,
            "max_rewrite_attempts": 3,
        },
        base_dir=tmp_path,
        llm=object(),
    )

    series_root = tmp_path / "library" / "series" / "paper-cuts"
    agent_state = json.loads((series_root / "agent_state.json").read_text(encoding="utf-8"))
    effect_entries = [
        json.loads(line)
        for line in (series_root / "effect_log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    handoff = (series_root / "book_1" / "HANDOFF.md").read_text(encoding="utf-8")

    assert blocked["quarantine"]["status"] == "blocked"
    assert agent_state["blocked"][0]["kind"] == "quarantine_blocker"
    assert {entry["stage"] for entry in effect_entries} >= {
        "chapter_generation",
        "chapter_result_write",
    }
    assert "## Quarantined/blocked chapters" in handoff
    assert "Forbidden answer revealed early" in handoff
    assert "## Pending human decisions" in handoff
