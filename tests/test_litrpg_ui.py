import http.client
import json
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer

import pytest

from podcastfy.litrpg import ui


@pytest.fixture
def ui_roots(tmp_path, monkeypatch):
    project_root = tmp_path
    usage_dir = project_root / "usage"
    data_dir = project_root / "data" / "litrpg"
    usage_dir.mkdir()
    data_dir.mkdir(parents=True)
    monkeypatch.setattr(ui, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(ui, "USAGE_DIR", usage_dir)
    monkeypatch.setattr(ui, "DATA_DIR", data_dir)
    monkeypatch.setattr(ui, "SETTINGS_PATH", data_dir / "settings.json")
    with ui._JOBS_LOCK:
        ui._JOBS.clear()
    return project_root


@pytest.fixture
def ui_server(ui_roots):
    handler = partial(ui.LitRPGUIHandler, directory=str(ui.STATIC_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def request_json(server, method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection = http.client.HTTPConnection(server.server_address[0], server.server_address[1])
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data
    finally:
        connection.close()


def request_bytes(server, path):
    connection = http.client.HTTPConnection(server.server_address[0], server.server_address[1])
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read(), response.getheader("Content-Type")
    finally:
        connection.close()


def test_index_page_exposes_task_creation_form(ui_server):
    status, body, content_type = request_bytes(ui_server, "/")
    html = body.decode("utf-8")

    assert status == 200
    assert content_type == "text/html"
    assert 'id="active-series-id"' in html
    assert 'id="series-select"' in html
    assert 'id="use-task-series"' in html
    assert 'id="load-active-series"' in html
    assert 'id="new-series-package"' in html
    assert 'id="series-status"' in html
    assert 'id="task-form"' in html
    assert 'name="series_id"' in html
    assert 'name="premise"' in html
    assert 'name="mode"' in html
    assert 'name="genre"' in html
    assert 'name="generation_provider"' in html
    assert 'name="generation_model"' in html
    assert 'name="tts_provider"' in html
    assert 'name="tts_model"' in html
    assert 'name="tts_format"' in html
    assert 'name="render_audio"' in html
    assert 'name="result_path"' in html
    assert 'name="checkpoint_dir"' in html
    assert 'name="storage_dir"' in html
    assert 'id="task-preview"' in html
    assert 'id="diagnostics-summary"' in html
    assert 'id="diagnostics-output"' in html
    assert 'id="copy-diagnostics"' in html
    assert 'id="package-form"' in html
    assert 'name="package_series_id"' in html
    assert 'name="baseline_text"' in html
    assert 'id="load-package"' in html
    assert 'id="save-package"' in html
    assert 'id="generate-package"' in html
    assert 'id="copy-package"' in html
    assert 'id="package-output"' in html
    assert 'id="role-package-panel"' in html
    assert 'id="role-list"' in html
    assert 'id="add-role"' in html
    assert 'id="rebuild-roles"' in html
    assert 'id="save-roles"' in html


def test_favicon_request_is_ignored_without_404_noise(ui_server):
    status, body, content_type = request_bytes(ui_server, "/favicon.ico")

    assert status == 204
    assert body == b""
    assert content_type is None


def test_series_package_save_and_load_uses_local_storage_fallback(ui_server, ui_roots):
    package = {
        "schema_version": "test-v1",
        "series_id": "catamaran-crawlers",
        "system_announcer": {"name": "System", "tone": "hostile marina bureaucrat"},
        "characters": [{"name": "Edward"}, {"name": "Kelli"}],
        "familiar": {"name": "Pedro"},
        "home_base": {"name": "The Marsh Boat"},
        "floor_rules": {"rules": ["No refunds."]},
        "faction_map": {"factions": [{"name": "Dockside Compact"}]},
        "bestiary": [{"name": "Code Worm", "entity_type": "mob"}],
        "encounters": [{"name": "Harbor Auditor", "encounter_type": "boss"}],
    }

    save_status, save_data = request_json(
        ui_server,
        "POST",
        "/api/series-package",
        {"series_id": "catamaran-crawlers", "package": package},
    )
    load_status, load_data = request_json(
        ui_server,
        "GET",
        "/api/series-package?series_id=catamaran-crawlers",
    )
    package_path = (
        ui_roots
        / "data"
        / "litrpg"
        / "series"
        / "catamaran-crawlers"
        / "series_package.json"
    )

    assert save_status == 200
    assert save_data["available"] is True
    assert save_data["modules"]["packages"] is True
    assert "System: tone: hostile marina bureaucrat" in save_data["summary"]
    assert "Edward: character package pending detail" in save_data["summary"]
    assert "Kelli: character package pending detail" in save_data["summary"]
    assert "Bestiary Code Worm:" in save_data["summary"]
    assert "Encounter Harbor Auditor:" in save_data["summary"]
    assert load_status == 200
    assert load_data["package"]["familiar"]["name"] == "Pedro"
    assert load_data["path"] == "data/litrpg/series/catamaran-crawlers/series_package.json"
    assert json.loads(package_path.read_text(encoding="utf-8"))["series_id"] == "catamaran-crawlers"


def test_series_package_load_missing_returns_readiness_payload(ui_server):
    status, data = request_json(
        ui_server,
        "GET",
        "/api/series-package?series_id=catamaran-crawlers",
    )

    assert status == 200
    assert data["available"] is False
    assert data["status"] == "missing"
    assert data["package"] is None
    assert data["modules"]["generator"] is True


def test_series_package_generate_uses_generator_when_available(
    ui_server, ui_roots, monkeypatch
):
    calls = []

    def fake_generate_series_package(*, series_id, premise, genre="", baseline_text, storage_dir):
        calls.append((series_id, premise, genre, baseline_text, storage_dir))
        return {
            "schema_version": "generated-v1",
            "series_id": series_id,
            "premise": premise,
            "metadata": {"genre": genre},
            "system_announcer": {"name": "Announcer", "tone": baseline_text},
            "characters": [{"name": "Edward"}],
        }

    monkeypatch.setattr(ui, "generate_series_package", fake_generate_series_package)

    status, data = request_json(
        ui_server,
        "POST",
        "/api/series-package/generate",
        {
            "series_id": "catamaran-crawlers",
            "premise": "Edward and Kelli get absorbed into a dungeon with a boat.",
            "genre": "Retirement heist",
            "baseline_text": "fine print against its will",
        },
    )
    saved = json.loads(
        (
            ui_roots
            / "data"
            / "litrpg"
            / "series"
            / "catamaran-crawlers"
            / "series_package.json"
        ).read_text(encoding="utf-8")
    )

    assert status == 200
    assert data["status"] == "generated"
    assert data["package"]["schema_version"] == 1
    assert saved["system_announcer"]["tone"] == "fine print against its will"
    assert calls == [
        (
            "catamaran-crawlers",
            "Edward and Kelli get absorbed into a dungeon with a boat.",
            "Retirement heist",
            "fine print against its will",
            ui.DATA_DIR,
        )
    ]
    assert saved["metadata"]["genre"] == "Retirement heist"


def test_series_package_generate_reports_unavailable_without_generator(ui_server):
    status, data = request_json(
        ui_server,
        "POST",
        "/api/series-package/generate",
        {
            "series_id": "catamaran-crawlers",
            "premise": "Edward and Kelli get absorbed into a dungeon with a boat.",
        },
    )

    assert status == 503
    assert data["ok"] is False
    assert data["status"] == "generator_unavailable"
    assert "not installed" in data["error"]


def test_series_package_rejects_unsafe_series_id(ui_server):
    status, data = request_json(
        ui_server,
        "GET",
        "/api/series-package?series_id=../secret",
    )

    assert status == 400
    assert "Unsafe path segment" in data["error"]


def wait_for_job(server, job_id, status, timeout=2):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response_status, data = request_json(server, "GET", f"/api/jobs/{job_id}")
        assert response_status == 200
        last = data["job"]
        if last["status"] == status:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} did not reach {status}; last={last}")


def test_settings_round_trip_redacts_secret_values(ui_server, ui_roots, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    status, data = request_json(
        ui_server,
        "POST",
        "/api/settings",
        {
            "openai_api_key": "from-file",
            "gemini_api_key": "",
            "default_tts_provider": "edge",
            "default_model": "gpt-5.5",
            "default_tts_model": "gpt-4o-mini-tts",
            "default_tts_format": "mp3",
            "unexpected": "ignored",
        },
    )

    settings_path = ui_roots / "data" / "litrpg" / "settings.json"
    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert status == 200
    assert stored == {
        "default_model": "gpt-5.5",
        "default_tts_format": "mp3",
        "default_tts_model": "gpt-4o-mini-tts",
        "default_tts_provider": "edge",
        "openai_api_key": "from-file",
    }
    assert data["settings_path"] == str(settings_path)
    assert data["api_keys"]["openai"]["configured"] is True
    assert data["api_keys"]["openai"]["value"] == "redacted"
    assert data["defaults"]["default_model"] == "gpt-5.5"
    assert data["defaults"]["default_tts_model"] == "gpt-4o-mini-tts"
    assert data["defaults"]["default_tts_format"] == "mp3"
    assert "from-file" not in json.dumps(data)
    assert "from-env" not in json.dumps(data)


def test_settings_get_does_not_return_plaintext_saved_or_env_keys(
    ui_server, ui_roots, monkeypatch
):
    settings_path = ui_roots / "data" / "litrpg" / "settings.json"
    settings_path.write_text(
        json.dumps({"elevenlabs_api_key": "eleven-secret"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

    status, data = request_json(ui_server, "GET", "/api/settings")
    encoded = json.dumps(data)

    assert status == 200
    assert data["api_keys"]["elevenlabs"]["value"] == "redacted"
    assert data["api_keys"]["gemini"]["env"] is True
    assert "eleven-secret" not in encoded
    assert "gemini-secret" not in encoded


def test_settings_post_can_clear_non_secret_defaults_without_clearing_saved_keys(
    ui_server, ui_roots
):
    settings_path = ui_roots / "data" / "litrpg" / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "openai_api_key": "openai-secret",
                "default_model": "gpt-5.5",
                "default_tts_format": "wav",
            }
        ),
        encoding="utf-8",
    )

    status, data = request_json(
        ui_server,
        "POST",
        "/api/settings",
        {
            "openai_api_key": "",
            "default_model": "",
            "default_tts_format": "",
        },
    )
    stored = json.loads(settings_path.read_text(encoding="utf-8"))

    assert status == 200
    assert stored == {"openai_api_key": "openai-secret"}
    assert data["defaults"]["default_model"] == ""
    assert data["defaults"]["default_tts_format"] == ""
    assert data["api_keys"]["openai"]["configured"] is True


def test_tasks_endpoint_lists_supported_story_json_files(ui_server, ui_roots):
    (ui_roots / "usage" / "litrpg_task.json").write_text("{}", encoding="utf-8")
    (ui_roots / "usage" / "story_task.json").write_text("{}", encoding="utf-8")
    (ui_roots / "usage" / "audio_story_task.json").write_text("{}", encoding="utf-8")
    (ui_roots / "usage" / "notes.json").write_text("{}", encoding="utf-8")

    status, data = request_json(ui_server, "GET", "/api/tasks")

    assert status == 200
    assert data["tasks"] == [
        {"name": "audio_story_task.json", "path": "usage/audio_story_task.json"},
        {"name": "litrpg_task.json", "path": "usage/litrpg_task.json"},
        {"name": "story_task.json", "path": "usage/story_task.json"},
    ]


def test_run_task_rejects_paths_outside_usage(ui_server, ui_roots):
    (ui_roots / "outside.json").write_text("{}", encoding="utf-8")

    status, data = request_json(
        ui_server, "POST", "/api/run-task", {"path": "../outside.json"}
    )

    assert status == 400
    assert "inside usage" in data["error"]


def test_run_task_rejects_unsupported_usage_file_prefix(ui_server, ui_roots):
    (ui_roots / "usage" / "notes.json").write_text("{}", encoding="utf-8")

    status, data = request_json(
        ui_server, "POST", "/api/run-task", {"path": "usage/notes.json"}
    )

    assert status == 400
    assert "litrpg*.json" in data["error"]
    assert "story*.json" in data["error"]


def test_run_task_calls_task_runner_with_safe_task_path(
    ui_server, ui_roots, monkeypatch
):
    task_path = ui_roots / "usage" / "litrpg_task.json"
    task_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_run_litrpg_task(path):
        calls.append(path)
        return {"series_id": "paper-cuts", "episode_number": 1}

    monkeypatch.setattr(ui, "run_litrpg_task", fake_run_litrpg_task)

    status, data = request_json(
        ui_server, "POST", "/api/run-task", {"path": "usage/litrpg_task.json"}
    )

    assert status == 200
    assert calls == [task_path.resolve()]
    assert data["result"]["series_id"] == "paper-cuts"


def test_run_task_accepts_inline_task_payload(ui_server, monkeypatch):
    calls = []

    def fake_run_litrpg_task_data(task, *, base_dir, llm=None, tts=None):
        calls.append((task, base_dir, llm, tts))
        return {"series_id": task["series_id"], "mode": task.get("mode", "episode")}

    monkeypatch.setattr(ui, "run_litrpg_task_data", fake_run_litrpg_task_data)

    status, data = request_json(
        ui_server,
        "POST",
        "/api/run-task",
        {
            "task": {
                "series_id": "paper-cuts",
                "premise": "A clerk descends into the office basement.",
                "mode": "chapter",
            }
        },
    )

    assert status == 200
    assert data["result"] == {"series_id": "paper-cuts", "mode": "chapter"}
    assert calls[0][0]["series_id"] == "paper-cuts"
    assert calls[0][1] == ui.PROJECT_ROOT


def test_submit_task_job_tracks_success_metadata(
    ui_server, ui_roots, monkeypatch
):
    task_path = ui_roots / "usage" / "litrpg_task.json"
    task_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_run_litrpg_task(path):
        calls.append(path)
        return {
            "series_id": "paper-cuts",
            "episode_number": 1,
            "checkpoint_dir": "data/litrpg/checkpoints/paper-cuts",
            "checkpoint_paths": ["part-1.json", "part-1_approved.xml"],
            "ignored_large_payload": "not needed",
        }

    monkeypatch.setattr(ui, "run_litrpg_task", fake_run_litrpg_task)

    status, data = request_json(
        ui_server, "POST", "/api/jobs", {"path": "usage/litrpg_task.json"}
    )
    job = data["job"]
    final_job = wait_for_job(ui_server, job["job_id"], "succeeded")
    list_status, list_data = request_json(ui_server, "GET", "/api/jobs")

    assert status == 202
    assert calls == [task_path.resolve()]
    assert job["status"] in {"queued", "running", "succeeded"}
    assert final_job["result"]["series_id"] == "paper-cuts"
    assert final_job["result"]["episode_number"] == 1
    assert final_job["result"]["checkpoint_dir"] == "data/litrpg/checkpoints/paper-cuts"
    assert "ignored_large_payload" not in final_job["result"]
    assert final_job["checkpoint_paths"] == [
        "part-1.json",
        "part-1_approved.xml",
        "data/litrpg/checkpoints/paper-cuts",
    ]
    assert final_job["error"] is None
    assert final_job["duration_seconds"] is not None
    assert list_status == 200
    assert list_data["jobs"][0]["job_id"] == job["job_id"]


def test_submit_inline_task_job_tracks_summary_and_status(
    ui_server, monkeypatch
):
    started = threading.Event()
    release = threading.Event()
    captured = []

    def fake_run_litrpg_task_data(task, *, base_dir, llm=None, tts=None):
        captured.append((task, base_dir))
        started.set()
        release.wait(timeout=2)
        return {
            "series_id": task["series_id"],
            "mode": task.get("mode", "episode"),
            "status": "cached",
            "audio_path": "data/litrpg/episodes/paper-cuts/episode-0001/audio/final.mp3",
        }

    monkeypatch.setattr(ui, "run_litrpg_task_data", fake_run_litrpg_task_data)

    status, data = request_json(
        ui_server,
        "POST",
        "/api/jobs",
        {
            "task": {
                "series_id": "paper-cuts",
                "premise": "A clerk descends into the office basement.",
                "mode": "episode",
                "render_audio": True,
                "generation": {"provider": "openai", "model": "gpt-5.5"},
                "tts": {"provider": "openai", "model": "gpt-4o-mini-tts"},
            }
        },
    )

    job = data["job"]
    assert started.wait(timeout=2)
    poll_status, poll_data = request_json(ui_server, "GET", f"/api/jobs/{job['job_id']}")
    release.set()
    final_job = wait_for_job(ui_server, job["job_id"], "succeeded")

    assert status == 202
    assert poll_status == 200
    assert job["task_id"] == job["job_id"]
    assert job["task_path"] is None
    assert job["task_summary"]["source"] == "inline"
    assert job["task_summary"]["generation_provider"] == "openai"
    assert job["task_summary"]["tts_provider"] == "openai"
    assert poll_data["job"]["phase"] == "running"
    assert final_job["phase"] == "complete"
    assert final_job["result"]["status"] == "cached"
    assert captured[0][0]["series_id"] == "paper-cuts"
    assert captured[0][1] == ui.PROJECT_ROOT


def test_submit_task_job_exposes_running_status(
    ui_server, ui_roots, monkeypatch
):
    task_path = ui_roots / "usage" / "litrpg_task.json"
    task_path.write_text("{}", encoding="utf-8")
    started = threading.Event()
    release = threading.Event()

    def fake_run_litrpg_task(path):
        started.set()
        release.wait(timeout=2)
        return {"series_id": "paper-cuts"}

    monkeypatch.setattr(ui, "run_litrpg_task", fake_run_litrpg_task)

    status, data = request_json(
        ui_server, "POST", "/api/jobs", {"path": "usage/litrpg_task.json"}
    )
    job_id = data["job"]["job_id"]
    assert started.wait(timeout=2)
    poll_status, poll_data = request_json(ui_server, "GET", f"/api/jobs/{job_id}")
    release.set()
    final_job = wait_for_job(ui_server, job_id, "succeeded")

    assert status == 202
    assert poll_status == 200
    assert poll_data["job"]["status"] == "running"
    assert final_job["status"] == "succeeded"


def test_submit_task_job_rejects_path_and_task_together(ui_server):
    status, data = request_json(
        ui_server,
        "POST",
        "/api/jobs",
        {"path": "usage/litrpg_task.json", "task": {"series_id": "paper-cuts"}},
    )

    assert status == 400
    assert "either path or task" in data["error"]


def test_submit_task_job_captures_errors(
    ui_server, ui_roots, monkeypatch
):
    task_path = ui_roots / "usage" / "litrpg_task.json"
    task_path.write_text("{}", encoding="utf-8")

    def fake_run_litrpg_task(path):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ui, "run_litrpg_task", fake_run_litrpg_task)

    status, data = request_json(
        ui_server, "POST", "/api/jobs", {"path": "usage/litrpg_task.json"}
    )
    final_job = wait_for_job(ui_server, data["job"]["job_id"], "failed")

    assert status == 202
    assert final_job["result"] is None
    assert final_job["error"] == "RuntimeError: provider unavailable"


def test_poll_unknown_job_returns_404(ui_server):
    status, data = request_json(ui_server, "GET", "/api/jobs/not-real")

    assert status == 404
    assert data["error"] == "Job not found"


def test_library_lists_audio_and_audio_endpoint_serves_only_data_dir(
    ui_server, ui_roots
):
    episode_dir = (
        ui_roots / "data" / "litrpg" / "episodes" / "paper-cuts" / "episode-0001"
    )
    audio_dir = episode_dir / "audio"
    audio_dir.mkdir(parents=True)
    (episode_dir / "metadata.json").write_text(
        json.dumps(
            {
                "episode_id": "episode-0001",
                "episode_number": 1,
                "files": {"script": "script.xml"},
                "prompt": "A clerk finds a dungeon.",
                "qa": {"ready": True, "status": "ready"},
                "series_id": "paper-cuts",
            }
        ),
        encoding="utf-8",
    )
    (episode_dir / "config.json").write_text(json.dumps({"minutes": 2}), encoding="utf-8")
    (episode_dir / "script.xml").write_text("<NARRATOR>Begin.</NARRATOR>", encoding="utf-8")
    audio_path = audio_dir / "final.mp3"
    audio_path.write_bytes(b"audio-bytes")
    (episode_dir / "audio_metadata.json").write_text(
        json.dumps({"audio_path": str(audio_path), "format": "mp3"}),
        encoding="utf-8",
    )

    status, data = request_json(ui_server, "GET", "/api/library")
    audio = data["library"][0]["episodes"][0]["audio"]
    audio_status, body, content_type = request_bytes(ui_server, audio["url"])

    assert status == 200
    assert data["library"][0]["title"] == "Paper Cuts"
    assert data["library"][0]["episodes"][0]["status"] == "complete"
    assert data["library"][0]["episodes"][0]["qa"] == {"ready": True, "status": "ready"}
    assert audio["path"] == "episodes/paper-cuts/episode-0001/audio/final.mp3"
    assert audio["url"] == "/audio?series_id=paper-cuts&episode_id=episode-0001"
    assert audio_status == 200
    assert body == b"audio-bytes"
    assert content_type == "audio/mpeg"


def test_resolve_audio_path_blocks_traversal(ui_roots):
    with pytest.raises(ValueError, match="inside data/litrpg"):
        ui.resolve_audio_path("../secret.mp3")


def test_audio_endpoint_rejects_unsafe_series_id(ui_server):
    status, body, _content_type = request_bytes(
        ui_server, "/audio?series_id=..&episode_id=episode-0001"
    )

    assert status == 400
    assert b"Unsafe path segment" in body
