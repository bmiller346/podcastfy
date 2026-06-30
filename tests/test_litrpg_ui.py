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


def request_bytes_with_headers(server, path):
    connection = http.client.HTTPConnection(server.server_address[0], server.server_address[1])
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
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
    assert 'id="refresh-robust-state"' in html
    assert 'id="robust-book-number"' in html
    assert 'id="series-status"' in html
    assert 'id="robust-state-panel"' in html
    assert 'id="robust-state-summary"' in html
    assert 'id="robust-effect-history"' in html
    assert 'id="approve-harness-stage"' in html
    assert 'id="rerun-quarantined-rewrite"' in html
    assert 'id="open-handoff"' in html
    assert 'id="handoff-preview"' in html
    assert 'id="studio-flow"' in html
    assert 'id="next-actions"' in html
    assert 'id="job-console"' in html
    assert 'id="messy-context"' in html
    assert 'id="revision-chat-log"' in html
    assert 'id="revision-chat-input"' in html
    assert 'id="append-revision-note"' in html
    assert 'id="clear-revision-note"' in html
    assert 'id="revision-proposal"' in html
    assert 'id="accept-revision-proposal"' in html
    assert 'id="discard-revision-proposal"' in html
    assert 'id="markdown-split"' in html
    assert 'id="markdown-wide"' in html
    assert 'id="markdown-focus"' in html
    assert 'id="markdown-full"' in html
    assert 'id="story-seed-path"' in html
    assert 'id="story-seed-status"' in html
    assert 'id="load-story-seed"' in html
    assert 'id="save-story-seed"' in html
    assert 'id="apply-messy-context"' in html
    assert 'id="queue-premise-intake"' in html
    assert 'id="copy-mcp-context"' in html
    assert 'id="premise-intake-result"' in html
    assert 'id="messy-context-summary"' in html
    assert "1. Premise Intake" in html
    assert "2. Intake Status" in html
    assert "3. Series Workspace" in html
    assert "Advanced Task Builder" in html
    assert "Auto-route cloud model by intent" in html
    assert "Premise Intake -> Run Premise Intake -> Load Series" in html
    assert "Story file" in html
    assert "usage/litrpg_messy_context_seed.md" in html
    assert "Revision Chat" in html
    assert "Propose Markdown Change" in html
    assert "Accept Proposal" in html
    assert "Discard" in html
    assert "Load Seed Markdown" in html
    assert "Save Seed Markdown" in html
    assert "Run Premise Intake" in html
    assert "Copy MCP Payload" in html
    assert "Optional Rough Autofill" in html
    assert "readable source of truth" in html
    assert "Premise intake has not run in this session." in html
    assert "Short premise override" in html
    assert "only an override/debug summary" in html
    assert "readable source of truth" in html
    assert 'id="task-form"' in html
    assert "Leave blank to keep existing key" in html
    assert 'name="series_id"' in html
    assert 'name="premise"' in html
    assert 'name="mode"' in html
    assert 'value="premise_intake"' in html
    assert 'name="series_title"' in html
    assert 'name="premise_path"' in html
    assert 'name="target_books"' in html
    assert 'name="chapters_per_book"' in html
    assert 'name="book_number"' in html
    assert 'name="chapter_number"' in html
    assert 'name="target_minutes"' in html
    assert 'name="max_rewrite_attempts"' in html
    assert 'name="series_promise"' in html
    assert 'name="endgame_direction"' in html
    assert 'name="genre"' in html
    assert 'name="book_length_mode"' in html
    assert 'value="tight"' in html
    assert 'name="arc_style"' in html
    assert 'value="escalating_floor_survival"' in html
    assert 'name="power_curve"' in html
    assert 'value="logarithmic"' in html
    assert 'name="generation_provider"' in html
    assert "Use settings default provider" in html
    assert "hybrid auto" in html
    assert 'value="hybrid"' in html
    assert 'value="gemini"' in html
    assert 'value="openai"' in html
    assert 'value="ollama"' in html
    assert 'name="generation_model"' in html
    assert 'name="generation_model_custom"' in html
    assert 'name="auto_model_routing"' in html
    assert 'name="tts_provider"' in html
    assert 'value="elevenlabs"' in html
    assert 'value="geminiapi"' in html
    assert 'name="tts_model"' in html
    assert 'name="tts_model_custom"' in html
    assert 'name="tts_format"' in html
    assert 'value="mp3"' in html
    assert 'value="wav"' in html
    assert 'value="opus"' in html
    assert 'name="render_audio"' in html
    assert 'name="harness_enabled"' in html
    assert 'name="rewrite_quarantined"' in html
    assert 'name="generate_handoff"' in html
    assert 'name="result_path"' in html
    assert 'name="checkpoint_dir"' in html
    assert 'name="storage_dir"' in html
    assert 'placeholder="data/litrpg"' in html
    assert 'placeholder="data/litrpg/paper-cuts/latest.json"' in html
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
    assert 'id="package-radar"' in html
    assert 'id="package-output"' in html
    assert 'id="role-package-panel"' in html
    assert 'id="role-list"' in html
    assert 'id="add-role"' in html
    assert 'id="rebuild-roles"' in html
    assert 'id="save-roles"' in html


