"""Deterministic validation and asset selection for LitRPG mix plans."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.sfx import AssetCandidate


CONTROL_CUE_TYPES = {"bgm_stop", "ambience_stop"}
BED_LAYER_TYPES = {"music", "ambience"}
NON_CONTROL_LAYER_TYPES = {"music", "ambience", "sfx"}
LOUD_SFX_VOLUME_DB = -9.0
LOUD_SFX_LUFS = -16.0
LOUD_SFX_INTENSITY = 8

SAFE_LAYER_DEFAULTS: dict[str, dict[str, Any]] = {
    "dialogue": {
        "volume": "unity",
        "ducking": {"receives_priority": True},
        "pan": "center",
    },
    "music": {
        "volume": "-12db",
        "ducking": {"ducks_under_dialogue": True},
        "pan": "wide",
    },
    "ambience": {
        "volume": "-18db",
        "ducking": {"ducks_under_dialogue": True},
        "pan": "stereo",
    },
    "sfx": {
        "volume": "-9db",
        "ducking": {"ducks_under_dialogue": False},
        "pan": "center",
    },
}


def select_asset_candidates(
    asset_mappings: AssetCandidate | Mapping[str, Any] | Sequence[AssetCandidate | Mapping[str, Any]],
    *,
    cue_type: str | None = None,
    semantic_tag: str | None = None,
    max_candidates: int | None = None,
) -> list[str]:
    """Return deterministic candidate paths from asset mappings.

    When structured asset metadata is available, candidates whose asset metadata
    is marked ``trusted: true`` sort first. Assets declaring ``cue_types`` are
    only considered for matching cue types, which keeps an ambience asset from
    being selected for a one-shot SFX cue just because the tag text overlaps.
    """
    entries = _candidate_entries(asset_mappings, cue_type=cue_type, semantic_tag=semantic_tag)
    selected: list[str] = []
    seen: set[str] = set()
    for entry in sorted(entries, key=_selection_sort_key):
        path = str(entry["path"])
        if path in seen:
            continue
        selected.append(path)
        seen.add(path)
        if max_candidates is not None and len(selected) >= max_candidates:
            break
    return selected


def normalize_mix_plan_defaults(mix_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of a mix plan with safe volume, ducking, and pan defaults."""
    normalized = deepcopy(dict(mix_plan or {}))
    layers = normalized.setdefault("layers", [])
    if not isinstance(layers, list):
        normalized["layers"] = []
        return normalized

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_type = str(layer.get("type") or "").lower()
        defaults = SAFE_LAYER_DEFAULTS.get(layer_type, SAFE_LAYER_DEFAULTS["sfx"])
        layer.setdefault("volume", defaults["volume"])
        layer.setdefault("pan", defaults["pan"])
        ducking = layer.get("ducking")
        if not isinstance(ducking, dict):
            layer["ducking"] = deepcopy(defaults["ducking"])
        else:
            for key, value in defaults["ducking"].items():
                ducking.setdefault(key, value)
    return normalized


