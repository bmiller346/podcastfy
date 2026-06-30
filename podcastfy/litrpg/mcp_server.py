"""Thin MCP-facing control surface for the LitRPG story engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from podcastfy.litrpg.agent_state import load_agent_state
from podcastfy.litrpg.effect_log import effect_log_path, read_effect_log as read_effect_log_entries
from podcastfy.litrpg.handoff import HANDOFF_FILENAME
from podcastfy.litrpg.premise_intake import run_premise_intake
from podcastfy.litrpg.series_architect import SeriesArchitect
from podcastfy.litrpg.task import run_litrpg_task, run_litrpg_task_data

try:  # pragma: no cover - exercised only when the optional SDK is installed.
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - default test environment has no MCP SDK.
    FastMCP = None  # type: ignore[assignment]


MCP_IMPORT_ERROR = (
    "The Python MCP SDK is not installed. Install the optional 'mcp' package to "
    "run podcastfy.litrpg.mcp_server as an MCP server; normal LitRPG imports do not require it."
)


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "bootstrap_from_premise": {
        "description": "Bootstrap durable story-engine files from a raw premise dump.",
        "required": ["storage_dir", "series_id"],
        "properties": {
            "storage_dir": {"type": "string"},
            "series_id": {"type": "string"},
            "premise": {"type": "string"},
            "premise_path": {"type": "string"},
            "target_books": {"type": "integer", "default": 1},
            "chapters_per_book": {"type": "integer", "default": 30},
            "series_title": {"type": "string"},
            "generation": {"type": "object"},
        },
    },
    "get_chapter_contract": {
        "description": "Return the persisted series-architect contract for one chapter.",
        "required": ["storage_dir", "series_id"],
        "properties": {
            "storage_dir": {"type": "string"},
            "series_id": {"type": "string"},
            "book_number": {"type": "integer", "default": 1},
            "chapter_number": {"type": "integer", "default": 1},
        },
    },
    "list_series_artifacts": {
        "description": "List known durable files for a bootstrapped series.",
        "required": ["storage_dir", "series_id"],
        "properties": {
            "storage_dir": {"type": "string"},
            "series_id": {"type": "string"},
        },
    },
    "run_litrpg_task": {
        "description": "Run an existing LitRPG task file or inline task payload.",
        "required": [],
        "properties": {
            "task": {"type": "object"},
            "task_path": {"type": "string"},
            "base_dir": {"type": "string"},
        },
    },
    "get_agent_state": {
        "description": "Return durable agent queues for a LitRPG series.",
        "required": ["storage_dir", "series_id"],
        "properties": {
            "storage_dir": {"type": "string"},
            "series_id": {"type": "string"},
        },
    },
    "list_quarantine_records": {
        "description": "List scarcity/quarantine records for one book.",
        "required": ["storage_dir", "series_id"],
        "properties": {
            "storage_dir": {"type": "string"},
            "series_id": {"type": "string"},
            "book_number": {"type": "integer", "default": 1},
        },
    },
    "read_effect_log": {
        "description": "Read recent effect log entries for a LitRPG series.",
        "required": ["storage_dir", "series_id"],
        "properties": {
            "storage_dir": {"type": "string"},
            "series_id": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        },
    },
    "get_book_handoff": {
        "description": "Return the deterministic HANDOFF.md for one book when present.",
        "required": ["storage_dir", "series_id"],
        "properties": {
            "storage_dir": {"type": "string"},
            "series_id": {"type": "string"},
            "book_number": {"type": "integer", "default": 1},
        },
    },
}


def list_mcp_tool_schemas() -> dict[str, dict[str, Any]]:
    """Return MCP tool contracts without requiring the optional MCP SDK."""

    return json.loads(json.dumps(TOOL_SCHEMAS))


def bootstrap_from_premise(
    *,
    storage_dir: str,
    series_id: str,
    premise: str = "",
    premise_path: str = "",
    target_books: int = 1,
    chapters_per_book: int = 30,
    series_title: str = "",
    series_promise: str = "",
    endgame_direction: str = "",
    book_length_mode: str = "tight",
    arc_style: str = "escalating_floor_survival",
    power_curve: str = "logarithmic",
    merge_existing: bool = True,
    generation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bootstrap durable story-engine files from a raw premise dump."""

    premise_text = _premise_text(premise=premise, premise_path=premise_path)
    llm = _llm_from_generation(generation)
    result = run_premise_intake(
        storage_dir=storage_dir,
        series_id=series_id,
        premise=premise_text,
        llm=llm,
        target_books=target_books,
        chapters_per_book=chapters_per_book,
        book_length_mode=book_length_mode,
        arc_style=arc_style,
        series_title=series_title,
        series_promise=series_promise,
        endgame_direction=endgame_direction,
        power_curve=power_curve,
        merge_existing=merge_existing,
    )
    payload = result.to_dict()
    payload["artifact_paths"] = list_series_artifacts(
        storage_dir=storage_dir,
        series_id=series_id,
    )["artifacts"]
    return payload