def test_ui_static_assets_are_not_cached_during_local_dev(ui_server):
    index_status, _, index_headers = request_bytes_with_headers(ui_server, "/")
    app_status, _, app_headers = request_bytes_with_headers(ui_server, "/static/app.js")

    assert index_status == 200
    assert app_status == 200
    assert "no-store" in index_headers["Cache-Control"]
    assert "no-store" in app_headers["Cache-Control"]


def test_favicon_request_is_ignored_without_404_noise(ui_server):
    status, body, content_type = request_bytes(ui_server, "/favicon.ico")

    assert status == 204
    assert body == b""
    assert content_type is None


def test_story_seed_api_loads_and_saves_markdown(ui_server, ui_roots):
    seed_path = ui_roots / "usage" / "litrpg_messy_context_seed.md"
    seed_path.write_text("# Seed\n\nSophie II survives.", encoding="utf-8")

    status, data = request_json(
        ui_server,
        "GET",
        "/api/story-seed?path=usage/litrpg_messy_context_seed.md",
    )

    assert status == 200
    assert data["exists"] is True
    assert data["text"] == "# Seed\n\nSophie II survives."

    save_status, save_data = request_json(
        ui_server,
        "POST",
        "/api/story-seed",
        {
            "path": "usage/litrpg_messy_context_seed.md",
            "text": "# Updated\n\nThe System remembers Sophie.",
        },
    )

    assert save_status == 200
    assert save_data["ok"] is True
    assert seed_path.read_text(encoding="utf-8") == "# Updated\n\nThe System remembers Sophie."


def test_story_seed_api_rejects_paths_outside_usage(ui_server):
    status, data = request_json(
        ui_server,
        "POST",
        "/api/story-seed",
        {"path": "../outside.md", "text": "nope"},
    )

    assert status == 400
    assert "inside usage" in data["error"]


def test_story_seed_propose_uses_llm_and_returns_revised_markdown(ui_server, monkeypatch):
    captured = {}

    class FakeLLM:
        def generate(self, *, prompt, stage):
            captured["prompt"] = prompt
            captured["stage"] = stage
            return json.dumps(
                {
                    "summary": "Renamed the boat.",
                    "revised_markdown": "# Seed\n\nCanonical vessel name: Sophie II",
                }
            )

    def fake_llm_from_task(task, *, settings):
        captured["task"] = task
        return FakeLLM()

    monkeypatch.setattr(ui, "_llm_from_task", fake_llm_from_task)

    status, data = request_json(
        ui_server,
        "POST",
        "/api/story-seed/propose",
        {
            "markdown": "# Seed\n\nCanonical vessel name: Old Name",
            "instruction": "Rename the boat to Sophie II.",
            "generation": {"provider": "ollama", "ollama_model": "test-model"},
        },
    )

    assert status == 200
    assert data["summary"] == "Renamed the boat."
    assert data["revised_markdown"] == "# Seed\n\nCanonical vessel name: Sophie II"
    assert data["provider"] == "ollama"
    assert data["model"] == "test-model"
    assert captured["stage"] == "story_seed_revision"
    assert "Rename the boat to Sophie II." in captured["prompt"]
    assert captured["task"]["generation"]["ollama_model"] == "test-model"


