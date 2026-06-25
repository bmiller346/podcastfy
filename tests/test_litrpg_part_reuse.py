import json

from podcastfy.litrpg.part_reuse import locked_part_scripts_from_ready_parts
from podcastfy.litrpg.task import run_litrpg_task


def _prior_result():
    return {
        "mode": "chapter",
        "parts": [
            {
                "part_id": "cold-open",
                "script": "<NARRATOR>Draft.</NARRATOR>",
                "revised_script": "<NARRATOR>Ready XP.</NARRATOR>",
                "gate": {"final": {"ready": True}},
            },
            {
                "part_id": "party-pressure",
                "script": "<NARRATOR>Weak.</NARRATOR>",
                "revised_script": "<NARRATOR>Still weak.</NARRATOR>",
                "gate": {"final": {"ready": False}},
            },
            {
                "part_id": "mechanics-reveal",
                "script": "<SYSTEM>Quest ready.</SYSTEM>",
                "qa": {"state": "ready"},
            },
        ],
    }


def test_locked_part_scripts_from_ready_parts_accepts_result_dict():
    locked = locked_part_scripts_from_ready_parts(_prior_result())

    assert locked == {
        "cold-open": "<NARRATOR>Ready XP.</NARRATOR>",
        "mechanics-reveal": "<SYSTEM>Quest ready.</SYSTEM>",
    }


def test_locked_part_scripts_from_ready_parts_accepts_result_file(tmp_path):
    result_path = tmp_path / "prior_chapter.json"
    result_path.write_text(json.dumps(_prior_result()), encoding="utf-8")

    locked = locked_part_scripts_from_ready_parts(result_path)

    assert locked["cold-open"] == "<NARRATOR>Ready XP.</NARRATOR>"
    assert locked["mechanics-reveal"] == "<SYSTEM>Quest ready.</SYSTEM>"


def test_locked_part_scripts_from_ready_parts_skips_failed_parts():
    locked = locked_part_scripts_from_ready_parts(_prior_result())

    assert "party-pressure" not in locked


def test_run_litrpg_task_injects_reused_locks_and_keeps_explicit_locks(tmp_path, monkeypatch):
    prior_path = tmp_path / "prior_chapter.json"
    prior_path.write_text(json.dumps(_prior_result()), encoding="utf-8")
    task_path = tmp_path / "chapter_task.json"
    task_path.write_text(
        json.dumps(
            {
                "mode": "chapter",
                "series_id": "paper-cuts",
                "premise": "A clerk discovers the office is a dungeon.",
                "reuse_ready_parts_from": "prior_chapter.json",
                "locked_part_scripts": {
                    "cold-open": "<NARRATOR>Explicit winner XP.</NARRATOR>",
                    "boss-setpiece": "<BOSS>Manual lock with loot.</BOSS>",
                },
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_generate(task, *, llm):
        captured.update(task)
        return {"mode": "chapter", "series_id": task["series_id"], "parts": []}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_chapter", fake_generate)

    result = run_litrpg_task(task_path, llm=object())

    assert result["mode"] == "chapter"
    assert captured["locked_part_scripts"] == {
        "cold-open": "<NARRATOR>Explicit winner XP.</NARRATOR>",
        "mechanics-reveal": "<SYSTEM>Quest ready.</SYSTEM>",
        "boss-setpiece": "<BOSS>Manual lock with loot.</BOSS>",
    }
    assert "party-pressure" not in captured["locked_part_scripts"]
