import json
from pathlib import Path

import pytest

from podcastfy.litrpg.library import (
    delete_episode,
    get_audio_path,
    get_episode,
    get_series,
    list_episodes,
    list_regenerable_parts,
    list_series,
    mark_episode_status,
)


def test_library_lists_complete_episode_and_reads_metadata(tmp_path):
    episode_dir = _episode_dir(tmp_path, "ember-keep", "episode-0001")
    audio_path = episode_dir / "audio" / "final.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"audio")
    _write_json(
        episode_dir / "metadata.json",
        {
            "cache_key": "cache-1",
            "episode_id": "episode-0001",
            "episode_number": 1,
            "files": {"script": "script.xml"},
            "prompt": "Open the cellar.",
            "series_id": "ember-keep",
        },
    )
    _write_json(episode_dir / "config.json", {"minutes": 8, "tone": "wry"})
    _write_json(episode_dir / "audio_metadata.json", {"audio_path": str(audio_path)})
    (episode_dir / "script.xml").write_text("<NARRATOR>Begin.</NARRATOR>", encoding="utf-8")
    _write_json(
        tmp_path / "series" / "ember-keep" / "series_state.json",
        {"series_id": "ember-keep", "title": "Ember Keep"},
    )

    series = list_series(tmp_path)
    episodes = list_episodes(tmp_path)
    episode = get_episode(tmp_path, "ember-keep", "episode-0001")

    assert series[0]["series_id"] == "ember-keep"
    assert series[0]["title"] == "Ember Keep"
    assert series[0]["episode_count"] == 1
    assert series[0]["incomplete_count"] == 0
    assert episodes[0]["status"] == "complete"
    assert episode["prompt"] == "Open the cellar."
    assert episode["config"]["minutes"] == 8
    assert episode["metadata"]["cache_key"] == "cache-1"
    assert episode["audio_path"] == str(audio_path.resolve())
    assert get_series(tmp_path, "ember-keep")["title"] == "Ember Keep"
    assert get_audio_path(tmp_path, "ember-keep", "episode-0001") == str(
        audio_path.resolve()
    )


def test_library_infers_missing_audio_incomplete_and_failed_render(tmp_path):
    missing_audio_dir = _episode_dir(tmp_path, "ember-keep", "episode-0001")
    _write_bundle(missing_audio_dir, status=None)

    incomplete_dir = _episode_dir(tmp_path, "ember-keep", "episode-0002")
    _write_json(
        incomplete_dir / "metadata.json",
        {
            "episode_id": "episode-0002",
            "episode_number": 2,
            "files": {},
            "series_id": "ember-keep",
        },
    )
    _write_json(incomplete_dir / "config.json", {"minutes": 4})

    failed_dir = _episode_dir(tmp_path, "ember-keep", "episode-0003")
    _write_bundle(failed_dir, status="failed_render")

    statuses = {
        episode["episode_id"]: episode["status"]
        for episode in list_episodes(tmp_path, "ember-keep")
    }

    assert statuses == {
        "episode-0001": "missing_audio",
        "episode-0002": "incomplete",
        "episode-0003": "failed_render",
    }


def test_library_ignores_unsafe_audio_metadata_path(tmp_path):
    outside_audio = tmp_path.parent / "outside.mp3"
    outside_audio.write_bytes(b"outside")
    episode_dir = _episode_dir(tmp_path, "ember-keep", "episode-0001")
    _write_bundle(episode_dir, status=None)
    _write_json(episode_dir / "audio_metadata.json", {"audio_path": str(outside_audio)})

    episode = get_episode(tmp_path, "ember-keep", "episode-0001")

    assert episode["audio_path"] is None
    assert episode["status"] == "missing_audio"


def test_delete_episode_removes_only_safe_bundle_paths(tmp_path):
    episode_dir = _episode_dir(tmp_path, "ember-keep", "episode-0001")
    _write_bundle(episode_dir, status=None)
    outside = tmp_path.parent / "outside-keep.txt"
    outside.write_text("keep", encoding="utf-8")

    assert delete_episode(tmp_path, "ember-keep", "episode-0001") is True
    assert not episode_dir.exists()
    assert outside.exists()
    assert delete_episode(tmp_path, "ember-keep", "episode-0001") is False
    with pytest.raises(ValueError):
        delete_episode(tmp_path, "..", "outside")


def test_mark_episode_status_and_list_regenerable_parts(tmp_path):
    episode_dir = _episode_dir(tmp_path, "ember-keep", "episode-0004")
    _write_bundle(episode_dir, status=None)
    parts_dir = episode_dir / "parts"
    parts_dir.mkdir()
    (parts_dir / "part-0001.xml").write_text("<line>One</line>", encoding="utf-8")

    marked = mark_episode_status(
        tmp_path, "ember-keep", "episode-0004", "failed_render"
    )
    parts = list_regenerable_parts(tmp_path, "ember-keep", "episode-0004")

    assert marked["status"] == "failed_render"
    assert {part["relative_path"] for part in parts} == {
        "script.xml",
        str(Path("parts") / "part-0001.xml"),
    }


def _episode_dir(tmp_path, series_id, episode_id):
    episode_dir = tmp_path / "episodes" / series_id / episode_id
    episode_dir.mkdir(parents=True)
    return episode_dir


def _write_bundle(episode_dir, status):
    episode_id = episode_dir.name
    series_id = episode_dir.parent.name
    metadata = {
        "episode_id": episode_id,
        "episode_number": int(episode_id.rsplit("-", 1)[1]),
        "files": {"script": "script.xml"},
        "series_id": series_id,
    }
    if status:
        metadata["status"] = status
    _write_json(episode_dir / "metadata.json", metadata)
    _write_json(episode_dir / "config.json", {"minutes": 5})
    (episode_dir / "script.xml").write_text("<NARRATOR>Begin.</NARRATOR>", encoding="utf-8")


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