def test_story_seed_propose_appends_patch_markdown(ui_server, monkeypatch):
    class FakeLLM:
        def generate(self, *, prompt, stage):
            return json.dumps(
                {
                    "summary": "Added Sophie guilt anchor.",
                    "patch_markdown": "## AI Notes\n\nStrengthen Sophie's death as a guilt anchor.",
                }
            )

    monkeypatch.setattr(ui, "_llm_from_task", lambda task, *, settings: FakeLLM())

    status, data = request_json(
        ui_server,
        "POST",
        "/api/story-seed/propose",
        {
            "markdown": "# Seed\n\nExisting canon.",
            "instruction": "Add Sophie guilt anchor.",
            "generation": {"provider": "ollama", "ollama_model": "test-model"},
        },
    )

    assert status == 200
    assert data["patch_markdown"] == "## AI Notes\n\nStrengthen Sophie's death as a guilt anchor."
    assert data["revised_markdown"] == (
        "# Seed\n\nExisting canon.\n\n"
        "## AI Notes\n\nStrengthen Sophie's death as a guilt anchor.\n"
    )


def test_story_seed_default_revision_model_uses_hermes():
    generation = ui._default_story_revision_generation()

    assert generation["provider"] == "ollama"
    assert generation["ollama_model"] == "hermes3:latest"
    assert generation["ollama_options"]["temperature"] == 0.25
    assert generation["ollama_options"]["num_predict"] == 700


def test_story_seed_revision_extracts_loose_json_with_markdown_newlines():
    raw = '{\n  "summary": "Added Sophie pressure.",\n  "patch_markdown": "## AI Notes\n\nSophie now echoes through Kelli guilt."\n}'

    proposal = ui.extract_story_seed_revision(raw)

    assert proposal["summary"] == "Added Sophie pressure."
    assert proposal["patch_markdown"] == "## AI Notes\n\nSophie now echoes through Kelli guilt."


def test_story_seed_propose_treats_raw_markdown_as_patch(ui_server, monkeypatch):
    class FakeLLM:
        def generate(self, *, prompt, stage):
            return "## AI Notes\n\nRaw model markdown patch."

    monkeypatch.setattr(ui, "_llm_from_task", lambda task, *, settings: FakeLLM())

    status, data = request_json(
        ui_server,
        "POST",
        "/api/story-seed/propose",
        {
            "markdown": "# Seed\n\nExisting canon.",
            "instruction": "Add a note.",
            "generation": {"provider": "ollama", "ollama_model": "test-model"},
        },
    )

    assert status == 200
    assert data["patch_markdown"] == "## AI Notes\n\nRaw model markdown patch."
    assert data["revised_markdown"] == "# Seed\n\nExisting canon.\n\n## AI Notes\n\nRaw model markdown patch.\n"


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


def test_series_package_load_returns_intake_artifact_workspace(ui_server, ui_roots):
    series_root = ui_roots / "data" / "litrpg" / "series" / "the-knotty-buoy"
    (series_root / "book_1").mkdir(parents=True)
    (series_root / "series_plan.json").write_text(
        json.dumps({"series_title": "The Knotty Buoy", "chapters_per_book": 30}),
        encoding="utf-8",
    )
    (series_root / "book_1" / "chapter_outline.json").write_text(
        json.dumps([{"chapter": 1, "title": "Out of the Atlantic", "premise": "Drop."}]),
        encoding="utf-8",
    )
    (series_root / "story_bible.json").write_text(
        json.dumps(
            {
                "premise": "Edward and Kelli sail Sophie II.",
                "characters": {
                    "Edward Marsh": {"name": "Edward Marsh", "voice_rules": ["gruff"]},
                    "Kelli Marsh": {"name": "Kelli Marsh", "voice_rules": ["sharp"]},
                    "Pedro": {"name": "Pedro", "voice_rules": ["phrase-bank"]},
                },
            }
        ),
        encoding="utf-8",
    )
    (series_root / "world_register.json").write_text(
        json.dumps(
            {
                "locations": [{"name": "Sophie II", "detail": "Mobile home base.", "tags": ["vehicle"]}],
                "rules": [{"rule": "Navigable waters mutate by floor"}],
                "entity_ecology": [{"entity": "OSHA Wraiths", "detail": "Violation debuffs."}],
            }
        ),
        encoding="utf-8",
    )
    (series_root / "voice_cards.json").write_text(
        json.dumps({"series_id": "the-knotty-buoy", "cards": {}}),
        encoding="utf-8",
    )
    (series_root / "foreshadow_ledger.json").write_text(
        json.dumps({"series_id": "the-knotty-buoy", "planted": [], "ready_to_pay": []}),
        encoding="utf-8",
    )

    status, data = request_json(
        ui_server,
        "GET",
        "/api/series-package?series_id=the-knotty-buoy",
    )

    assert status == 200
    assert data["available"] is True
    assert data["status"] == "artifact_workspace"
    assert data["package"]["series_plan"]["series_title"] == "The Knotty Buoy"
    assert data["package"]["chapter_outline"][0]["title"] == "Out of the Atlantic"
    assert data["package"]["story_bible"]["characters"]["Pedro"]["name"] == "Pedro"
    assert data["package"]["world_register"]["entity_ecology"][0]["entity"] == "OSHA Wraiths"
    assert data["package"]["voice_cards"]["cards"]["Pedro"]["sample_lines"] == ["WHERE'S THE PERMIT?"]
    assert data["package"]["foreshadow_ledger"]["planted"]
    assert [item["name"] for item in data["package"]["characters"]] == [
        "Edward Marsh",
        "Kelli Marsh",
        "Pedro",
    ]
    assert data["package"]["home_base"]["name"] == "Sophie II"
    assert data["package"]["bestiary"][0]["name"] == "OSHA Wraiths"
    assert set(data["package"]["metadata"]["derived_artifacts"]) >= {"voice_cards", "foreshadow_ledger"}


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


