import json
import os
import shutil
from pathlib import Path

import pytest

from podcastfy.litrpg.task import load_litrpg_task, run_litrpg_task


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_TASK = REPO_ROOT / "usage" / "litrpg_live_smoke.task.example.json"


def _live_smoke_skip_reason() -> str | None:
    if os.environ.get("RUN_LITRPG_LIVE_SMOKE") != "1":
        return "Set RUN_LITRPG_LIVE_SMOKE=1 to run the live provider smoke test"
    if not os.environ.get("OPENAI_API_KEY"):
        return "Set OPENAI_API_KEY to run the live provider smoke test"
    return None


def test_live_smoke_example_loads_and_defaults_to_no_audio():
    task = load_litrpg_task(SMOKE_TASK)

    assert task["mode"] == "chapter"
    assert task["series_id"] == "live-smoke"
    assert task["render_audio"] is False
    assert task["generation"]["provider"] == "openai"
    assert task["generation"]["model"] == "gpt-5.5"
    assert task["generation"]["max_retries"] == 2
    assert task["reviews"]["enabled"] is False
    assert task["reviews"]["rewrite"] is False


def test_live_smoke_example_limits_live_generation_cost():
    task = load_litrpg_task(SMOKE_TASK)
    locked = task["locked_part_scripts"]

    assert set(locked) == {
        "mechanics-reveal",
        "boss-setpiece",
        "fallout-cliffhanger",
    }
    assert "cold-open" not in locked
    assert "party-pressure" not in locked
    assert task["part_overrides"]["cold-open"]["target_minutes"] == 2
    assert task["part_overrides"]["party-pressure"]["target_minutes"] == 2


def test_live_smoke_skip_reason_requires_flag_and_api_key(monkeypatch):
    monkeypatch.delenv("RUN_LITRPG_LIVE_SMOKE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert "RUN_LITRPG_LIVE_SMOKE" in _live_smoke_skip_reason()

    monkeypatch.setenv("RUN_LITRPG_LIVE_SMOKE", "1")
    assert "OPENAI_API_KEY" in _live_smoke_skip_reason()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert _live_smoke_skip_reason() is None


def test_live_smoke_task_copy_keeps_paths_relative_to_task_file(tmp_path):
    task = load_litrpg_task(SMOKE_TASK)
    task["storage_dir"] = "smoke-data"
    task["result_path"] = "smoke-data/chapter-001.json"
    task["checkpoint_dir"] = "smoke-data/chapter-001_checkpoints"
    task["settings_path"] = "settings.local.json"
    task_path = tmp_path / "live-smoke.task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")

    loaded = load_litrpg_task(task_path)

    assert loaded["storage_dir"] == "smoke-data"
    assert loaded["result_path"] == "smoke-data/chapter-001.json"
    assert loaded["checkpoint_dir"] == "smoke-data/chapter-001_checkpoints"
    assert loaded["settings_path"] == "settings.local.json"


def test_live_smoke_with_real_openai_provider(tmp_path):
    reason = _live_smoke_skip_reason()
    if reason:
        pytest.skip(reason)

    task_path = tmp_path / "live-smoke.task.json"
    task = load_litrpg_task(SMOKE_TASK)
    task["storage_dir"] = "smoke-data"
    task["result_path"] = "smoke-data/chapter-001.json"
    task["checkpoint_dir"] = "smoke-data/chapter-001_checkpoints"
    task["settings_path"] = "settings.local.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    settings_path = REPO_ROOT / "settings.local.json"
    if settings_path.exists():
        shutil.copyfile(settings_path, tmp_path / "settings.local.json")
    else:
        (tmp_path / "settings.local.json").write_text("{}", encoding="utf-8")

    result = run_litrpg_task(task_path)

    assert result["mode"] == "chapter"
    assert result["series_id"] == "live-smoke"
    assert result["render"]["audio_rendered"] is False
    assert (tmp_path / "smoke-data" / "chapter-001.json").exists()
    assert (tmp_path / "smoke-data" / "chapter-001_checkpoints").exists()