def get_chapter_contract(
    *,
    storage_dir: str,
    series_id: str,
    book_number: int = 1,
    chapter_number: int = 1,
) -> dict[str, Any]:
    """Return the persisted series-architect contract for one chapter."""

    return SeriesArchitect(storage_dir, series_id).get_chapter_contract(
        book_number=book_number,
        chapter_number=chapter_number,
    )


def list_series_artifacts(*, storage_dir: str, series_id: str) -> dict[str, Any]:
    """List known durable files for a bootstrapped series."""

    root = Path(storage_dir) / "series" / str(series_id)
    artifacts = [
        str(path)
        for path in sorted(root.rglob("*.json"))
        if path.is_file() and _is_relative_to(path.resolve(), root.resolve())
    ]
    return {
        "series_id": str(series_id),
        "storage_dir": str(storage_dir),
        "series_root": str(root),
        "artifacts": artifacts,
    }


def run_litrpg_task_tool(
    *,
    task: Mapping[str, Any] | None = None,
    task_path: str = "",
    base_dir: str = "",
) -> dict[str, Any]:
    """Run an existing LitRPG task file or inline task payload."""

    if task is not None and task_path:
        raise ValueError("Provide either task or task_path, not both")
    if task is not None:
        return run_litrpg_task_data(task, base_dir=base_dir or None)
    if task_path:
        return run_litrpg_task(task_path)
    raise ValueError("run_litrpg_task requires task or task_path")


def get_agent_state(*, storage_dir: str, series_id: str) -> dict[str, Any]:
    """Return durable agent queues for a series."""

    return load_agent_state(storage_dir, series_id)


def list_quarantine_records(
    *,
    storage_dir: str,
    series_id: str,
    book_number: int = 1,
) -> dict[str, Any]:
    """List persisted quarantine records for one book."""

    root = Path(storage_dir) / "series" / str(series_id) / f"book_{int(book_number)}" / "quarantine"
    records = []
    for path in sorted(root.glob("chapter_*_attempt_*.json")):
        payload = _read_json_object(path)
        if payload:
            payload["path"] = str(path)
            records.append(payload)
    return {
        "series_id": str(series_id),
        "book_number": int(book_number),
        "records": records,
    }


def read_effect_log(*, storage_dir: str, series_id: str, limit: int = 20) -> dict[str, Any]:
    """Read recent effect log entries for a series."""

    entries = [
        entry.to_dict()
        for entry in read_effect_log_entries(effect_log_path(storage_dir, series_id))
    ]
    bounded = max(0, int(limit))
    return {
        "series_id": str(series_id),
        "path": str(effect_log_path(storage_dir, series_id)),
        "entries": entries[-bounded:] if bounded else [],
    }


def get_book_handoff(
    *,
    storage_dir: str,
    series_id: str,
    book_number: int = 1,
) -> dict[str, Any]:
    """Return the deterministic HANDOFF.md for one book when present."""

    path = Path(storage_dir) / "series" / str(series_id) / f"book_{int(book_number)}" / HANDOFF_FILENAME
    exists = path.exists()
    return {
        "series_id": str(series_id),
        "book_number": int(book_number),
        "path": str(path),
        "exists": exists,
        "text": path.read_text(encoding="utf-8") if exists else "",
    }


def create_mcp_server(name: str = "podcastfy-litrpg") -> Any:
    """Create and register the optional MCP server instance."""

    if FastMCP is None:
        raise RuntimeError(MCP_IMPORT_ERROR)
    server = FastMCP(name)
    server.tool()(bootstrap_from_premise)
    server.tool()(get_chapter_contract)
    server.tool()(list_series_artifacts)
    server.tool(name="run_litrpg_task")(run_litrpg_task_tool)
    server.tool()(get_agent_state)
    server.tool()(list_quarantine_records)
    server.tool()(read_effect_log)
    server.tool()(get_book_handoff)
    return server


def main() -> None:
    """Run the MCP server if the optional SDK is available."""

    create_mcp_server().run()


def _premise_text(*, premise: str, premise_path: str) -> str:
    text = str(premise or "").strip()
    path_text = str(premise_path or "").strip()
    if text and path_text:
        raise ValueError("Provide either premise or premise_path, not both")
    if path_text:
        text = Path(path_text).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("bootstrap_from_premise requires premise or premise_path")
    return text


def _llm_from_generation(generation: Mapping[str, Any] | None) -> Any:
    config = dict(generation or {})
    if config.get("static_response") is not None:
        return _StaticLLM(str(config["static_response"]))
    if config.get("static_payload") is not None:
        return _StaticLLM(json.dumps(config["static_payload"]))
    from podcastfy.litrpg.task import _llm_from_task
    from podcastfy.litrpg.settings import load_litrpg_settings

    return _llm_from_task({"generation": config}, settings=load_litrpg_settings(None))


class _StaticLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, *, prompt: str, stage: str) -> str:
        return self.response


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else {}


if __name__ == "__main__":
    main()
