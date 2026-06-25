"""Filesystem library utilities for local LitRPG episode bundles."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


EPISODE_STATUS_COMPLETE = "complete"
EPISODE_STATUS_INCOMPLETE = "incomplete"
EPISODE_STATUS_MISSING_AUDIO = "missing_audio"
EPISODE_STATUS_FAILED_RENDER = "failed_render"

_FAILED_STATUS_VALUES = {
    "failed",
    "failed_render",
    "render_failed",
    "render_error",
}
_AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
_PART_GLOBS = (
    "script.*",
    "part-*.*",
    "part_*.*",
    "parts/*",
    "parts/**/*",
    "script_parts/*",
    "script_parts/**/*",
)


def list_series(storage_dir: str | Path) -> list[dict[str, Any]]:
    """List series that have state or episode bundles under storage_dir."""

    root = _storage_root(storage_dir)
    series_ids = {
        path.name
        for path in _safe_iter_dirs(root / "series")
        if _safe_name(path.name)
    }
    series_ids.update(
        path.name
        for path in _safe_iter_dirs(root / "episodes")
        if _safe_name(path.name)
    )

    series = []
    for series_id in sorted(series_ids):
        state_path = _safe_join(root, "series", series_id, "series_state.json")
        episodes = list_episodes(root, series_id=series_id)
        state = _read_json(state_path) if state_path.exists() else {}
        series.append(
            {
                "series_id": series_id,
                "title": str(state.get("title") or _title_from_id(series_id)),
                "episode_count": len(episodes),
                "incomplete_count": sum(
                    1
                    for episode in episodes
                    if episode["status"] != EPISODE_STATUS_COMPLETE
                ),
                "path": str(_safe_join(root, "episodes", series_id)),
                "state_path": str(state_path) if state_path.exists() else None,
                "state": state,
            }
        )
    return series


def list_episodes(
    storage_dir: str | Path, series_id: str | None = None
) -> list[dict[str, Any]]:
    """List episode bundle metadata, optionally for one series."""

    root = _storage_root(storage_dir)
    series_dirs = []
    if series_id is None:
        series_dirs = list(_safe_iter_dirs(root / "episodes"))
    else:
        series_dirs = [_safe_join(root, "episodes", series_id)]

    episodes = []
    for series_dir in series_dirs:
        if not series_dir.exists():
            continue
        for episode_dir in _safe_iter_dirs(series_dir):
            episodes.append(_episode_record(root, series_dir.name, episode_dir.name))

    return sorted(
        episodes,
        key=lambda item: (
            str(item.get("series_id") or ""),
            int(item.get("episode_number") or 0),
            str(item.get("episode_id") or ""),
        ),
    )


def get_episode(
    storage_dir: str | Path, series_id: str, episode_id: str
) -> dict[str, Any] | None:
    """Return one episode record, or None when the bundle directory is missing."""

    root = _storage_root(storage_dir)
    episode_dir = _safe_episode_dir(root, series_id, episode_id)
    if not episode_dir.exists() or not episode_dir.is_dir():
        return None
    return _episode_record(root, series_id, episode_id)


def get_audio_path(
    storage_dir: str | Path, series_id: str, episode_id: str
) -> str | None:
    """Return a safe existing audio path for replay, or None."""

    episode = get_episode(storage_dir, series_id, episode_id)
    if episode is None:
        return None
    return episode.get("audio_path")


def mark_episode_status(
    storage_dir: str | Path, series_id: str, episode_id: str, status: str
) -> dict[str, Any]:
    """Persist a library status value in metadata.json and return the episode."""

    if status not in {
        EPISODE_STATUS_COMPLETE,
        EPISODE_STATUS_INCOMPLETE,
        EPISODE_STATUS_MISSING_AUDIO,
        EPISODE_STATUS_FAILED_RENDER,
    }:
        raise ValueError(f"Unsupported episode status: {status}")

    root = _storage_root(storage_dir)
    episode_dir = _safe_episode_dir(root, series_id, episode_id)
    if not episode_dir.exists():
        raise FileNotFoundError(str(episode_dir))

    metadata_path = _safe_join(episode_dir, "metadata.json")
    metadata = _read_json(metadata_path) if metadata_path.exists() else {}
    metadata["status"] = status
    _write_json(metadata_path, metadata)
    return _episode_record(root, series_id, episode_id)


def delete_episode(storage_dir: str | Path, series_id: str, episode_id: str) -> bool:
    """Delete one episode bundle directory, constrained to storage_dir."""

    root = _storage_root(storage_dir)
    episode_dir = _safe_episode_dir(root, series_id, episode_id)
    if not episode_dir.exists():
        return False
    if not episode_dir.is_dir():
        raise ValueError(f"Episode path is not a directory: {episode_dir}")
    _ensure_within(episode_dir, root)
    shutil.rmtree(episode_dir)
    return True


def list_regenerable_parts(
    storage_dir: str | Path, series_id: str, episode_id: str
) -> list[dict[str, Any]]:
    """List script or part files that a UI can offer for targeted regeneration."""

    root = _storage_root(storage_dir)
    episode_dir = _safe_episode_dir(root, series_id, episode_id)
    if not episode_dir.exists():
        return []

    found: dict[Path, dict[str, Any]] = {}
    metadata = _read_json(episode_dir / "metadata.json")
    files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
    for key, filename in files.items():
        if "script" in str(key).lower() or "part" in str(key).lower():
            path = _safe_optional_path(root, episode_dir, filename)
            if path and path.is_file():
                found[path] = _part_record(episode_dir, path, str(key))

    for pattern in _PART_GLOBS:
        for path in episode_dir.glob(pattern):
            if not path.is_file():
                continue
            _ensure_within(path.resolve(), root)
            found.setdefault(path.resolve(), _part_record(episode_dir, path, path.stem))

    return sorted(found.values(), key=lambda item: str(item["relative_path"]))


def _episode_record(root: Path, series_id: str, episode_id: str) -> dict[str, Any]:
    episode_dir = _safe_episode_dir(root, series_id, episode_id)
    metadata_path = _safe_join(episode_dir, "metadata.json")
    config_path = _safe_join(episode_dir, "config.json")
    audio_metadata_path = _safe_join(episode_dir, "audio_metadata.json")

    metadata = _read_json(metadata_path) if metadata_path.exists() else {}
    config = _read_json(config_path) if config_path.exists() else {}
    audio_metadata = _read_json(audio_metadata_path) if audio_metadata_path.exists() else {}
    audio_path = _find_audio_path(root, episode_dir, audio_metadata)
    status = _infer_status(root, episode_dir, metadata, audio_metadata, audio_path)

    return {
        "series_id": str(metadata.get("series_id") or series_id),
        "episode_id": str(metadata.get("episode_id") or episode_id),
        "episode_number": _episode_number(metadata, episode_id),
        "cache_key": metadata.get("cache_key"),
        "prompt": metadata.get("prompt"),
        "status": status,
        "path": str(episode_dir),
        "metadata_path": str(metadata_path) if metadata_path.exists() else None,
        "config_path": str(config_path) if config_path.exists() else None,
        "audio_metadata_path": str(audio_metadata_path)
        if audio_metadata_path.exists()
        else None,
        "audio_path": str(audio_path) if audio_path else None,
        "metadata": metadata,
        "config": config,
        "audio_metadata": audio_metadata,
        "files": _safe_files(root, episode_dir, metadata),
        "regenerable_parts": list_regenerable_parts(root, series_id, episode_id),
    }


def _infer_status(
    root: Path,
    episode_dir: Path,
    metadata: dict[str, Any],
    audio_metadata: dict[str, Any],
    audio_path: Path | None,
) -> str:
    status_value = str(
        metadata.get("status")
        or metadata.get("render_status")
        or audio_metadata.get("status")
        or ""
    ).lower()
    if status_value in _FAILED_STATUS_VALUES:
        return EPISODE_STATUS_FAILED_RENDER
    if any(key in metadata for key in ("error", "render_error", "exception")):
        return EPISODE_STATUS_FAILED_RENDER
    if any(key in audio_metadata for key in ("error", "render_error", "exception")):
        return EPISODE_STATUS_FAILED_RENDER
    if not metadata:
        return EPISODE_STATUS_INCOMPLETE
    if not (episode_dir / "config.json").exists():
        return EPISODE_STATUS_INCOMPLETE
    if not _has_script_or_part(episode_dir, root, metadata):
        return EPISODE_STATUS_INCOMPLETE
    if audio_path is None:
        return EPISODE_STATUS_MISSING_AUDIO
    return EPISODE_STATUS_COMPLETE


def _find_audio_path(
    root: Path, episode_dir: Path, audio_metadata: dict[str, Any]
) -> Path | None:
    metadata_path = audio_metadata.get("audio_path")
    if metadata_path:
        path = _safe_optional_path(root, episode_dir, str(metadata_path))
        if path and path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS:
            return path

    audio_dir = episode_dir / "audio"
    if audio_dir.exists():
        for path in sorted(audio_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS:
                _ensure_within(path.resolve(), root)
                return path.resolve()
    return None


def _safe_files(root: Path, episode_dir: Path, metadata: dict[str, Any]) -> dict[str, str]:
    files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
    safe_files: dict[str, str] = {}
    for key, filename in files.items():
        path = _safe_optional_path(root, episode_dir, str(filename))
        if path is not None and path.exists():
            safe_files[str(key)] = str(path)
    return safe_files


def _has_script_or_part(episode_dir: Path, root: Path, metadata: dict[str, Any]) -> bool:
    files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
    for key, filename in files.items():
        if "script" in str(key).lower() or "part" in str(key).lower():
            candidate = _safe_optional_path(root, episode_dir, str(filename))
            if candidate is not None and candidate.exists():
                return True
    return any(
        path.is_file()
        for pattern in _PART_GLOBS
        for path in episode_dir.glob(pattern)
    )


def _part_record(episode_dir: Path, path: Path, part_id: str) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "part_id": part_id,
        "path": str(resolved),
        "relative_path": str(resolved.relative_to(episode_dir.resolve())),
        "size_bytes": resolved.stat().st_size,
    }


def _episode_number(metadata: dict[str, Any], episode_id: str) -> int:
    if "episode_number" in metadata:
        try:
            return int(metadata["episode_number"])
        except (TypeError, ValueError):
            pass
    try:
        return int(episode_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def _storage_root(storage_dir: str | Path) -> Path:
    return Path(storage_dir).resolve()


def _safe_episode_dir(root: Path, series_id: str, episode_id: str) -> Path:
    return _safe_join(root, "episodes", series_id, episode_id)


def _safe_join(root: Path, *parts: str | Path) -> Path:
    for part in parts:
        if not _safe_name(str(part)):
            raise ValueError(f"Unsafe path segment: {part}")
    path = root.joinpath(*parts).resolve()
    _ensure_within(path, root)
    return path


def _safe_optional_path(root: Path, episode_dir: Path, value: str) -> Path | None:
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [episode_dir / raw, root / raw, Path.cwd() / raw]
    safe_candidates = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if _is_within(resolved, root):
            safe_candidates.append(resolved)
    for candidate in safe_candidates:
        if candidate.exists():
            return candidate
    return safe_candidates[0] if safe_candidates else None


def _safe_iter_dirs(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(child for child in path.iterdir() if child.is_dir())


def _safe_name(value: str) -> bool:
    path = Path(value)
    return value not in {"", ".", ".."} and path.name == value


def _ensure_within(path: Path, root: Path) -> None:
    if not _is_within(path, root):
        raise ValueError(f"Path escapes storage_dir: {path}")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as json_file:
            value = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(value, json_file, ensure_ascii=True, indent=2, sort_keys=True)
        json_file.write("\n")


def _title_from_id(series_id: str) -> str:
    return series_id.replace("-", " ").replace("_", " ").title()
