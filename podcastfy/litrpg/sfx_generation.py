"""Local SFX generation request metadata for LitRPG audio cues."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_GENERATION_PROVIDER = "local_audiogen"
DEFAULT_GENERATION_MODEL = "audiogen-medium"
DEFAULT_GENERATION_OUTPUT_DIR = "assets/litrpg/generated/audio"
DEFAULT_GENERATION_REQUEST_DIR = "assets/litrpg/generated/requests"
DEFAULT_GENERATION_STATUS = "requested"

MUSIC_CUE_TYPES = {"bgm_start", "ambience_start"}


@dataclass(slots=True)
class GenerateSfxRequest:
    """Metadata-only request for a local SFX generator."""

    tag: str
    cue_type: str
    prompt: str
    provider: str = DEFAULT_GENERATION_PROVIDER
    model: str = DEFAULT_GENERATION_MODEL
    duration_seconds: float = 2.0
    output_dir: str = DEFAULT_GENERATION_OUTPUT_DIR
    status: str = DEFAULT_GENERATION_STATUS
    trusted: bool = False
    cache_path: str = ""
    request_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_local_sfx_prompt(tag: str, cue_type: str = "sfx") -> str:
    """Turn a semantic cue tag into a concrete local audio-generation prompt."""
    clean_tag = _humanize_tag(tag) or "unassigned cue"
    normalized_type = _normalize_cue_type(cue_type)
    detail = _prompt_detail_for_tag(clean_tag, normalized_type)

    if normalized_type == "bgm_start":
        return (
            f"Loopable background music bed for {clean_tag}: {detail}. "
            "Instrumental only, no vocals, no speech, podcast dialogue-safe mix."
        )
    if normalized_type == "ambience_start":
        return (
            f"Loopable ambient environment for {clean_tag}: {detail}. "
            "Natural texture, no melody, no vocals, no speech, leave room for narration."
        )
    if normalized_type.endswith("_stop"):
        return (
            f"Control cue for stopping {clean_tag}; no audio generation needed. "
            "Record this as metadata only."
        )
    return (
        f"Short one-shot sound effect for {clean_tag}: {detail}. "
        "No music, no melody, no vocals, no speech, clean transient, dry tail."
    )


def sfx_cache_path(
    tag: str,
    *,
    provider: str = DEFAULT_GENERATION_PROVIDER,
    model: str = DEFAULT_GENERATION_MODEL,
    duration_seconds: float = 2.0,
    output_dir: str | Path = DEFAULT_GENERATION_OUTPUT_DIR,
    extension: str = ".wav",
) -> str:
    """Return a deterministic generated-audio cache path for a cue request."""
    safe_extension = str(extension or ".wav")
    if not safe_extension.startswith("."):
        safe_extension = f".{safe_extension}"
    parts = [
        _slug(provider) or "provider",
        _slug(model) or "model",
        _duration_slug(duration_seconds),
        _slug(tag) or "unassigned",
    ]
    return str(Path(output_dir) / "__".join(parts)).replace("\\", "/") + safe_extension


def create_generation_request(
    tag: str,
    *,
    cue_type: str = "sfx",
    provider: str = DEFAULT_GENERATION_PROVIDER,
    model: str = DEFAULT_GENERATION_MODEL,
    duration_seconds: float = 2.0,
    output_dir: str | Path = DEFAULT_GENERATION_OUTPUT_DIR,
    status: str = DEFAULT_GENERATION_STATUS,
    write_sidecar: bool = False,
    request_dir: str | Path = DEFAULT_GENERATION_REQUEST_DIR,
) -> dict[str, Any]:
    """Create metadata for a local SFX generation request.

    This function does not import or call a model. When ``write_sidecar`` is
    true it writes the request JSON into a queue directory for a separate local
    worker to consume later.
    """
    normalized_cue_type = _normalize_cue_type(cue_type)
    duration = _coerce_duration(duration_seconds)
    cache_path = sfx_cache_path(
        tag,
        provider=provider,
        model=model,
        duration_seconds=duration,
        output_dir=output_dir,
    )
    request = GenerateSfxRequest(
        tag=str(tag or "").strip(),
        cue_type=normalized_cue_type,
        prompt=build_local_sfx_prompt(tag, normalized_cue_type),
        provider=str(provider or DEFAULT_GENERATION_PROVIDER).strip(),
        model=str(model or DEFAULT_GENERATION_MODEL).strip(),
        duration_seconds=duration,
        output_dir=str(output_dir).replace("\\", "/"),
        status=str(status or DEFAULT_GENERATION_STATUS),
        trusted=False,
        cache_path=cache_path,
    )
    metadata = request.to_dict()
    if write_sidecar:
        sidecar_path = generation_request_sidecar_path(
            tag,
            provider=provider,
            model=model,
            duration_seconds=duration,
            request_dir=request_dir,
        )
        Path(sidecar_path).parent.mkdir(parents=True, exist_ok=True)
        metadata["request_path"] = sidecar_path
        Path(sidecar_path).write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return metadata


def generation_request_sidecar_path(
    tag: str,
    *,
    provider: str = DEFAULT_GENERATION_PROVIDER,
    model: str = DEFAULT_GENERATION_MODEL,
    duration_seconds: float = 2.0,
    request_dir: str | Path = DEFAULT_GENERATION_REQUEST_DIR,
) -> str:
    filename = "__".join(
        [
            _slug(provider) or "provider",
            _slug(model) or "model",
            _duration_slug(duration_seconds),
            _slug(tag) or "unassigned",
        ]
    )
    return str(Path(request_dir) / f"{filename}.json").replace("\\", "/")


def promote_generated_asset_request(
    request: GenerateSfxRequest | Mapping[str, Any],
    generated_file_path: str | Path,
    *,
    asset_root: str | Path = "assets/litrpg",
    status: str = "generated_unreviewed",
) -> dict[str, Any]:
    """Convert a completed local generation request into manifest metadata."""
    request_data = request.to_dict() if isinstance(request, GenerateSfxRequest) else dict(request)
    generated_path = Path(generated_file_path)
    stem = _manifest_stem(generated_path, Path(asset_root))
    cue_type = _normalize_cue_type(str(request_data.get("cue_type") or "sfx"))
    tag = str(request_data.get("tag") or "").strip()
    return {
        "stem": stem,
        "tags": [tag] if tag else [],
        "cue_types": [cue_type],
        "loopable": cue_type in MUSIC_CUE_TYPES,
        "source": "local_ai_generated",
        "provider": request_data.get("provider", DEFAULT_GENERATION_PROVIDER),
        "model": request_data.get("model", DEFAULT_GENERATION_MODEL),
        "prompt": request_data.get("prompt", ""),
        "duration_seconds": request_data.get("duration_seconds"),
        "generated_path": str(generated_path).replace("\\", "/"),
        "cache_path": request_data.get("cache_path", ""),
        "status": status,
        "trusted": False,
    }


def _normalize_cue_type(cue_type: str) -> str:
    return str(cue_type or "sfx").strip().lower().replace("-", "_")


def _coerce_duration(value: float) -> float:
    duration = float(value)
    if duration <= 0:
        raise ValueError("duration_seconds must be greater than zero")
    return int(duration) if duration.is_integer() else duration


def _duration_slug(value: float) -> str:
    duration = _coerce_duration(value)
    text = str(duration).replace(".", "p")
    return f"{text}s"


def _slug(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _humanize_tag(value: str) -> str:
    text = str(value or "").strip().replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _prompt_detail_for_tag(clean_tag: str, cue_type: str) -> str:
    tokens = set(clean_tag.split())
    if "ui" in tokens or "quest" in tokens or "level" in tokens:
        return "crisp fantasy game interface chime, glassy sparkle, quick confirmation"
    if "sword" in tokens or "blade" in tokens:
        return "metal blade clash, sharp impact, brief ring, physical close perspective"
    if "spell" in tokens or "magic" in tokens or "arcane" in tokens:
        return "magical energy whoosh, bright impact, shimmering particles, controlled decay"
    if "door" in tokens or "gate" in tokens:
        return "heavy door movement, hinge friction, latch detail, grounded room tone"
    if "crowd" in tokens or "arena" in tokens:
        return "distant audience reaction, wide stereo space, restrained enough for dialogue"
    if "dungeon" in tokens or "cavern" in tokens:
        return "stone chamber air, subtle drips, low rumble, damp underground reflections"
    if "forest" in tokens:
        return "leaves, soft wind, distant insects, open nighttime space"
    if cue_type == "bgm_start":
        return "tense rhythmic pulse, sparse percussion, cinematic pressure, seamless loop"
    if cue_type == "ambience_start":
        return "steady environmental bed, subtle movement, seamless loop"
    return "clear physical action, focused texture, production-ready effect"


def _manifest_stem(generated_path: Path, asset_root: Path) -> str:
    path_text = str(generated_path.with_suffix("")).replace("\\", "/")
    try:
        relative = generated_path.with_suffix("").resolve().relative_to(asset_root.resolve())
    except (OSError, ValueError):
        return path_text
    return str(relative).replace("\\", "/")
