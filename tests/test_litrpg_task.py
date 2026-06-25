import json
from pathlib import Path

import pytest

from podcastfy.litrpg.bible import CharacterBibleEntry, StoryBible, save_story_bible
from podcastfy.litrpg.models import CharacterState, SeriesState
from podcastfy.litrpg.state_store import save_series_state
from podcastfy.litrpg.task import load_litrpg_task, run_litrpg_task


class FakeTTS:
    def __init__(self):
        self.calls = []

    def convert_script_to_speech(
        self, script, output_file, voice_map, role_tags=None, role_instructions=None
    ):
        self.calls.append((script, output_file, voice_map, role_tags, role_instructions))
        Path(output_file).write_bytes(b"task-audio")


def _write_task(tmp_path, **overrides):
    task = {
        "series_id": "paper-cuts",
        "premise": "A clerk discovers the office is a dungeon.",
        "storage_dir": "library",
        "result_path": "last_result.json",
        "render_audio": True,
        "outline": "Outline: SYSTEM grants a quest.",
        "script": "<NARRATOR>Begin.</NARRATOR><SYSTEM>Quest accepted.</SYSTEM>",
        "litrpg_config": {"minutes": 4, "tone": "wry"},
    }
    task.update(overrides)
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    return task_path


def test_load_litrpg_task_requires_json_object(tmp_path):
    task_path = tmp_path / "task.json"
    task_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        load_litrpg_task(task_path)


def test_run_litrpg_task_uses_inline_script_and_writes_result(tmp_path):
    task_path = _write_task(tmp_path)
    tts = FakeTTS()

    result = run_litrpg_task(task_path, tts=tts)

    result_path = tmp_path / "last_result.json"
    audio_path = Path(result["audio_metadata"]["audio_path"])

    assert len(tts.calls) == 1
    assert result["series_id"] == "paper-cuts"
    assert result["episode_number"] == 1
    assert audio_path.exists()
    assert audio_path.read_bytes() == b"task-audio"
    assert json.loads(result_path.read_text(encoding="utf-8"))["series_id"] == "paper-cuts"


def test_run_litrpg_task_passes_tts_provider_options(tmp_path, monkeypatch):
    task_path = _write_task(
        tmp_path,
        tts={"provider": "openai", "model": "gpt-4o-mini-tts", "format": "mp3"},
    )
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"series_id": kwargs["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_audio_episode", fake_generate)

    result = run_litrpg_task(task_path, tts=FakeTTS())

    assert result == {"series_id": "paper-cuts"}
    assert captured["tts_options"]["provider"] == "openai"


def test_run_litrpg_task_replays_inline_script_without_rendering_again(tmp_path):
    task_path = _write_task(tmp_path)
    first_tts = FakeTTS()
    first = run_litrpg_task(task_path, tts=first_tts)
    second_tts = FakeTTS()

    replay = run_litrpg_task(task_path, tts=second_tts)

    assert replay["replayed"] is True
    assert replay["episode_id"] == first["episode_id"]
    assert replay["audio_metadata"]["audio_path"] == first["audio_metadata"]["audio_path"]
    assert second_tts.calls == []


def test_run_litrpg_task_rejects_unknown_generation_provider(tmp_path):
    task_path = _write_task(
        tmp_path,
        outline="",
        script="",
        generation={"provider": "unknown"},
    )

    with pytest.raises(ValueError, match="generation.provider=openai"):
        run_litrpg_task(task_path, tts=FakeTTS())


def test_run_litrpg_task_injects_story_bible_and_mechanics_context_for_chapters(tmp_path, monkeypatch):
    storage_dir = tmp_path / "library"
    series_dir = storage_dir / "series" / "paper-cuts"
    save_story_bible(
        storage_dir,
        StoryBible(
            series_id="paper-cuts",
            characters={
                "Hero": CharacterBibleEntry(
                    name="Hero",
                    never_contradict_facts=["Hero promised never to trust elevators."],
                    voice_rules=["Dry under pressure."],
                )
            },
        ),
    )
    save_series_state(
        series_dir,
        SeriesState(
            series_id="paper-cuts",
            title="Paper Cuts",
            episode_number=2,
            character=CharacterState(
                name="Hero",
                level=3,
                character_class="Intern",
                skills=["Paper Cut"],
                inventory=["mana flask"],
            ),
        ),
    )
    task_path = tmp_path / "chapter_task.json"
    task_path.write_text(
        json.dumps(
            {
                "mode": "chapter",
                "series_id": "paper-cuts",
                "premise": "A clerk discovers the office is a dungeon.",
                "storage_dir": "library",
                "reviews": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_generate(task, *, llm):
        captured.update(task)
        return {"mode": "chapter", "series_id": task["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_chapter", fake_generate)

    result = run_litrpg_task(task_path, llm=object())

    assert result == {"mode": "chapter", "series_id": "paper-cuts"}
    assert "Hero promised never to trust elevators." in captured["story_bible_summary"]
    assert captured["mechanics_context"]["inventory"] == ["mana flask"]
    assert captured["mechanics_context"]["skills"] == ["Paper Cut"]
    assert captured["mechanics_context"]["class"] == "Intern"
