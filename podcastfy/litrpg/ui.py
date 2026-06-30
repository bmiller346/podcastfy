"""Small stdlib HTTP UI for local LitRPG episode tasks."""

from __future__ import annotations

import argparse
import importlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from podcastfy.litrpg import library as episode_library
from podcastfy.litrpg.settings import (
    DEFAULT_SETTINGS_PATH,
    get_provider_api_key,
    load_litrpg_settings,
    redacted_litrpg_settings_status,
    save_litrpg_settings,
)
from podcastfy.litrpg.task import _llm_from_task, run_litrpg_task, run_litrpg_task_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USAGE_DIR = PROJECT_ROOT / "usage"
DATA_DIR = PROJECT_ROOT / "data" / "litrpg"
SETTINGS_PATH = DEFAULT_SETTINGS_PATH
STATIC_DIR = Path(__file__).resolve().parent / "static"
TASK_FILE_PREFIXES = ("litrpg", "story", "audio_story")
DEFAULT_STORY_SEED_PATH = "usage/litrpg_messy_context_seed.md"


@dataclass
class TaskJob:
    """Tracked background task started from the local UI."""

    job_id: str
    task_path: str | None = None
    task_id: str | None = None
    phase: str = "queued"
    status: str = "queued"
    task_summary: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    checkpoint_paths: list[str] = field(default_factory=list)


_JOBS: dict[str, TaskJob] = {}
_JOBS_LOCK = threading.Lock()


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server that releases the local dev port quickly after reload."""

    allow_reuse_address = True


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the LitRPG local UI until interrupted."""
    handler = partial(LitRPGUIHandler, directory=str(STATIC_DIR))
    server = ReusableThreadingHTTPServer((host, port), handler)
    print(f"LitRPG UI running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLitRPG UI stopped.")
    finally:
        server.server_close()


