"""Curated local SFX asset manifest helpers for LitRPG audio cues."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


ASSET_MANIFEST_VERSION = 1
DEFAULT_AUDIO_EXTENSIONS = (".wav", ".mp3", ".ogg")
VALID_CUE_TYPES = {
    "sfx",
    "bgm_start",
    "bgm_stop",
    "ambience_start",
    "ambience_stop",
}


@dataclass(slots=True)
class AssetManifestEntry:
    """One reviewed or review-pending local audio asset."""

    stem: str
    tags: list[str] = field(default_factory=list)
    cue_types: list[str] = field(default_factory=lambda: ["sfx"])
    loopable: bool = False
    default_lufs: float | int = -18
    intensity: int = 5
    pan_safe: bool = True
    transient: bool = True
    source: str = "manual"
    trusted: bool = False
    license: str = ""
    attribution: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AssetManifestEntry":
        stem = str(data.get("stem") or data.get("path") or "").strip()
        return cls(
            stem=_normalize_stem(stem),
            tags=_dedupe_strings(
                _as_string_list(data.get("tags") or data.get("tag") or [])
            ),
            cue_types=_dedupe_strings(
                _as_string_list(data.get("cue_types") or ["sfx"])
            ),
            loopable=data.get("loopable", False),
            default_lufs=data.get("default_lufs", -18),
            intensity=data.get("intensity", 5),
            pan_safe=data.get("pan_safe", True),
            transient=data.get("transient", True),
            source=str(data.get("source", "manual")),
            trusted=data.get("trusted", False),
            license=str(data.get("license", "")),
            attribution=str(data.get("attribution", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AssetManifest:
    """Versioned collection of local asset entries."""

    version: int = ASSET_MANIFEST_VERSION
    assets: list[AssetManifestEntry] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AssetManifest":
        assets = data.get("assets", [])
        if not isinstance(assets, Sequence) or isinstance(assets, (str, bytes)):
            raise ValueError("Asset manifest 'assets' must be a list")
        return cls(
            version=int(data.get("version", ASSET_MANIFEST_VERSION)),
            assets=[
                AssetManifestEntry.from_mapping(asset)
                for asset in assets
                if isinstance(asset, Mapping)
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "assets": [asset.to_dict() for asset in self.assets],
        }


def load_asset_manifest_file(path: str | Path, *, validate: bool = True) -> AssetManifest:
    """Load the editable curated asset manifest."""
    with Path(path).open("r", encoding="utf-8") as manifest_file:
        data = json.load(manifest_file)
    if not isinstance(data, Mapping):
        raise ValueError("Asset manifest must contain a JSON object")
    manifest = AssetManifest.from_mapping(data)
    if validate:
        validate_asset_manifest(manifest)
    return manifest


def save_asset_manifest_file(
    manifest: AssetManifest | Mapping[str, Any],
    path: str | Path,
) -> None:
    """Write a manifest in the shape consumed by ``sfx.load_asset_manifest``."""
    resolved = _coerce_manifest(manifest)
    validate_asset_manifest(resolved)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(resolved.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def validate_asset_manifest(manifest: AssetManifest | Mapping[str, Any]) -> None:
    """Raise ``ValueError`` for invalid curated asset metadata."""
    resolved = _coerce_manifest(manifest)
    if resolved.version != ASSET_MANIFEST_VERSION:
        raise ValueError(f"Unsupported asset manifest version: {resolved.version}")
    seen_stems: set[str] = set()
    for index, asset in enumerate(resolved.assets):
        prefix = f"assets[{index}]"
        stem = _normalize_stem(asset.stem)
        if not stem:
            raise ValueError(f"{prefix}.stem is required")
        if stem in seen_stems:
            raise ValueError(f"Duplicate asset stem: {stem}")
        seen_stems.add(stem)
        if not asset.tags:
            raise ValueError(f"{prefix}.tags must contain at least one tag")
        if not asset.cue_types:
            raise ValueError(f"{prefix}.cue_types must contain at least one cue type")
        invalid_cue_types = sorted(set(asset.cue_types) - VALID_CUE_TYPES)
        if invalid_cue_types:
            raise ValueError(
                f"{prefix}.cue_types contains unsupported values: {invalid_cue_types}"
            )
        if not isinstance(asset.loopable, bool):
            raise ValueError(f"{prefix}.loopable must be a boolean")
        if not isinstance(asset.default_lufs, (int, float)):
            raise ValueError(f"{prefix}.default_lufs must be numeric")
        if not isinstance(asset.intensity, int) or not 0 <= asset.intensity <= 10:
            raise ValueError(f"{prefix}.intensity must be between 0 and 10")
        if not isinstance(asset.pan_safe, bool):
            raise ValueError(f"{prefix}.pan_safe must be a boolean")
        if not isinstance(asset.transient, bool):
            raise ValueError(f"{prefix}.transient must be a boolean")
        for field_name in ("source", "license", "attribution"):
            if not isinstance(getattr(asset, field_name), str):
                raise ValueError(f"{prefix}.{field_name} must be a string")
        if not isinstance(asset.trusted, bool):
            raise ValueError(f"{prefix}.trusted must be a boolean")


def add_or_promote_asset(
    manifest: AssetManifest | Mapping[str, Any],
    asset: AssetManifestEntry | Mapping[str, Any],
    *,
    promote: bool = False,
) -> AssetManifest:
    """Add an entry or merge it into an existing stem without duplicate tags."""
    resolved = _coerce_manifest(manifest)
    incoming = _coerce_entry(asset)
    existing = next((item for item in resolved.assets if item.stem == incoming.stem), None)
    if existing is None:
        if promote:
            incoming.trusted = True
        resolved.assets.append(incoming)
        validate_asset_manifest(resolved)
        return resolved

    existing.tags = _dedupe_strings([*existing.tags, *incoming.tags])
    existing.cue_types = _dedupe_strings([*existing.cue_types, *incoming.cue_types])
    existing.loopable = incoming.loopable
    existing.default_lufs = incoming.default_lufs
    existing.intensity = incoming.intensity
    existing.pan_safe = incoming.pan_safe
    existing.transient = incoming.transient
    existing.source = incoming.source or existing.source
    existing.license = incoming.license or existing.license
    existing.attribution = incoming.attribution or existing.attribution
    existing.trusted = bool(existing.trusted or incoming.trusted or promote)
    validate_asset_manifest(resolved)
    return resolved


def scan_asset_directory(
    asset_dir: str | Path,
    *,
    extensions: Sequence[str] = DEFAULT_AUDIO_EXTENSIONS,
    source: str = "local_scan",
) -> list[AssetManifestEntry]:
    """Return untrusted manifest candidates for audio files under ``asset_dir``."""
    root = Path(asset_dir)
    allowed = {extension.lower() for extension in extensions}
    candidates: list[AssetManifestEntry] = []
    if not root.exists():
        return candidates
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.suffix.lower() not in allowed:
            continue
        stem = path.relative_to(root).with_suffix("").as_posix()
        cue_types = _cue_types_for_stem(stem)
        tags = _tags_from_stem(stem)
        candidates.append(
            AssetManifestEntry(
                stem=stem,
                tags=tags,
                cue_types=cue_types,
                loopable=cue_types[0] in {"bgm_start", "ambience_start"},
                default_lufs=_default_lufs_for_cue_type(cue_types[0]),
                intensity=5,
                pan_safe=True,
                transient=cue_types[0] == "sfx",
                source=source,
                trusted=False,
                license="",
                attribution="",
            )
        )
    return candidates


def _coerce_manifest(manifest: AssetManifest | Mapping[str, Any]) -> AssetManifest:
    if isinstance(manifest, AssetManifest):
        for asset in manifest.assets:
            _coerce_entry(asset)
        return manifest
    if isinstance(manifest, Mapping):
        return AssetManifest.from_mapping(manifest)
    raise ValueError("Asset manifest must be an AssetManifest or JSON object")


def _coerce_entry(asset: AssetManifestEntry | Mapping[str, Any]) -> AssetManifestEntry:
    if isinstance(asset, AssetManifestEntry):
        asset.stem = _normalize_stem(asset.stem)
        asset.tags = _dedupe_strings(asset.tags)
        asset.cue_types = _dedupe_strings(asset.cue_types)
        return asset
    if isinstance(asset, Mapping):
        return AssetManifestEntry.from_mapping(asset)
    raise ValueError("Asset entry must be an AssetManifestEntry or JSON object")


def _normalize_stem(value: str) -> str:
    stem = str(value or "").strip().replace("\\", "/").lstrip("/")
    for extension in DEFAULT_AUDIO_EXTENSIONS:
        if stem.lower().endswith(extension):
            return stem[: -len(extension)]
    return stem


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return []


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            deduped.append(clean)
            seen.add(key)
    return deduped


def _cue_types_for_stem(stem: str) -> list[str]:
    first_part = stem.split("/", 1)[0].lower()
    if first_part in {"music", "bgm"}:
        return ["bgm_start"]
    if first_part in {"ambience", "amb", "ambient"}:
        return ["ambience_start"]
    return ["sfx"]


def _default_lufs_for_cue_type(cue_type: str) -> int:
    if cue_type == "bgm_start":
        return -24
    if cue_type == "ambience_start":
        return -28
    return -18


def _tags_from_stem(stem: str) -> list[str]:
    basename = Path(stem).name
    clean = re.sub(r"[_\-.]+", " ", basename).strip().lower()
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"\b\d+\b$", "", clean).strip()
    tokens = [token for token in clean.split(" ") if token and not token.isdigit()]
    tags = [clean] if clean else []
    tags.extend(tokens)
    return _dedupe_strings(tags)
