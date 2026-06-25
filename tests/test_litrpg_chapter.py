import json

from podcastfy.litrpg.chapter import generate_litrpg_chapter
from podcastfy.litrpg.task import run_litrpg_task


class FakeChapterLLM:
    def __init__(self):
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        if stage.startswith("part:"):
            role = "SYSTEM" if stage == "part:mechanics-reveal" else "NARRATOR"
            return f"<{role}>{stage} script with cursed stapler.</{role}>"
        if stage.startswith("review:"):
            return f"review for {stage}"
        if stage == "chapter_review":
            return "chapter review: render ready"
        raise AssertionError(f"unexpected stage {stage}")


def _chapter_task(**overrides):
    task = {
        "mode": "chapter",
        "series_id": "paper-cuts",
        "premise": "A clerk discovers the office is a dungeon.",
        "chapter_number": 2,
        "chapter_title": "The Stapler Hungers",
        "target_minutes": 25,
        "injected_beats": ["The cursed stapler must appear.", "The copier demands tribute."],
        "generation": {"provider": "fake", "temperature": 0.2},
        "reviews": {"enabled": True},
    }
    task.update(overrides)
    return task


def test_generate_litrpg_chapter_calls_parts_reviews_and_chapter_review_in_order():
    llm = FakeChapterLLM()

    result = generate_litrpg_chapter(_chapter_task(), llm=llm)

    assert [call["stage"] for call in llm.calls] == [
        "part:cold-open",
        "review:cold-open",
        "part:party-pressure",
        "review:party-pressure",
        "part:mechanics-reveal",
        "review:mechanics-reveal",
        "part:boss-setpiece",
        "review:boss-setpiece",
        "part:fallout-cliffhanger",
        "review:fallout-cliffhanger",
        "chapter_review",
    ]
    assert "The cursed stapler must appear." in llm.calls[0]["prompt"]
    assert result["chapter"]["number"] == 2
    assert result["chapter"]["title"] == "The Stapler Hungers"
    assert result["parts"][0]["review"] == "review for review:cold-open"
    assert "part:cold-open script" in result["combined_script"]
    assert result["render"]["ready"] is True
    assert result["render"]["audio_rendered"] is False


def test_generate_litrpg_chapter_applies_part_overrides_and_disables_reviews():
    llm = FakeChapterLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            reviews={"enabled": False},
            part_overrides={
                "cold-open": {
                    "title": "Payroll Ambush",
                    "target_minutes": 7,
                    "extra_injected_beats": ["The boss fight starts at the time clock."],
                }
            },
        ),
        llm=llm,
    )

    assert [call["stage"] for call in llm.calls] == [
        "part:cold-open",
        "part:party-pressure",
        "part:mechanics-reveal",
        "part:boss-setpiece",
        "part:fallout-cliffhanger",
    ]
    assert result["parts"][0]["title"] == "Payroll Ambush"
    assert result["parts"][0]["target_minutes"] == 7
    assert "The boss fight starts at the time clock." in result["parts"][0]["prompt"]
    assert result["parts"][0]["review"] == ""
    assert result["chapter_review"] == ""


def test_run_litrpg_task_routes_chapter_mode_and_writes_result(tmp_path):
    task_path = tmp_path / "chapter_task.json"
    task = _chapter_task(result_path="chapter_result.json")
    task_path.write_text(json.dumps(task), encoding="utf-8")
    llm = FakeChapterLLM()

    result = run_litrpg_task(task_path, llm=llm)

    written = json.loads((tmp_path / "chapter_result.json").read_text(encoding="utf-8"))
    assert result["mode"] == "chapter"
    assert written["mode"] == "chapter"
    assert written["series_id"] == "paper-cuts"


def test_run_litrpg_task_default_mode_still_uses_episode_pipeline(tmp_path, monkeypatch):
    task_path = tmp_path / "task.json"
    task_path.write_text(
        json.dumps(
            {
                "series_id": "paper-cuts",
                "premise": "A clerk discovers the office is a dungeon.",
                "outline": "Outline",
                "script": "<NARRATOR>Begin.</NARRATOR>",
                "render_audio": False,
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"mode": "episode", "series_id": kwargs["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_audio_episode", fake_generate)

    result = run_litrpg_task(task_path)

    assert result == {"mode": "episode", "series_id": "paper-cuts"}
    assert captured["premise"] == "A clerk discovers the office is a dungeon."
