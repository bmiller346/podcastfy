"""Small stdlib HTTP UI for local LitRPG episode tasks."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from podcastfy.litrpg.settings import API_KEY_FIELDS
from podcastfy.litrpg.task import run_litrpg_task

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USAGE_DIR = PROJECT_ROOT / "usage"
DATA_DIR = PROJECT_ROOT / "data" / "litrpg"
SETTINGS_PATH = PROJECT_ROOT / "settings.local.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

API_KEY_SETTING_KEYS = tuple(dict.fromkeys(value[0] for value in API_KEY_FIELDS.values()))
ALLOWED_SETTING_KEYS = {
    *API_KEY_SETTING_KEYS,
    "default_generation_provider",
    "default_tts_provider",
    "default_model",
    "default_tts_model",
}


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the LitRPG local UI until interrupted."""
    handler = partial(LitRPGUIHandler, directory=str(STATIC_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"LitRPG UI running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLitRPG UI stopped.")
    finally:
        server.server_close()


class LitRPGUIHandler(SimpleHTTPRequestHandler):
    """HTTP handler for the local LitRPG app shell and JSON API."""

    server_version = "LitRPGUI/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if parsed.path == "/api/settings":
            return self._send_json(settings_status())
        if parsed.path == "/api/tasks":
            return self._send_json({"tasks": list_tasks()})
        if parsed.path == "/api/library":
            return self._send_json({"library": list_library()})
        if parsed.path == "/audio":
            return self._serve_audio(parsed.query)
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
                task_path = resolve_task_path(payload.get("path"))
                result = run_litrpg_task(task_path)
                return self._send_json({"ok": True, "result": result})
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
        audio_path = resolve_audio_path(params.get("path", [""])[0])
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
    file_settings = _load_settings_file()
    api_keys: dict[str, dict[str, Any]] = {}
    for provider, (setting_key, env_key) in sorted(API_KEY_FIELDS.items()):
        if provider in api_keys:
            continue
        file_configured = bool(file_settings.get(setting_key))
        env_configured = bool(os.getenv(env_key))
        api_keys[provider] = {
            "setting_key": setting_key,
            "env_key": env_key,
            "file": file_configured,
            "env": env_configured,
            "configured": file_configured or env_configured,
            "value": "redacted" if file_configured or env_configured else "",
        }
    defaults = {
        key: file_settings.get(key, "")
        for key in sorted(ALLOWED_SETTING_KEYS)
        if key not in API_KEY_SETTING_KEYS
    }
    return {
        "settings_path": str(SETTINGS_PATH),
        "exists": SETTINGS_PATH.exists(),
        "api_keys": api_keys,
        "defaults": defaults,
    }


def write_settings(payload: dict[str, Any]) -> None:
    """Write allowed local settings fields to settings.local.json."""
    existing = _load_settings_file()
    next_settings = {
        key: value for key, value in existing.items() if key in ALLOWED_SETTING_KEYS
    }
    for key, value in payload.items():
        if key not in ALLOWED_SETTING_KEYS:
            continue
        if value is None:
            next_settings.pop(key, None)
            continue
        if value == "":
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Unsupported settings value for {key}")
        next_settings[key] = value

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as settings_file:
        json.dump(next_settings, settings_file, ensure_ascii=True, indent=2, sort_keys=True)
        settings_file.write("\n")


def list_tasks() -> list[dict[str, str]]:
    """List usage/litrpg*.json task files."""
    if not USAGE_DIR.exists():
        return []
    tasks = []
    for path in sorted(USAGE_DIR.glob("litrpg*.json")):
        if path.is_file():
            tasks.append({"name": path.name, "path": _display_path(path)})
    return tasks


def list_library() -> list[dict[str, Any]]:
    """List saved series/episode metadata and playable audio under data/litrpg."""
    episodes_root = DATA_DIR / "episodes"
    if not episodes_root.exists():
        return []
    library = []
    for series_dir in sorted(path for path in episodes_root.iterdir() if path.is_dir()):
        episodes = []
        for episode_dir in sorted(path for path in series_dir.iterdir() if path.is_dir()):
            metadata = _read_json_file(episode_dir / "metadata.json")
            audio_metadata = _read_json_file(episode_dir / "audio_metadata.json")
            audio_path = _audio_path_from_metadata(episode_dir, audio_metadata)
            if audio_path is None:
                audio_path = next(iter(sorted((episode_dir / "audio").glob("*"))), None)
            audio = None
            if audio_path and audio_path.is_file():
                relative = _relative_to_data(audio_path)
                audio = {
                    "path": relative,
                    "url": f"/audio?path={quote(relative)}",
                    "format": audio_metadata.get("format") or audio_path.suffix.lstrip("."),
                    "bytes": audio_path.stat().st_size,
                }
            episodes.append(
                {
                    "episode_id": str(metadata.get("episode_id") or episode_dir.name),
                    "episode_number": metadata.get("episode_number"),
                    "prompt": metadata.get("prompt", ""),
                    "path": _display_path(episode_dir),
                    "audio": audio,
                }
            )
        library.append({"series_id": series_dir.name, "episodes": episodes})
    return library


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
    if not resolved.name.startswith("litrpg") or resolved.suffix.lower() != ".json":
        raise ValueError("Task must be a usage/litrpg*.json file")
    if not resolved.is_file():
        raise ValueError("Task file does not exist")
    return resolved


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


def _load_settings_file() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    with SETTINGS_PATH.open("r", encoding="utf-8") as settings_file:
        data = json.load(settings_file)
    if not isinstance(data, dict):
        raise ValueError("LitRPG settings file must contain a JSON object")
    return data


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    return data if isinstance(data, dict) else {}


def _audio_path_from_metadata(
    episode_dir: Path, audio_metadata: dict[str, Any]
) -> Path | None:
    raw_path = audio_metadata.get("audio_path")
    if not raw_path:
        return None
    path = Path(str(raw_path))
    candidates = [path]
    if not path.is_absolute():
        candidates.extend([PROJECT_ROOT / path, episode_dir / path])
    for candidate in candidates:
        resolved = candidate.resolve()
        if _is_relative_to(resolved, DATA_DIR.resolve()) and resolved.exists():
            return resolved
    return None


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
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
