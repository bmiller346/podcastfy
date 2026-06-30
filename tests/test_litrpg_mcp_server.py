import importlib
import json

import pytest


def test_mcp_server_imports_without_optional_sdk():
    module = importlib.import_module("podcastfy.litrpg.mcp_server")

    assert module.MCP_IMPORT_ERROR.startswith("The Python MCP SDK is not installed")


def test_bootstrap_from_premise_uses_existing_intake_engine(tmp_path):
    from podcastfy.litrpg import mcp_server

    result = mcp_server.bootstrap_from_premise(
        storage_dir=str(tmp_path),
        series_id="mcp-series",
        premise="A tired carpenter gets a hostile quest log.",
        target_books=1,
        chapters_per_book=1,
        series_title="MCP Series",
        generation={
            "static_payload": {
                "series_shape": {"series_title": "MCP Series", "chapters_per_book": 1},
                "book_outlines": {
                    "1": [
                        {
                            "chapter": 1,
                            "title": "Wake Prompt",
                            "premise": "The first quest arrives.",
                        }
                    ]
                },
            }
        },
    )

    assert result["series_id"] == "mcp-series"
    assert any(path.endswith("series_plan.json") for path in result["written_files"])
    assert any(path.endswith("chapter_outline.json") for path in result["artifact_paths"])


def test_mcp_tool_schemas_are_available_without_sdk():
    from podcastfy.litrpg import mcp_server

    schemas = mcp_server.list_mcp_tool_schemas()

    assert schemas["bootstrap_from_premise"]["required"] == ["storage_dir", "series_id"]
    assert "premise_path" in schemas["bootstrap_from_premise"]["properties"]
    assert schemas["get_chapter_contract"]["properties"]["chapter_number"]["default"] == 1
    assert "task_path" in schemas["run_litrpg_task"]["properties"]
    assert schemas["get_agent_state"]["required"] == ["storage_dir", "series_id"]
    assert schemas["list_quarantine_records"]["properties"]["book_number"]["default"] == 1
    assert schemas["read_effect_log"]["properties"]["limit"]["default"] == 20
    assert schemas["get_book_handoff"]["properties"]["book_number"]["default"] == 1
    schemas["bootstrap_from_premise"]["required"].append("mutated")
    assert "mutated" not in mcp_server.TOOL_SCHEMAS["bootstrap_from_premise"]["required"]


def test_mcp_helpers_list_artifacts_and_contracts(tmp_path):
    from podcastfy.litrpg import mcp_server

    mcp_server.bootstrap_from_premise(
        storage_dir=str(tmp_path),
        series_id="contracts",
        premise="A pilot argues with a dungeon.",
        chapters_per_book=1,
        generation={
            "static_payload": {
                "series_shape": {"series_title": "Contracts", "chapters_per_book": 1},
                "book_outlines": {"1": [{"chapter": 1, "title": "Docking Fees"}]},
            }
        },
    )

    artifacts = mcp_server.list_series_artifacts(storage_dir=str(tmp_path), series_id="contracts")
    contract = mcp_server.get_chapter_contract(
        storage_dir=str(tmp_path),
        series_id="contracts",
        book_number=1,
        chapter_number=1,
    )

    assert artifacts["series_id"] == "contracts"
    assert any(path.endswith("series_arc.json") for path in artifacts["artifacts"])
    assert contract["title"] == "Docking Fees"


def test_mcp_helpers_expose_robust_state_files(tmp_path):
    from podcastfy.litrpg import mcp_server
    from podcastfy.litrpg.effect_log import append_effect_log_entry
    from podcastfy.litrpg.effect_log import build_effect_log_entry
    from podcastfy.litrpg.effect_log import effect_log_path

    series_root = tmp_path / "series" / "contracts"
    book_root = series_root / "book_1"
    quarantine_root = book_root / "quarantine"
    quarantine_root.mkdir(parents=True)
    (series_root / "agent_state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "series_id": "contracts",
                "now": [],
                "next": [],
                "blocked": [
                    {
                        "id": "blocked:chapter:2",
                        "kind": "quarantine_blocker",
                        "summary": "Chapter 2 blocked.",
                        "source": "quarantine",
                        "priority": 1,
                        "metadata": {"chapter_number": 2},
                    }
                ],
                "improve": [],
                "recurring": [],
                "updated_at": "2026-06-29T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (quarantine_root / "chapter_002_attempt_001.json").write_text(
        json.dumps(
            {
                "status": "quarantined",
                "chapter_number": 2,
                "attempt": 1,
                "rewrite_instruction": "Hide the answer.",
            }
        ),
        encoding="utf-8",
    )
    (book_root / "HANDOFF.md").write_text("# HANDOFF\n\n## Pending human decisions", encoding="utf-8")
    append_effect_log_entry(
        effect_log_path(tmp_path, "contracts"),
        build_effect_log_entry(
            series_id="contracts",
            book_number=1,
            chapter_number=2,
            stage="chapter_result_write",
            input_payload={"result": True},
            output_payload={"path": "result.json"},
            provider="fake",
            model="unit",
        ),
    )

    state = mcp_server.get_agent_state(storage_dir=str(tmp_path), series_id="contracts")
    quarantine = mcp_server.list_quarantine_records(
        storage_dir=str(tmp_path),
        series_id="contracts",
        book_number=1,
    )
    effects = mcp_server.read_effect_log(
        storage_dir=str(tmp_path),
        series_id="contracts",
        limit=1,
    )
    handoff = mcp_server.get_book_handoff(
        storage_dir=str(tmp_path),
        series_id="contracts",
        book_number=1,
    )

    assert state["blocked"][0]["kind"] == "quarantine_blocker"
    assert quarantine["records"][0]["rewrite_instruction"] == "Hide the answer."
    assert effects["entries"][0]["stage"] == "chapter_result_write"
    assert handoff["exists"] is True
    assert "Pending human decisions" in handoff["text"]


def test_create_mcp_server_fails_clearly_without_sdk(monkeypatch):
    from podcastfy.litrpg import mcp_server

    monkeypatch.setattr(mcp_server, "FastMCP", None)

    with pytest.raises(RuntimeError, match="Python MCP SDK is not installed"):
        mcp_server.create_mcp_server()


def test_create_mcp_server_registers_tools_when_sdk_present(monkeypatch):
    from podcastfy.litrpg import mcp_server

    class FakeFastMCP:
        def __init__(self, name):
            self.name = name
            self.tools = []

        def tool(self, name=None):
            def register(function):
                self.tools.append(name or function.__name__)
                return function

            return register

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    server = mcp_server.create_mcp_server("test-lit")

    assert server.name == "test-lit"
    assert server.tools == [
        "bootstrap_from_premise",
        "get_chapter_contract",
        "list_series_artifacts",
        "run_litrpg_task",
        "get_agent_state",
        "list_quarantine_records",
        "read_effect_log",
        "get_book_handoff",
    ]