def validate_mix_plan(
    mix_plan: Mapping[str, Any],
    *,
    asset_mappings: Sequence[AssetCandidate | Mapping[str, Any]] | None = None,
    final_mode: bool = False,
) -> dict[str, Any]:
    """Validate a metadata-only mix plan before a real mixer consumes it."""
    plan = normalize_mix_plan_defaults(mix_plan)
    asset_index = _asset_index(asset_mappings or [])
    issues = list(plan.get("issues") or [])
    warnings: list[str] = []

    for layer in plan.get("layers", []):
        if not isinstance(layer, Mapping):
            continue
        layer_type = str(layer.get("type") or "").lower()
        if layer_type not in NON_CONTROL_LAYER_TYPES:
            continue

        layer_id = str(layer.get("layer_id") or layer_type)
        candidates = _layer_candidate_paths(layer)
        selected_asset = str(layer.get("selected_asset") or "").strip()
        used_paths = [selected_asset] if selected_asset else candidates

        if not used_paths:
            issues.append(f"{layer_id}: missing asset candidates for {layer_type} cue")
            continue

        metadata_items = _metadata_for_paths(used_paths, layer, asset_index)
        if final_mode:
            for path, metadata in zip(used_paths, metadata_items, strict=False):
                if metadata.get("trusted") is False:
                    issues.append(f"{layer_id}: untrusted asset in final mode: {path}")

        if layer_type in BED_LAYER_TYPES:
            for path, metadata in zip(used_paths, metadata_items, strict=False):
                if metadata.get("loopable") is False:
                    issues.append(f"{layer_id}: non-loopable asset used as {layer_type} bed: {path}")
            if not _ducks_under_dialogue(layer):
                warnings.append(f"{layer_id}: missing ducking on {layer_type} bed")

        if layer_type == "sfx" and _is_loud_sfx_risk(layer, metadata_items):
            warnings.append(f"{layer_id}: loud SFX over dialogue risk")

    for automation in plan.get("automations", []):
        if not isinstance(automation, Mapping):
            continue
        automation_type = str(automation.get("type") or "")
        if automation_type.endswith("_stop") and not automation.get("target_layer_id"):
            automation_id = str(automation.get("automation_id") or automation_type)
            issues.append(f"{automation_id}: stop cue without target layer")

    return {
        "ready": not issues,
        "issues": _dedupe_preserve_order(issues),
        "warnings": _dedupe_preserve_order(warnings),
        "metadata": {
            "issue_count": len(_dedupe_preserve_order(issues)),
            "warning_count": len(_dedupe_preserve_order(warnings)),
            "final_mode": bool(final_mode),
        },
    }


