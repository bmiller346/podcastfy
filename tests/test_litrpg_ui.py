import http.client
import json
import threading
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
    monkeypatch.setattr(ui, "SETTINGS_PATH", project_root / "settings.local.json")
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
            "unexpected": "ignored",
        },
    )

    stored = json.loads((ui_roots / "settings.local.json").read_text(encoding="utf-8"))
    assert status == 200
    assert stored == {"default_tts_provider": "edge", "openai_api_key": "from-file"}
    assert data["api_keys"]["openai"]["configured"] is True
    assert data["api_keys"]["openai"]["value"] == "redacted"
    assert "from-file" not in json.dumps(data)
    assert "from-env" not in json.dumps(data)


def test_tasks_endpoint_lists_litrpg_json_files(ui_server, ui_roots):
    (ui_roots / "usage" / "litrpg_task.json").write_text("{}", encoding="utf-8")
    (ui_roots / "usage" / "notes.json").write_text("{}", encoding="utf-8")

    status, data = request_json(ui_server, "GET", "/api/tasks")

    assert status == 200
    assert data["tasks"] == [{"name": "litrpg_task.json", "path": "usage/litrpg_task.json"}]


def test_run_task_rejects_paths_outside_usage(ui_server, ui_roots):
    (ui_roots / "outside.json").write_text("{}", encoding="utf-8")

    status, data = request_json(
        ui_server, "POST", "/api/run-task", {"path": "../outside.json"}
    )

    assert status == 400
    assert "inside usage" in data["error"]


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
                "prompt": "A clerk finds a dungeon.",
                "series_id": "paper-cuts",
            }
        ),
        encoding="utf-8",
    )
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
    assert audio["path"] == "episodes/paper-cuts/episode-0001/audio/final.mp3"
    assert audio_status == 200
    assert body == b"audio-bytes"
    assert content_type == "audio/mpeg"


def test_resolve_audio_path_blocks_traversal(ui_roots):
    with pytest.raises(ValueError, match="inside data/litrpg"):
        ui.resolve_audio_path("../secret.mp3")