def run_server_with_reload(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the local UI in a restart-on-change development loop."""

    print(f"LitRPG UI reload watcher running at http://{host}:{port}/")
    process: subprocess.Popen[str] | None = None
    snapshot = _reload_snapshot()
    try:
        while True:
            if process is None or process.poll() is not None:
                process = _start_reload_child(host=host, port=port)
            time.sleep(1.0)
            next_snapshot = _reload_snapshot()
            if next_snapshot != snapshot:
                snapshot = next_snapshot
                print("Change detected. Restarting LitRPG UI...")
                _stop_reload_child(process)
                process = _start_reload_child(host=host, port=port)
    except KeyboardInterrupt:
        print("\nLitRPG UI reload watcher stopped.")
    finally:
        if process is not None:
            _stop_reload_child(process)


def _start_reload_child(*, host: str, port: int) -> subprocess.Popen[str]:
    env = dict(os.environ)
    env["LITRPG_UI_RELOAD_CHILD"] = "1"
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "podcastfy.litrpg.ui",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
    )


def _stop_reload_child(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _reload_snapshot() -> tuple[tuple[str, int, int], ...]:
    watched_roots = (PROJECT_ROOT / "podcastfy" / "litrpg",)
    watched_suffixes = {".py", ".html", ".js", ".css"}
    records: list[tuple[str, int, int]] = []
    for root in watched_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in watched_suffixes:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                records.append((_display_path(path), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(records))


class LitRPGUIHandler(SimpleHTTPRequestHandler):
    """HTTP handler for the local LitRPG app shell and JSON API."""

    server_version = "LitRPGUI/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if parsed.path == "/api/settings":
            return self._send_json(settings_status())
        if parsed.path == "/api/tasks":
            return self._send_json({"tasks": list_tasks()})
        if parsed.path == "/api/story-seed":
            params = parse_qs(parsed.query)
            try:
                return self._send_json(story_seed_response(params.get("path", [""])[0]))
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path == "/api/jobs":
            return self._send_json({"jobs": list_jobs()})
        if parsed.path.startswith("/api/jobs/"):
            try:
                return self._send_json(get_job_response(parsed.path.removeprefix("/api/jobs/")))
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.NOT_FOUND)
        if parsed.path == "/api/library/series":
            try:
                return self._send_json({"series": list_library_series()})
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path == "/api/library/episodes":
            params = parse_qs(parsed.query)
            try:
                return self._send_json(
                    {"episodes": list_library_episodes(params.get("series_id", [""])[0] or None)}
                )
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path.startswith("/api/library/episodes/"):
            try:
                relative = parsed.path.removeprefix("/api/library/episodes/").strip("/")
                series_id, episode_id = relative.split("/", 1)
                return self._send_json(
                    {"episode": get_library_episode(series_id=series_id, episode_id=episode_id)}
                )
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path == "/api/library":
            return self._send_json({"library": list_library()})
        if parsed.path == "/api/series-package":
            params = parse_qs(parsed.query)
            try:
                return self._send_json(series_package_response(params.get("series_id", [""])[0]))
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path == "/audio":
            try:
                return self._serve_audio(parsed.query)
            except ValueError as exc:
                return self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
        if parsed.path.startswith("/static/"):
            self.path = parsed.path.removeprefix("/static")
            return super().do_GET()
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        try:
            payload = self._read_json_body()
            if parsed.path == "/api/settings":
                write_settings(payload)
                return self._send_json(settings_status())
            if parsed.path == "/api/run-task":
                task_path, task_data = resolve_task_request(payload)
                result = _run_task_request(task_path=task_path, task_data=task_data)
                return self._send_json({"ok": True, "result": result})
            if parsed.path == "/api/jobs":
                task_path, task_data = resolve_task_request(payload)
                job = submit_task_job(task_path=task_path, task_data=task_data)
                return self._send_json(
                    {"ok": True, "job": serialize_job(job)},
                    HTTPStatus.ACCEPTED,
                )
            if parsed.path == "/api/story-seed":
                return self._send_json(save_story_seed_request(payload))
            if parsed.path == "/api/story-seed/propose":
                return self._send_json(propose_story_seed_revision_request(payload))
            if parsed.path == "/api/series-package":
                result = save_series_package_request(payload)
                return self._send_json(result)
            if parsed.path == "/api/series-package/generate":
                result = generate_series_package_request(payload)
                status = HTTPStatus.OK if result.get("ok", True) else HTTPStatus.SERVICE_UNAVAILABLE
                return self._send_json(result, status)
            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - exercised as integration behavior.
            self._send_json(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        if self.path.startswith("/api/settings"):
            return
        super().log_message(format, *args)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        return data

    def _send_json(
        self, value: Any, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        encoded = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_audio(self, query: str) -> None:
        params = parse_qs(query)
        audio_path = resolve_audio_request(params)
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(audio_path.stat().st_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with audio_path.open("rb") as audio_file:
            while chunk := audio_file.read(1024 * 256):
                self.wfile.write(chunk)


def settings_status() -> dict[str, Any]:
    """Return local settings and environment status without revealing secrets."""
    return redacted_litrpg_settings_status(SETTINGS_PATH)


def write_settings(payload: dict[str, Any]) -> None:
    """Write allowed local settings fields to the local ignored settings file."""
    save_litrpg_settings(payload, SETTINGS_PATH)


def story_seed_response(path_value: str = "") -> dict[str, Any]:
    """Return a markdown story seed file for human editing in the local UI."""
    path = resolve_story_seed_path(path_value or DEFAULT_STORY_SEED_PATH)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "ok": True,
        "path": _display_path(path),
        "text": text,
        "exists": path.exists(),
    }


def save_story_seed_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a markdown story seed file from the local UI."""
    path = resolve_story_seed_path(str(payload.get("path") or DEFAULT_STORY_SEED_PATH))
    text = str(payload.get("text") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "ok": True,
        "path": _display_path(path),
        "text": text,
        "exists": True,
    }


def propose_story_seed_revision_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Ask the configured LLM to propose a markdown seed revision."""
    current_markdown = str(payload.get("markdown") or "")
    instruction = str(payload.get("instruction") or "").strip()
    if not current_markdown.strip():
        raise ValueError("markdown is required")
    if not instruction:
        raise ValueError("instruction is required")
    generation = payload.get("generation")
    if not isinstance(generation, dict):
        generation = _default_story_revision_generation()
    settings = load_litrpg_settings(SETTINGS_PATH)
    llm = _llm_from_task({"generation": generation}, settings=settings)
    prompt = build_story_seed_revision_prompt(
        markdown=current_markdown,
        instruction=instruction,
    )
    print(
        "Story seed AI proposal started "
        f"(provider={generation.get('provider', '')}, "
        f"model={generation.get('ollama_model') or generation.get('local_model') or generation.get('model') or ''}, "
        f"chars={len(current_markdown)}, prompt_chars={len(prompt)}, instruction={instruction[:80]!r})",
        flush=True,
    )
    raw = str(llm.generate(prompt=prompt, stage="story_seed_revision"))
    proposal = extract_story_seed_revision(raw)
    revised_markdown = proposal["revised_markdown"]
    if proposal.get("patch_markdown") and revised_markdown == proposal["patch_markdown"]:
        revised_markdown = f"{current_markdown.rstrip()}\n\n{proposal['patch_markdown']}\n"
    print(
        "Story seed AI proposal finished "
        f"(revised_chars={len(revised_markdown)})",
        flush=True,
    )
    return {
        "ok": True,
        "summary": proposal["summary"],
        "revised_markdown": revised_markdown,
        "patch_markdown": proposal.get("patch_markdown", ""),
        "raw": raw,
        "provider": generation.get("provider", ""),
        "model": generation.get("ollama_model")
        or generation.get("local_model")
        or generation.get("model")
        or "",
    }


def build_story_seed_revision_prompt(*, markdown: str, instruction: str) -> str:
    """Build a focused prompt for proposing markdown seed edits."""
    excerpt = _story_seed_revision_excerpt(markdown, instruction)
    return f"""You are an AI story development editor for a LitRPG story seed.

Propose a focused markdown patch according to the user's instruction. Preserve
the document's concrete names, continuity rules, and production details. Do not
rewrite the whole document. Do not return generic advice. Make the patch ready
to insert into the story seed as canon guidance or an AI Notes section.
The patch must be additive or surgical: 80-700 words, no full-file replacement,
no repeated intake instructions, and no copy of the whole seed.

Return ONLY a JSON object with these keys:
- summary: one sentence describing what changed.
- patch_markdown: a concise markdown block containing the proposed change.

User instruction:
{instruction}

Relevant current markdown excerpts:
{excerpt}
"""


def extract_story_seed_revision(text: str) -> dict[str, str]:
    """Extract a story seed revision JSON object from model output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                data = _extract_loose_story_revision_json(stripped[start : end + 1])
        else:
            data = {"summary": "Model returned markdown without JSON.", "patch_markdown": stripped}
    if not isinstance(data, dict):
        raise ValueError("Story revision model must return a JSON object")
    revised = str(data.get("revised_markdown") or "").strip()
    patch = str(data.get("patch_markdown") or "").strip()
    if not revised and not patch:
        raise ValueError("Story revision model did not return revised_markdown or patch_markdown")
    if not revised:
        revised = patch
    return {
        "summary": str(data.get("summary") or "Proposed markdown revision.").strip(),
        "revised_markdown": revised,
        "patch_markdown": patch,
    }


def _extract_loose_story_revision_json(text: str) -> dict[str, str]:
    """Recover common model JSON with unescaped markdown newlines."""
    fields: dict[str, str] = {}
    for key in ("summary", "patch_markdown", "revised_markdown"):
        pattern = rf'"{key}"\s*:\s*"(?P<value>.*?)(?:"\s*,\s*"(?:summary|patch_markdown|revised_markdown)"|"\s*\}})'
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            value = match.group("value")
            fields[key] = value.replace('\\"', '"').replace("\\n", "\n").strip()
    if fields:
        return fields
    return {"summary": "Model returned markdown without strict JSON.", "patch_markdown": text.strip()}


def _story_seed_revision_excerpt(markdown: str, instruction: str) -> str:
    """Return compact context for a local model patch proposal."""
    normalized = markdown.replace("\r\n", "\n")
    sections = normalized.split("\n## ")
    terms = {
        term.lower()
        for term in instruction.replace("-", " ").replace("_", " ").split()
        if len(term.strip(".,:;!?\"'()[]{}")) >= 4
        for term in [term.strip(".,:;!?\"'()[]{}")]
    }
    selected: list[str] = []
    if sections:
        selected.append(sections[0][:1800])
    for section in sections[1:]:
        section_text = "## " + section
        lower = section_text.lower()
        if any(term in lower for term in terms):
            selected.append(section_text[:1800])
        if len("\n\n".join(selected)) >= 5200:
            break
    if len(selected) == 1:
        selected.append(normalized[:3800])
    excerpt = "\n\n---\n\n".join(dict.fromkeys(selected))
    return excerpt[:6500]


def _default_story_revision_generation() -> dict[str, Any]:
    return {
        "provider": "ollama",
        "ollama_model": "hermes3:latest",
        "ollama_timeout_seconds": 120,
        "ollama_options": {
            "temperature": 0.25,
            "top_p": 0.9,
            "num_ctx": 4096,
            "num_predict": 700,
        },
    }


def series_package_response(series_id: str) -> dict[str, Any]:
    """Return package readiness and saved package content for a series."""
    safe_series_id = _safe_series_id(series_id)
    package = load_series_package(safe_series_id)
    if package is None:
        package = load_intake_artifact_workspace(safe_series_id)
        if package is not None:
            return _series_package_payload(
                safe_series_id,
                package,
                status="artifact_workspace",
            )
    return _series_package_payload(safe_series_id, package)


def load_intake_artifact_workspace(series_id: str) -> dict[str, Any] | None:
    """Load premise-intake artifacts as a readable workspace package."""
    series_root = (DATA_DIR / "series" / _safe_series_id(series_id)).resolve()
    if not series_root.exists():
        return None
    artifacts = {
        "series_plan": _read_json_if_object(series_root / "series_plan.json"),
        "series_arc": _read_json_if_any(series_root / "series_arc.json"),
        "chapter_outline": _read_json_if_any(series_root / "book_1" / "chapter_outline.json"),
        "story_bible": _read_json_if_object(series_root / "story_bible.json"),
        "voice_cards": _read_json_if_object(series_root / "voice_cards.json"),
        "continuity_ledger": _read_json_if_object(series_root / "continuity_ledger.json"),
        "emotional_arcs": _read_json_if_object(series_root / "emotional_arcs.json"),
        "world_register": _read_json_if_object(series_root / "world_register.json"),
        "foreshadow_ledger": _read_json_if_object(series_root / "foreshadow_ledger.json"),
    }
    present = {key: value for key, value in artifacts.items() if value not in (None, {}, [])}
    if not present:
        return None
    series_plan = _mapping_or_empty(present.get("series_plan"))
    story_bible = _mapping_or_empty(present.get("story_bible"))
    world_register = _mapping_or_empty(present.get("world_register"))
    return {
        "schema_version": "artifact-workspace-v1",
        "series_id": series_id,
        "metadata": {
            "source": "premise_intake_artifacts",
            "artifact_count": len(present),
            "title": series_plan.get("series_title") or series_plan.get("title") or series_id,
        },
        "premise": str(story_bible.get("premise") or ""),
        **present,
        "characters": _package_characters_from_story_bible(story_bible),
        "familiar": _package_familiar_from_story_bible(story_bible),
        "home_base": _package_home_base_from_world_register(world_register),
        "floor_rules": {
            "rules": [
                item.get("rule") or item.get("name") or item.get("detail")
                for item in _list_of_dicts(world_register.get("rules"))
                if item.get("rule") or item.get("name") or item.get("detail")
            ],
        },
        "bestiary": _package_bestiary_from_world_register(world_register),
    }


def save_series_package_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a series package JSON payload from the local UI."""
    series_id = _safe_series_id(str(payload.get("series_id") or ""))
    package = payload.get("package")
    if not isinstance(package, dict):
        package = {
            "schema_version": "ui-draft-v1",
            "series_id": series_id,
            "metadata": {
                "source": "ui",
                "genre": str(payload.get("genre") or payload.get("style") or "").strip(),
            },
            "premise": str(payload.get("premise") or "").strip(),
            "baseline_text": str(payload.get("baseline_text") or "").strip(),
            "system_announcer": {},
            "characters": [],
            "familiar": {},
            "home_base": {},
            "floor_rules": {},
            "faction_map": {},
            "bestiary": [],
            "encounters": [],
        }
    saved = save_series_package(series_id, package)
    return _series_package_payload(series_id, saved, ok=True)


def generate_series_package_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate and optionally save a series package when the generator is installed."""
    series_id = _safe_series_id(str(payload.get("series_id") or ""))
    premise = str(payload.get("premise") or "").strip()
    genre = str(payload.get("genre") or payload.get("style") or "").strip()
    baseline_text = str(payload.get("baseline_text") or "").strip()
    if not premise:
        raise ValueError("premise is required")
    try:
        generated = generate_series_package(
            series_id=series_id,
            premise=premise,
            genre=genre,
            baseline_text=baseline_text,
            storage_dir=DATA_DIR,
        )
    except RuntimeError as exc:
        return {
            "ok": False,
            "series_id": series_id,
            "status": "generator_unavailable",
            "error": str(exc),
            "modules": package_module_status(),
        }
    if not isinstance(generated, dict):
        raise ValueError("Package generator must return a JSON object")
    if payload.get("save", True):
        generated = save_series_package(series_id, generated)
    return _series_package_payload(series_id, generated, ok=True, status="generated")


def load_series_package(series_id: str) -> dict[str, Any] | None:
    """Load a series package through Worker A helpers when available, else fallback."""
    path = _series_package_path(series_id)
    if not path.exists():
        return None
    package_module = _optional_module("podcastfy.litrpg.packages")
    if package_module is not None:
        loader = getattr(package_module, "load_series_package", None)
        if callable(loader):
            return _package_to_dict(_call_package_helper(loader, series_id))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Saved series package must be a JSON object")
    return data


def save_series_package(series_id: str, package: dict[str, Any]) -> dict[str, Any]:
    """Save a series package through Worker A helpers when available, else fallback."""
    package_module = _optional_module("podcastfy.litrpg.packages")
    if package_module is not None:
        saver = getattr(package_module, "save_series_package", None)
        if callable(saver):
            saved = _call_package_helper(saver, series_id, package)
            if saved is not None:
                return _package_to_dict(saved) or package
            loaded = load_series_package(series_id)
            if loaded is not None:
                return loaded
    path = _series_package_path(series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = dict(package)
    normalized.setdefault("schema_version", "ui-draft-v1")
    normalized.setdefault("series_id", series_id)
    path.write_text(
        json.dumps(normalized, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return normalized


def generate_series_package(
    *,
    series_id: str,
    premise: str,
    genre: str = "",
    baseline_text: str = "",
    storage_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Call the package generator with the configured local generation provider."""
    generator_module = _optional_module("podcastfy.litrpg.package_generator")
    generator = getattr(generator_module, "generate_series_package", None) if generator_module else None
    if not callable(generator):
        raise RuntimeError("Series package generator is not installed yet")
    settings = load_litrpg_settings(SETTINGS_PATH)
    provider = str(settings.get("default_generation_provider") or "openai").lower()
    if provider not in {"openai", "gemini", "geminiapi", "google"}:
        raise RuntimeError(
            f"Series package generation currently supports openai or gemini, not {provider!r}"
        )
    model = str(
        settings.get("default_model")
        or ("gemini-2.5-flash" if provider in {"gemini", "geminiapi", "google"} else "gpt-5.4")
    )
    try:
        llm = _llm_from_task(
            {"generation": {"provider": provider, "model": model, "reasoning_effort": "low"}},
            settings=settings,
        )
    except ValueError as exc:
        raise RuntimeError(
            "Series package generator is not installed or provider API key is not configured: "
            f"{exc}"
        ) from exc
    for kwargs in (
        {
            "series_id": series_id,
            "premise": premise,
            "genre": genre,
            "baseline_text": baseline_text,
            "llm": llm,
            "storage_dir": storage_dir or DATA_DIR,
            "save": False,
        },
        {
            "series_id": series_id,
            "premise": premise,
            "genre": genre,
            "baseline_text": baseline_text,
            "llm": llm,
        },
        {"premise": premise, "genre": genre, "baseline_text": baseline_text, "llm": llm},
        {
            "series_id": series_id,
            "premise": premise,
            "baseline_text": baseline_text,
            "llm": llm,
            "storage_dir": storage_dir or DATA_DIR,
            "save": False,
        },
        {
            "series_id": series_id,
            "premise": premise,
            "baseline_text": baseline_text,
            "llm": llm,
        },
        {"premise": premise, "baseline_text": baseline_text, "llm": llm},
    ):
        try:
            return generator(**kwargs)
        except TypeError:
            continue
    raise RuntimeError("Series package generator is not installed or has an unsupported signature")


def package_module_status() -> dict[str, Any]:
    """Return package helper/generator readiness without importing secrets or providers."""
    packages_module = _optional_module("podcastfy.litrpg.packages")
    generator_module = _optional_module("podcastfy.litrpg.package_generator")
    return {
        "packages": packages_module is not None,
        "generator": generator_module is not None
        and callable(getattr(generator_module, "generate_series_package", None)),
    }


def list_tasks() -> list[dict[str, str]]:
    """List supported local story task files."""
    if not USAGE_DIR.exists():
        return []
    paths = {
        path
        for prefix in TASK_FILE_PREFIXES
        for path in USAGE_DIR.glob(f"{prefix}*.json")
    }
    tasks = []
    for path in sorted(paths):
        if path.is_file():
            tasks.append({"name": path.name, "path": _display_path(path)})
    return tasks


def submit_task_job(
    task_path: Path | None = None,
    task_data: dict[str, Any] | None = None,
) -> TaskJob:
    """Start a task in the background and return its tracking record."""
    task_id = uuid.uuid4().hex
    job = TaskJob(
        job_id=task_id,
        task_id=task_id,
        task_path=_display_path(task_path) if task_path is not None else None,
        task_summary=_task_summary(task_path=task_path, task_data=task_data),
    )
    with _JOBS_LOCK:
        _JOBS[job.job_id] = job
    thread = threading.Thread(
        target=_run_task_job,
        args=(job.job_id, task_path, task_data),
        name=f"litrpg-task-{job.job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return job


def list_jobs() -> list[dict[str, Any]]:
    """Return newest known jobs first."""
    with _JOBS_LOCK:
        jobs = list(_JOBS.values())
    return [serialize_job(job) for job in sorted(jobs, key=lambda item: item.created_at, reverse=True)]


def get_job_response(job_id: str) -> dict[str, Any]:
    """Return a single job response object for API polling."""
    normalized = job_id.strip("/")
    with _JOBS_LOCK:
        job = _JOBS.get(normalized)
    if job is None:
        raise ValueError("Job not found")
    return {"job": serialize_job(job)}


def serialize_job(job: TaskJob) -> dict[str, Any]:
    """Serialize a task job without exposing local object references."""
    return {
        "job_id": job.job_id,
        "task_id": job.task_id or job.job_id,
        "task_path": job.task_path,
        "phase": job.phase,
        "status": job.status,
        "task_summary": job.task_summary,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "duration_seconds": _duration_seconds(job),
        "result": job.result,
        "error": job.error,
        "checkpoint_paths": job.checkpoint_paths,
    }


def _run_task_job(
    job_id: str,
    task_path: Path | None,
    task_data: dict[str, Any] | None,
) -> None:
    _update_job(job_id, status="running", phase="running", started_at=time.time())
    try:
        result = _run_task_request(task_path=task_path, task_data=task_data)
        _update_job(
            job_id,
            status="succeeded",
            phase="complete",
            finished_at=time.time(),
            result=_result_metadata(result),
            checkpoint_paths=_checkpoint_paths(result),
        )
    except Exception as exc:  # pragma: no cover - direct behavior covered through HTTP.
        _update_job(
            job_id,
            status="failed",
            phase="failed",
            finished_at=time.time(),
            error=f"{type(exc).__name__}: {exc}",
        )


def _update_job(job_id: str, **changes: Any) -> TaskJob | None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        for key, value in changes.items():
            setattr(job, key, value)
        return job


def _duration_seconds(job: TaskJob) -> float | None:
    if job.started_at is None:
        return None
    end = job.finished_at or time.time()
    return round(max(0.0, end - job.started_at), 3)


def _result_metadata(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"value": result}
    keys = (
        "series_id",
        "episode_id",
        "episode_number",
        "chapter_id",
        "chapter_number",
        "mode",
        "status",
        "result_path",
        "bundle_dir",
        "episode_dir",
        "checkpoint_dir",
        "audio_path",
        "written_files",
        "artifact_paths",
    )
    metadata = {key: result[key] for key in keys if key in result}
    for key in ("script_path", "metadata_path", "audio_metadata_path"):
        if key in result:
            metadata[key] = result[key]
    if not metadata:
        metadata = dict(result)
    return metadata


def _checkpoint_paths(result: Any) -> list[str]:
    if not isinstance(result, dict):
        return []
    raw_paths: list[Any] = []
    for key in (
        "checkpoint_paths",
        "checkpoints",
        "part_paths",
        "approved_part_paths",
        "written_files",
        "artifact_paths",
    ):
        value = result.get(key)
        if isinstance(value, list):
            raw_paths.extend(value)
    for key in ("checkpoint_dir", "result_path"):
        value = result.get(key)
        if value:
            raw_paths.append(value)
    return [str(path) for path in raw_paths]


def _run_task_request(
    *,
    task_path: Path | None,
    task_data: dict[str, Any] | None,
) -> dict[str, Any]:
    if task_path is not None:
        return run_litrpg_task(task_path)
    if task_data is not None:
        return run_litrpg_task_data(task_data, base_dir=PROJECT_ROOT)
    raise ValueError("Task path or task payload is required")


def resolve_task_request(payload: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
    task_value = payload.get("task")
    path_value = payload.get("path")
    if task_value is not None:
        if path_value is not None:
            raise ValueError("Provide either path or task, not both")
        if not isinstance(task_value, dict):
            raise ValueError("task must be a JSON object")
        return None, dict(task_value)
    if path_value is not None:
        return resolve_task_path(path_value), None
    raise ValueError("Task path or task payload is required")


def _task_summary(
    *,
    task_path: Path | None,
    task_data: dict[str, Any] | None,
) -> dict[str, Any]:
    if task_data is None:
        summary: dict[str, Any] = {"source": "task-file"}
        if task_path is not None:
            summary["path"] = _display_path(task_path)
        return summary
    summary = {
        "source": "inline",
        "series_id": str(task_data.get("series_id") or "default-series"),
        "mode": str(task_data.get("mode") or "episode"),
        "render_audio": bool(task_data.get("render_audio", True)),
    }
    if task_data.get("genre") or task_data.get("style"):
        summary["genre"] = str(task_data.get("genre") or task_data.get("style"))
    premise = str(task_data.get("premise") or "").strip()
    if premise:
        summary["premise"] = premise[:160]
    generation = task_data.get("generation")
    if isinstance(generation, dict):
        if generation.get("provider"):
            summary["generation_provider"] = str(generation["provider"])
        if generation.get("model"):
            summary["generation_model"] = str(generation["model"])
    tts = task_data.get("tts")
    if isinstance(tts, dict):
        if tts.get("provider"):
            summary["tts_provider"] = str(tts["provider"])
        if tts.get("model"):
            summary["tts_model"] = str(tts["model"])
    return summary


def list_library() -> list[dict[str, Any]]:
    """List saved series/episode metadata and playable audio under data/litrpg."""
    series_records = list_library_series()
    return [
        {
            "series_id": series["series_id"],
            "title": series.get("title") or series["series_id"],
            "episode_count": series.get("episode_count", 0),
            "incomplete_count": series.get("incomplete_count", 0),
            "episodes": list_library_episodes(series_id=str(series["series_id"])),
        }
        for series in series_records
    ]


def list_library_series() -> list[dict[str, Any]]:
    """List local series summaries for the replay library."""

    return episode_library.list_series(DATA_DIR)


def list_library_episodes(series_id: str | None = None) -> list[dict[str, Any]]:
    """List replayable episode payloads, optionally for one series."""

    return [
        _episode_payload(episode)
        for episode in episode_library.list_episodes(DATA_DIR, series_id=series_id)
    ]


def get_library_episode(series_id: str, episode_id: str) -> dict[str, Any]:
    """Return one episode payload for the replay library."""

    episode = episode_library.get_episode(DATA_DIR, series_id, episode_id)
    if episode is None:
        raise ValueError("Episode not found")
    return _episode_payload(episode)


def resolve_task_path(value: Any) -> Path:
    if not value:
        raise ValueError("Task path is required")
    path = Path(str(value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    usage_root = USAGE_DIR.resolve()
    if not _is_relative_to(resolved, usage_root):
        raise ValueError("Task path must stay inside usage/")
    if not _is_supported_task_file(resolved):
        prefixes = ", ".join(f"{prefix}*.json" for prefix in TASK_FILE_PREFIXES)
        raise ValueError(f"Task must be a usage/ file matching: {prefixes}")
    if not resolved.is_file():
        raise ValueError("Task file does not exist")
    return resolved


def resolve_story_seed_path(value: Any) -> Path:
    if not value:
        raise ValueError("Story seed path is required")
    path = Path(str(value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    usage_root = USAGE_DIR.resolve()
    if not _is_relative_to(resolved, usage_root):
        raise ValueError("Story seed path must stay inside usage/")
    if resolved.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Story seed must be a markdown or text file")
    return resolved


def _is_supported_task_file(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() == ".json" and any(
        name.startswith(prefix) for prefix in TASK_FILE_PREFIXES
    )


def resolve_audio_path(value: str) -> Path:
    if not value:
        raise ValueError("Audio path is required")
    path = Path(unquote(value))
    if path.is_absolute():
        candidate = path
    else:
        candidate = DATA_DIR / path
    resolved = candidate.resolve()
    data_root = DATA_DIR.resolve()
    if not _is_relative_to(resolved, data_root):
        raise ValueError("Audio path must stay inside data/litrpg")
    if not resolved.is_file():
        raise ValueError("Audio file does not exist")
    return resolved


def resolve_audio_request(params: dict[str, list[str]]) -> Path:
    """Resolve an audio request from safe series/episode IDs or legacy path."""
    series_id = params.get("series_id", [""])[0]
    episode_id = params.get("episode_id", [""])[0]
    if series_id and episode_id:
        audio_path = episode_library.get_audio_path(DATA_DIR, series_id, episode_id)
        if not audio_path:
            raise ValueError("Audio file does not exist")
        return resolve_audio_path(audio_path)
    return resolve_audio_path(params.get("path", [""])[0])


def _series_package_payload(
    series_id: str,
    package: Any | None,
    *,
    ok: bool = True,
    status: str | None = None,
) -> dict[str, Any]:
    package_path = _series_package_path(series_id)
    package_payload = _package_to_dict(package)
    exists = package_payload is not None
    return {
        "ok": ok,
        "series_id": series_id,
        "status": status or ("ready" if exists else "missing"),
        "available": exists,
        "package": package_payload,
        "summary": summarize_series_package(package_payload),
        "path": _display_path(package_path),
        "modules": package_module_status(),
    }


def summarize_series_package(package: Any | None) -> str:
    """Return a compact human-readable summary for diagnostics and copying."""
    package_payload = _package_to_dict(package)
    if not package_payload:
        return ""
    package_module = _optional_module("podcastfy.litrpg.packages")
    if package_module is not None:
        for name in ("format_series_package_summary", "format_package_summary", "package_prompt_summary", "summarize_series_package"):
            formatter = getattr(package_module, name, None)
            if callable(formatter):
                try:
                    value = formatter(package_payload)
                except TypeError:
                    continue
                return str(value)

    pieces = []
    metadata = package_payload.get("metadata")
    if isinstance(metadata, dict):
        if metadata.get("title"):
            pieces.append(f"Title: {metadata['title']}")
        if metadata.get("logline"):
            pieces.append(f"Logline: {metadata['logline']}")
    announcer = package_payload.get("system_announcer")
    if isinstance(announcer, dict):
        name = announcer.get("name") or announcer.get("role") or "System Announcer"
        tone = announcer.get("tone") or announcer.get("voice") or announcer.get("style")
        pieces.append(f"{name}: {tone}" if tone else str(name))
    characters = package_payload.get("characters")
    if isinstance(characters, list) and characters:
        names = [
            str(item.get("name") or item.get("role"))
            for item in characters
            if isinstance(item, dict) and (item.get("name") or item.get("role"))
        ]
        if names:
            pieces.append("Characters: " + ", ".join(names[:8]))
    familiar = package_payload.get("familiar")
    if isinstance(familiar, dict) and (familiar.get("name") or familiar.get("role")):
        pieces.append(f"Familiar: {familiar.get('name') or familiar.get('role')}")
    home_base = package_payload.get("home_base")
    if isinstance(home_base, dict) and (home_base.get("name") or home_base.get("type")):
        pieces.append(f"Home base: {home_base.get('name') or home_base.get('type')}")
    floor_rules = package_payload.get("floor_rules")
    if isinstance(floor_rules, dict):
        rule_count = len(floor_rules.get("rules", [])) if isinstance(floor_rules.get("rules"), list) else len(floor_rules)
        if rule_count:
            pieces.append(f"Floor rules: {rule_count}")
    faction_map = package_payload.get("faction_map")
    if isinstance(faction_map, dict):
        faction_count = len(faction_map.get("factions", [])) if isinstance(faction_map.get("factions"), list) else len(faction_map)
        if faction_count:
            pieces.append(f"Factions: {faction_count}")
    bestiary = (
        package_payload.get("bestiary")
        or package_payload.get("world_entities")
        or package_payload.get("entities")
        or package_payload.get("monsters")
        or package_payload.get("mobs")
    )
    bestiary_count = _package_collection_count(bestiary)
    if bestiary_count:
        pieces.append(f"Bestiary: {bestiary_count}")
    encounters = (
        package_payload.get("encounters")
        or package_payload.get("encounter_registry")
        or package_payload.get("bosses")
    )
    encounter_count = _package_collection_count(encounters)
    if encounter_count:
        pieces.append(f"Encounters: {encounter_count}")
    return "\n".join(pieces)


def _package_collection_count(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if isinstance(item, dict)])
    if isinstance(value, dict):
        return len(value)
    return 0


def _read_json_if_any(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_json_if_object(path: Path) -> dict[str, Any] | None:
    value = _read_json_if_any(path)
    return value if isinstance(value, dict) else None


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [dict(item) for item in value.values() if isinstance(item, dict)]
    return []


def _package_characters_from_story_bible(story_bible: dict[str, Any]) -> list[dict[str, Any]]:
    characters = story_bible.get("characters")
    items = _list_of_dicts(characters)
    if isinstance(characters, dict):
        for key, item in zip(characters.keys(), items):
            item.setdefault("name", str(key))
    return [
        {
            "name": item.get("name") or item.get("character") or "Unnamed",
            "voice": "; ".join(str(rule) for rule in item.get("voice_rules", [])[:3])
            if isinstance(item.get("voice_rules"), list)
            else str(item.get("voice") or ""),
            "personality": "; ".join(str(note) for note in item.get("notes", [])[:3])
            if isinstance(item.get("notes"), list)
            else "",
            "arc": "; ".join(str(thread) for thread in item.get("unresolved_promises", [])[:3])
            if isinstance(item.get("unresolved_promises"), list)
            else "",
            "rules": item.get("never_contradict_facts", []),
            "notes": item.get("running_jokes", []),
        }
        for item in items
        if item.get("name") or item.get("character")
    ]


def _package_familiar_from_story_bible(story_bible: dict[str, Any]) -> dict[str, Any]:
    for item in _package_characters_from_story_bible(story_bible):
        name = str(item.get("name") or "")
        if name.casefold() in {"pedro", "pedro the macaw"} or "pedro" in name.casefold():
            return {
                "name": name,
                "species": "macaw/familiar",
                "voice": item.get("voice", ""),
                "rules": item.get("rules", []),
                "notes": item.get("notes", []),
            }
    return {}


def _package_home_base_from_world_register(world_register: dict[str, Any]) -> dict[str, Any]:
    for item in _list_of_dicts(world_register.get("locations")):
        name = str(item.get("name") or "")
        tags = " ".join(str(tag) for tag in item.get("tags", [])).casefold() if isinstance(item.get("tags"), list) else ""
        if "sophie" in name.casefold() or "vehicle" in tags or "home-base" in tags:
            return {
                "name": name,
                "description": item.get("detail") or item.get("description") or "",
                "rules": [],
                "notes": item.get("tags", []),
            }
    return {}


def _package_bestiary_from_world_register(world_register: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": item.get("entity") or item.get("name") or "Unnamed",
            "entity_type": "world entity",
            "first_seen": item.get("location") or "",
            "behavior_rules": [item.get("detail")] if item.get("detail") else [],
            "notes": item.get("tags", []),
        }
        for item in _list_of_dicts(world_register.get("entity_ecology"))
        if item.get("entity") or item.get("name")
    ]


def _series_package_path(series_id: str) -> Path:
    return DATA_DIR / "series" / _safe_series_id(series_id) / "series_package.json"


def _safe_series_id(series_id: str) -> str:
    value = str(series_id or "").strip()
    if not value:
        raise ValueError("series_id is required")
    path = Path(value)
    if value in {"", ".", ".."} or path.name != value:
        raise ValueError(f"Unsafe path segment: {value}")
    return value


def _optional_module(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            return None
        raise


def _package_to_dict(package: Any | None) -> dict[str, Any] | None:
    if package is None:
        return None
    if isinstance(package, dict):
        return package
    package_module = _optional_module("podcastfy.litrpg.packages")
    converter = getattr(package_module, "series_package_to_dict", None) if package_module else None
    if callable(converter):
        try:
            value = converter(package)
        except (TypeError, ValueError):
            value = None
        if isinstance(value, dict):
            return value
    if is_dataclass(package):
        value = asdict(package)
        return value if isinstance(value, dict) else None
    return None


def _call_package_helper(
    helper: Any,
    series_id: str,
    package: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    attempts = []
    if package is None:
        attempts = [
            ((), {"series_id": series_id, "storage_dir": DATA_DIR}),
            ((), {"storage_dir": DATA_DIR, "series_id": series_id}),
            ((series_id,), {"storage_dir": DATA_DIR}),
            ((DATA_DIR, series_id), {}),
        ]
    else:
        normalized = dict(package)
        normalized.setdefault("series_id", series_id)
        attempts = [
            ((), {"storage_dir": DATA_DIR, "package": normalized}),
            ((), {"package": normalized, "storage_dir": DATA_DIR}),
            ((DATA_DIR, normalized), {}),
            ((series_id, normalized), {"storage_dir": DATA_DIR}),
            ((DATA_DIR, series_id, normalized), {}),
        ]
    for args, kwargs in attempts:
        try:
            return helper(*args, **kwargs)
        except TypeError:
            continue
    raise RuntimeError("Series package helper has an unsupported signature")


def _episode_payload(episode: dict[str, Any]) -> dict[str, Any]:
    audio_path = episode.get("audio_path")
    audio = None
    replay = {
        "available": False,
        "mode": "cached",
        "status": "missing_audio",
    }
    if audio_path:
        path = Path(str(audio_path))
        relative = _relative_to_data(path)
        audio = {
            "path": relative,
            "url": (
                "/audio?"
                f"series_id={quote(str(episode['series_id']))}"
                f"&episode_id={quote(str(episode['episode_id']))}"
            ),
            "legacy_url": f"/audio?path={quote(relative)}",
            "format": _audio_format(path, episode.get("audio_metadata", {})),
            "bytes": path.stat().st_size,
        }
        replay = {
            "available": True,
            "mode": "cached",
            "status": "ready",
            "format": audio["format"],
            "bytes": audio["bytes"],
            "url": audio["url"],
        }
    return {
        "series_id": episode.get("series_id"),
        "episode_id": episode.get("episode_id"),
        "episode_number": episode.get("episode_number"),
        "status": episode.get("status"),
        "qa": _qa_summary(episode),
        "prompt": episode.get("prompt", ""),
        "path": _display_path(Path(str(episode.get("path", "")))),
        "audio": audio,
        "replay": replay,
        "regenerable_parts": episode.get("regenerable_parts", []),
    }


def _audio_format(path: Path, audio_metadata: Any) -> str:
    if isinstance(audio_metadata, dict) and audio_metadata.get("format"):
        return str(audio_metadata["format"])
    return path.suffix.lstrip(".")


def _qa_summary(episode: dict[str, Any]) -> dict[str, Any]:
    metadata = episode.get("metadata") if isinstance(episode.get("metadata"), dict) else {}
    qa = metadata.get("qa") if isinstance(metadata.get("qa"), dict) else {}
    review = metadata.get("review") if isinstance(metadata.get("review"), dict) else {}
    return {
        "status": str(
            qa.get("status")
            or review.get("status")
            or metadata.get("qa_status")
            or metadata.get("review_status")
            or "unknown"
        ),
        "ready": bool(
            qa.get("ready")
            or review.get("ready")
            or metadata.get("qa_ready")
            or metadata.get("ready_for_audio")
        ),
    }


def _relative_to_data(path: Path) -> str:
    return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local LitRPG HTTP UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart the local UI automatically when Python, HTML, CSS, or JS files change.",
    )
    args = parser.parse_args()
    if args.reload and not os.getenv("LITRPG_UI_RELOAD_CHILD"):
        run_server_with_reload(host=args.host, port=args.port)
        return
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