def mix_audio_locally(
    *,
    dialogue_path: str | Path,
    output_path: str | Path,
    mix_plan: Mapping[str, Any],
    asset_mappings: Sequence[AssetCandidate | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Render a minimal local mixdown when dialogue and assets exist.

    The current timing model only has script character offsets, so placements
    are approximate. The function is still intentionally real: it loads audio,
    overlays existing assets, writes a mixed file, and reports skipped layers.
    """
    dialogue = Path(dialogue_path)
    output = Path(output_path)
    if not dialogue.exists():
        return {
            "mixed": False,
            "output_path": str(output),
            "issues": [f"dialogue audio not found: {dialogue}"],
            "skipped_layers": [],
            "applied_layers": [],
        }

    try:
        from pydub import AudioSegment
    except Exception as exc:
        return {
            "mixed": False,
            "output_path": str(output),
            "issues": [f"local mixer unavailable: {exc}"],
            "skipped_layers": [],
            "applied_layers": [],
        }

    plan = normalize_mix_plan_defaults(mix_plan)
    validation = validate_mix_plan(plan, asset_mappings=asset_mappings or [])
    issues = list(validation.get("issues") or [])
    warnings = list(validation.get("warnings") or [])
    applied_layers: list[str] = []
    skipped_layers: list[str] = []

    try:
        base = AudioSegment.from_file(dialogue)
    except Exception as exc:
        return {
            "mixed": False,
            "output_path": str(output),
            "issues": [f"could not read dialogue audio: {exc}"],
            "warnings": warnings,
            "skipped_layers": skipped_layers,
            "applied_layers": applied_layers,
        }

    mixed = base
    for layer in plan.get("layers", []):
        if not isinstance(layer, Mapping):
            continue
        layer_type = str(layer.get("type") or "").lower()
        if layer_type == "dialogue":
            continue
        layer_id = str(layer.get("layer_id") or layer_type)
        asset_path = _first_existing_asset(layer)
        if asset_path is None:
            skipped_layers.append(layer_id)
            continue
        try:
            segment = AudioSegment.from_file(asset_path)
        except Exception as exc:
            issues.append(f"{layer_id}: could not read asset {asset_path}: {exc}")
            skipped_layers.append(layer_id)
            continue

        segment += _volume_to_db(layer.get("volume")) or 0.0
        start_ms = _layer_start_ms(layer, duration_ms=len(base))
        if layer_type in BED_LAYER_TYPES:
            segment = _loop_to_duration(segment, max(1, len(base) - start_ms))
        mixed = mixed.overlay(segment, position=start_ms)
        applied_layers.append(layer_id)

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        mixed.export(output, format=_export_format(output))
    except Exception as exc:
        return {
            "mixed": False,
            "output_path": str(output),
            "issues": [*issues, f"could not export mixed audio: {exc}"],
            "warnings": warnings,
            "skipped_layers": skipped_layers,
            "applied_layers": applied_layers,
        }
    return {
        "mixed": True,
        "output_path": str(output),
        "issues": _dedupe_preserve_order(issues),
        "warnings": _dedupe_preserve_order(warnings),
        "skipped_layers": skipped_layers,
        "applied_layers": applied_layers,
        "duration_ms": len(mixed),
    }


def _candidate_entries(
    asset_mappings: AssetCandidate | Mapping[str, Any] | Sequence[AssetCandidate | Mapping[str, Any]],
    *,
    cue_type: str | None,
    semantic_tag: str | None,
) -> list[dict[str, Any]]:
    mappings = _as_mapping_sequence(asset_mappings)
    normalized_cue_type = str(cue_type or "").lower()
    normalized_tag = str(semantic_tag or "")
    entries: list[dict[str, Any]] = []
    for mapping_index, mapping in enumerate(mappings):
        mapping_cue_type = str(_mapping_value(mapping, "cue_type") or "").lower()
        mapping_tag = str(_mapping_value(mapping, "semantic_tag") or "")
        if normalized_cue_type and mapping_cue_type != normalized_cue_type:
            continue
        if normalized_tag and mapping_tag != normalized_tag:
            continue
        if mapping_cue_type in CONTROL_CUE_TYPES:
            continue

        assets = _mapping_assets(mapping)
        paths = list(_mapping_value(mapping, "candidates") or [])
        for path_index, path in enumerate(paths):
            path_text = str(path)
            metadata = _metadata_for_candidate_path(path_text, assets)
            if normalized_cue_type and not _metadata_allows_cue_type(metadata, normalized_cue_type):
                continue
            entries.append(
                {
                    "path": path_text,
                    "metadata": metadata,
                    "mapping_index": mapping_index,
                    "path_index": path_index,
                }
            )
    return entries


def _first_existing_asset(layer: Mapping[str, Any]) -> Path | None:
    selected = str(layer.get("selected_asset") or "").strip()
    candidates = [selected] if selected else _layer_candidate_paths(layer)
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _layer_start_ms(layer: Mapping[str, Any], *, duration_ms: int) -> int:
    timing = layer.get("timing")
    anchor: Mapping[str, Any] | None = None
    if isinstance(timing, Mapping):
        raw_anchor = timing.get("anchor") or timing.get("start_anchor")
        if isinstance(raw_anchor, Mapping):
            anchor = raw_anchor
    clean_offset = _to_float(anchor.get("clean_offset") if anchor else None)
    if clean_offset is None or clean_offset <= 0:
        return 0
    # Until renderer timestamps exist, treat roughly 15 chars as one spoken second.
    approx_ms = int((clean_offset / 15.0) * 1000)
    return max(0, min(duration_ms, approx_ms))


def _loop_to_duration(segment: Any, duration_ms: int) -> Any:
    if len(segment) <= 0:
        return segment
    loops = (duration_ms // len(segment)) + 1
    return (segment * loops)[:duration_ms]


def _export_format(output_path: Path) -> str:
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in {"mp3", "wav", "ogg", "flac"}:
        return suffix
    return "mp3"


def _selection_sort_key(entry: Mapping[str, Any]) -> tuple[int, int, int, str]:
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
    trusted = metadata.get("trusted")
    if trusted is True:
        trusted_rank = 0
    elif trusted is False:
        trusted_rank = 2
    else:
        trusted_rank = 1
    return (
        trusted_rank,
        int(entry.get("mapping_index") or 0),
        int(entry.get("path_index") or 0),
        str(entry.get("path") or ""),
    )


def _as_mapping_sequence(
    asset_mappings: AssetCandidate | Mapping[str, Any] | Sequence[AssetCandidate | Mapping[str, Any]],
) -> list[AssetCandidate | Mapping[str, Any]]:
    if isinstance(asset_mappings, AssetCandidate) or isinstance(asset_mappings, Mapping):
        return [asset_mappings]
    return list(asset_mappings or [])


def _mapping_value(mapping: AssetCandidate | Mapping[str, Any], key: str) -> Any:
    if isinstance(mapping, AssetCandidate):
        return getattr(mapping, key)
    return mapping.get(key)


def _mapping_assets(mapping: AssetCandidate | Mapping[str, Any]) -> list[Mapping[str, Any]]:
    metadata = _mapping_value(mapping, "metadata")
    if not isinstance(metadata, Mapping):
        return []
    assets = metadata.get("assets")
    if not isinstance(assets, Sequence) or isinstance(assets, (str, bytes)):
        return []
    return [asset for asset in assets if isinstance(asset, Mapping)]


def _metadata_for_candidate_path(path: str, assets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized_path = _normalize_path(path)
    for asset in assets:
        stem = str(asset.get("stem") or asset.get("path") or "").strip().replace("\\", "/")
        if stem and _path_matches_stem(normalized_path, stem):
            return dict(asset)
    return {}


def _metadata_allows_cue_type(metadata: Mapping[str, Any], cue_type: str) -> bool:
    cue_types = metadata.get("cue_types")
    if cue_types is None:
        return True
    if isinstance(cue_types, str):
        cue_types = [cue_types]
    if not isinstance(cue_types, Sequence):
        return True
    return cue_type in {str(item).lower() for item in cue_types}


def _asset_index(asset_mappings: Sequence[AssetCandidate | Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for mapping in asset_mappings:
        for path in list(_mapping_value(mapping, "candidates") or []):
            metadata = _metadata_for_candidate_path(str(path), _mapping_assets(mapping))
            if metadata:
                indexed[_normalize_path(str(path))] = metadata
    return indexed


def _layer_candidate_paths(layer: Mapping[str, Any]) -> list[str]:
    candidates = layer.get("asset_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return []
    return [str(candidate) for candidate in candidates if str(candidate)]


def _metadata_for_paths(
    paths: Sequence[str],
    layer: Mapping[str, Any],
    asset_index: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    layer_metadata = layer.get("asset_metadata")
    if isinstance(layer_metadata, Mapping):
        return [dict(layer_metadata) for _ in paths]
    return [dict(asset_index.get(_normalize_path(path), {})) for path in paths]


def _ducks_under_dialogue(layer: Mapping[str, Any]) -> bool:
    ducking = layer.get("ducking")
    return isinstance(ducking, Mapping) and ducking.get("ducks_under_dialogue") is True


def _is_loud_sfx_risk(layer: Mapping[str, Any], metadata_items: Sequence[Mapping[str, Any]]) -> bool:
    if _ducks_under_dialogue(layer):
        return False
    volume_db = _volume_to_db(layer.get("volume"))
    if volume_db is None or volume_db > LOUD_SFX_VOLUME_DB:
        return True
    for metadata in metadata_items:
        default_lufs = _to_float(metadata.get("default_lufs"))
        intensity = _to_float(metadata.get("intensity"))
        if default_lufs is not None and default_lufs > LOUD_SFX_LUFS:
            return True
        if intensity is not None and intensity >= LOUD_SFX_INTENSITY:
            return True
    return False


def _volume_to_db(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().lower()
    if text in {"unity", "0", "0db", "+0db"}:
        return 0.0
    if text.endswith("db"):
        return _to_float(text[:-2])
    return _to_float(text)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_path(path: str) -> str:
    return str(PurePosixPath(str(path).replace("\\", "/")))


def _path_matches_stem(path: str, stem: str) -> bool:
    normalized_stem = str(PurePosixPath(stem.replace("\\", "/"))).strip("/")
    path_without_suffix = str(PurePosixPath(path).with_suffix(""))
    return path_without_suffix.endswith(normalized_stem)


def _dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item)
        if text in seen:
            continue
        deduped.append(text)
        seen.add(text)
    return deduped
