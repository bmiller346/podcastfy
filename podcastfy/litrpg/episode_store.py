"""Cache-first episode bundle storage for local LitRPG serials."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from podcastfy.litrpg.models import EpisodeBundle, EpisodeConfig, ScriptLine


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(_to_jsonable(value), json_file, ensure_ascii=True, indent=2, sort_keys=True)
        json_file.write("\n")


def _episode_config_from_dict(data: dict[str, Any]) -> EpisodeConfig:
    return EpisodeConfig(
        prompt=str(data.get("prompt", "")),
        minutes=int(data.get("minutes", 0)),
        tone=str(data.get("tone", "")),
        cast=dict(data.get("cast") or {}),
        tts_model=data.get("tts_model"),
        model_version=data.get("model_version"),
    )


def stable_cache_key(prompt: str, config: EpisodeConfig | dict[str, Any]) -> str:
    """Build a stable cache key from prompt and deterministic config values."""

    config_payload = _to_jsonable(config)
    payload = {
        "config": config_payload,
        "prompt": prompt,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def find_bundle_by_cache_key(
    storage_dir: str | Path, series_id: str, cache_key: str
) -> EpisodeBundle | None:
    """Locate an existing episode bundle for a series/cache key pair."""

    episodes_dir = Path(storage_dir) / "episodes" / series_id
    if not episodes_dir.exists():
        return None

    for metadata_path in sorted(episodes_dir.glob("episode-*/metadata.json")):
        with metadata_path.open("r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        if metadata.get("cache_key") != cache_key:
            continue

        config_path = metadata_path.parent / "config.json"
        with config_path.open("r", encoding="utf-8") as config_file:
            config_data = json.load(config_file)

        paths = {
            key: str(metadata_path.parent / filename)
            for key, filename in metadata.get("files", {}).items()
        }
        paths["episode_dir"] = str(metadata_path.parent)
        paths["metadata"] = str(metadata_path)
        audio_metadata_path = metadata_path.parent / "audio_metadata.json"
        audio_metadata = {}
        if audio_metadata_path.exists():
            with audio_metadata_path.open("r", encoding="utf-8") as audio_metadata_file:
                audio_metadata = json.load(audio_metadata_file)
            paths["audio_metadata"] = str(audio_metadata_path)
            if audio_metadata.get("audio_path"):
                paths["audio"] = str(audio_metadata["audio_path"])
        return EpisodeBundle(
            series_id=str(metadata["series_id"]),
            episode_id=str(metadata["episode_id"]),
            episode_number=int(metadata["episode_number"]),
            cache_key=str(metadata["cache_key"]),
            prompt=str(metadata.get("prompt", "")),
            config=_episode_config_from_dict(config_data),
            paths=paths,
        )

    return None


class EpisodeStore:
    """Filesystem-backed storage for generated LitRPG episode artifacts."""

    def __init__(self, storage_dir: str | Path) -> None:
        self.storage_dir = Path(storage_dir)

    def cache_key(self, prompt: str, config: EpisodeConfig | dict[str, Any]) -> str:
        return stable_cache_key(prompt, config)

    def find_by_cache_key(self, series_id: str, cache_key: str) -> EpisodeBundle | None:
        return find_bundle_by_cache_key(self.storage_dir, series_id, cache_key)

    def find_existing_bundle(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Return existing bundle metadata for a prompt/config payload if present."""

        config = _episode_config_from_payload(payload)
        series_id = str(payload.get("series_id") or "default-series")
        found = self.find_by_cache_key(series_id, stable_cache_key(config.prompt, config))
        if found is None:
            return None
        if payload.get("require_audio") and not found.paths.get("audio"):
            return None
        return {
            "bundle_path": found.paths["episode_dir"],
            "cache_key": found.cache_key,
            "episode_id": found.episode_id,
            "episode_number": found.episode_number,
            "paths": found.paths,
            "audio_metadata": {
                "audio_path": found.paths.get("audio"),
                "audio_metadata_path": found.paths.get("audio_metadata"),
            },
            "replayed": True,
        }

    def save_bundle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a generic engine bundle payload.

        This adapter lets the dependency-injected LitRPG engine write through the
        filesystem store without knowing its concrete method signature.
        """

        config = _episode_config_from_payload(payload)
        series_id = str(payload.get("series_id") or "default-series")
        bundle = self.create_bundle(
            series_id=series_id,
            episode_number=int(payload.get("episode_number", 1)),
            prompt=config.prompt,
            config=config,
            outline={"text": payload.get("outline", "")},
            script=payload.get("script"),
            metadata={
                "engine_episode_id": payload.get("episode_id"),
                "audio_metadata": payload.get("audio_metadata") or {},
                "storage_metadata": payload.get("storage_metadata") or {},
            },
        )
        return {
            "bundle_path": bundle.paths["episode_dir"],
            "cache_key": bundle.cache_key,
            "episode_id": bundle.episode_id,
        }

    def create_bundle(
        self,
        series_id: str,
        episode_number: int,
        prompt: str,
        config: EpisodeConfig,
        outline: dict[str, Any] | list[Any] | None = None,
        script: list[ScriptLine] | list[dict[str, Any]] | str | None = None,
        metadata: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> EpisodeBundle:
        key = cache_key or stable_cache_key(prompt, config)
        episode_id = f"episode-{episode_number:04d}"
        episode_dir = self.storage_dir / "episodes" / series_id / episode_id
        episode_dir.mkdir(parents=True, exist_ok=True)

        paths: dict[str, str] = {"episode_dir": str(episode_dir)}
        (episode_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        paths["prompt"] = str(episode_dir / "prompt.txt")

        _write_json(episode_dir / "config.json", config)
        paths["config"] = str(episode_dir / "config.json")

        files = {
            "prompt": "prompt.txt",
            "config": "config.json",
        }
        if outline is not None:
            _write_json(episode_dir / "outline.json", outline)
            paths["outline"] = str(episode_dir / "outline.json")
            files["outline"] = "outline.json"

        if script is not None:
            if isinstance(script, str):
                script_path = episode_dir / "script.xml"
                script_path.write_text(script, encoding="utf-8")
            else:
                script_path = episode_dir / "script.json"
                _write_json(script_path, script)
            paths["script"] = str(script_path)
            files["script"] = script_path.name

        metadata_payload = {
            **(metadata or {}),
            "cache_key": key,
            "episode_id": episode_id,
            "episode_number": episode_number,
            "files": files,
            "prompt": prompt,
            "series_id": series_id,
        }
        _write_json(episode_dir / "metadata.json", metadata_payload)
        paths["metadata"] = str(episode_dir / "metadata.json")

        return EpisodeBundle(
            series_id=series_id,
            episode_id=episode_id,
            episode_number=episode_number,
            cache_key=key,
            prompt=prompt,
            config=config,
            paths=paths,
        )


def _episode_config_from_payload(payload: dict[str, Any]) -> EpisodeConfig:
    config_data = dict(payload.get("config") or {})
    prompt = str(payload.get("premise") or payload.get("prompt") or "")
    cast = dict(config_data.get("cast") or {})
    if not cast:
        cast = {
            "cast_roles": config_data.get("cast_roles") or {},
            "effects": config_data.get("effects") or {},
            "episode_structure": config_data.get("episode_structure") or [],
            "voices": config_data.get("voices") or {},
        }
    return EpisodeConfig(
        prompt=prompt,
        minutes=int(config_data.get("minutes", 0)),
        tone=str(config_data.get("tone", "")),
        cast=cast,
        tts_model=config_data.get("tts_model"),
        model_version=config_data.get("model_version"),
    )