def test_series_package_generate_reports_unavailable_without_generator(ui_server, monkeypatch):
    def unavailable_generator(**kwargs):
        raise RuntimeError("Series package generator is not installed yet")

    monkeypatch.setattr(ui, "generate_series_package", unavailable_generator)

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
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    status, data = request_json(
        ui_server,
        "POST",
        "/api/settings",
        {
            "openai_api_key": "sk-file",
            "gemini_api_key": "",
            "default_tts_provider": "edge",
            "default_model": "gpt-5.4",
            "default_tts_model": "gpt-4o-mini-tts",
            "default_tts_format": "mp3",
            "unexpected": "ignored",
        },
    )

    settings_path = ui_roots / "data" / "litrpg" / "settings.json"
    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert status == 200
    assert stored == {
        "default_model": "gpt-5.4",
        "default_tts_format": "mp3",
        "default_tts_model": "gpt-4o-mini-tts",
        "default_tts_provider": "edge",
        "openai_api_key": "sk-file",
    }
    assert data["settings_path"] == str(settings_path)
    assert data["api_keys"]["openai"]["configured"] is True
    assert data["api_keys"]["openai"]["value"] == "redacted"
    assert data["defaults"]["default_model"] == "gpt-5.4"
    assert data["defaults"]["default_tts_model"] == "gpt-4o-mini-tts"
    assert data["defaults"]["default_tts_format"] == "mp3"
    assert "sk-file" not in json.dumps(data)
    assert "sk-env" not in json.dumps(data)


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
                "openai_api_key": "sk-openai-secret",
                "default_model": "gpt-5.4",
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
    assert stored == {"openai_api_key": "sk-openai-secret"}
    assert data["defaults"]["default_model"] == ""
    assert data["defaults"]["default_tts_format"] == ""
    assert data["api_keys"]["openai"]["configured"] is True


def test_settings_post_rejects_malformed_openai_key(ui_server):
    status, data = request_json(
        ui_server,
        "POST",
        "/api/settings",
        {"openai_api_key": "this is pasted prose, not a key"},
    )

    assert status == 400
    assert "Invalid API key format for openai_api_key" in data["error"]


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
            "status": "approval_required",
            "harness_decision": {
                "stage": "chapter_generation",
                "allowed": False,
                "requires_human_approval": True,
                "approved": False,
                "estimated_cost_usd": 0.09,
                "reason": "Stage requires human approval.",
                "policy": {"requires_human_approval": True},
            },
            "quarantine": {
                "status": "quarantined",
                "path": "data/litrpg/series/paper-cuts/book_1/quarantine/chapter_001_attempt_001.json",
                "rewrite_instruction": "Remove the reveal.",
            },
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
    assert final_job["result"]["status"] == "approval_required"
    assert final_job["result"]["harness_decision"]["stage"] == "chapter_generation"
    assert final_job["result"]["quarantine"]["rewrite_instruction"] == "Remove the reveal."
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


def test_robust_state_endpoint_exposes_agent_quarantine_handoff_and_effects(ui_server, ui_roots):
    from podcastfy.litrpg.effect_log import append_effect_log_entry
    from podcastfy.litrpg.effect_log import build_effect_log_entry
    from podcastfy.litrpg.effect_log import effect_log_path

    series_root = ui_roots / "data" / "litrpg" / "series" / "paper-cuts"
    book_root = series_root / "book_1"
    quarantine_root = book_root / "quarantine"
    quarantine_root.mkdir(parents=True)
    (series_root / "agent_state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "series_id": "paper-cuts",
                "now": [],
                "next": [],
                "blocked": [
                    {
                        "id": "blocked:chapter:12",
                        "kind": "quarantine_blocker",
                        "summary": "Chapter 12 is blocked by quarantine.",
                        "source": "quarantine",
                        "priority": 1,
                        "metadata": {"chapter_number": 12},
                    }
                ],
                "improve": [],
                "recurring": [],
                "updated_at": "2026-06-29T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (quarantine_root / "chapter_012_attempt_004.json").write_text(
        json.dumps(
            {
                "status": "blocked",
                "chapter_number": 12,
                "attempt": 4,
                "rewrite_instruction": "Remove the sponsor reveal.",
            }
        ),
        encoding="utf-8",
    )
    (book_root / "HANDOFF.md").write_text(
        "# HANDOFF: Paper Cuts Book 1\n\n## Pending human decisions\n- Fix Chapter 12",
        encoding="utf-8",
    )
    append_effect_log_entry(
        effect_log_path(ui.DATA_DIR, "paper-cuts"),
        build_effect_log_entry(
            series_id="paper-cuts",
            book_number=1,
            chapter_number=12,
            stage="chapter_generation",
            input_payload={"chapter": 12},
            output_payload={"status": "blocked"},
            provider="fake",
            model="unit",
            estimated_cost_usd=0.13,
        ),
    )

    status, data = request_json(
        ui_server,
        "GET",
        "/api/robust-state?series_id=paper-cuts&book_number=1",
    )

    assert status == 200
    assert data["blocked"][0]["kind"] == "quarantine_blocker"
    assert data["quarantine"]["latest"]["status"] == "blocked"
    assert data["quarantine"]["latest"]["rewrite_instruction"] == "Remove the sponsor reveal."
    assert data["handoff"]["path"] == "data/litrpg/series/paper-cuts/book_1/HANDOFF.md"
    assert "Fix Chapter 12" in data["handoff"]["text"]
    assert data["effect_log"]["recent"][0]["stage"] == "chapter_generation"
    assert data["effect_log"]["committed_cost_usd"] == 0.13


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
                "generation": {"provider": "openai", "model": "gpt-5.4"},
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


def test_submit_premise_intake_job_routes_to_task_data(ui_server, monkeypatch):
    captured = []

    def fake_run_litrpg_task_data(task, *, base_dir, llm=None, tts=None):
        captured.append((task, base_dir, llm, tts))
        return {
            "series_id": task["series_id"],
            "mode": task["mode"],
            "written_files": ["data/litrpg/series/knotty/series_plan.json"],
        }

    monkeypatch.setattr(ui, "run_litrpg_task_data", fake_run_litrpg_task_data)

    status, data = request_json(
        ui_server,
        "POST",
        "/api/jobs",
        {
            "task": {
                "mode": "premise_intake",
                "series_id": "knotty",
                "premise": "A large pasted outline.",
                "series_title": "The Knotty Buoy",
                "target_books": 1,
                "chapters_per_book": 30,
            }
        },
    )

    final_job = wait_for_job(ui_server, data["job"]["job_id"], "succeeded")

    assert status == 202
    assert captured[0][0]["mode"] == "premise_intake"
    assert captured[0][0]["series_title"] == "The Knotty Buoy"
    assert captured[0][1] == ui.PROJECT_ROOT
    assert final_job["result"]["written_files"] == [
        "data/litrpg/series/knotty/series_plan.json"
    ]
    assert final_job["checkpoint_paths"] == [
        "data/litrpg/series/knotty/series_plan.json"
    ]


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
