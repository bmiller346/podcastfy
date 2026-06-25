"""Cinematic audio cue sheet helpers for LitRPG scripts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


CUE_TAG_PATTERN = re.compile(
    r"\[(BGM_START|BGM_STOP|SFX|AMBIENCE_START|AMBIENCE_STOP)(?::\s*([^\]]*?))?\]",
    re.IGNORECASE,
)

DEFAULT_ASSET_ROOT = "assets/litrpg"
DEFAULT_EXTENSIONS = (".wav", ".mp3", ".ogg")

_CUE_TYPE_ALIASES = {
    "BGM_START": "bgm_start",
    "BGM_STOP": "bgm_stop",
    "SFX": "sfx",
    "AMBIENCE_START": "ambience_start",
    "AMBIENCE_STOP": "ambience_stop",
}

DEFAULT_ASSET_LIBRARY: dict[str, tuple[str, ...]] = {
    "battle": ("music/battle_loop", "music/boss_pressure", "music/combat_pulse"),
    "boss": ("music/boss_pressure", "sfx/monster_roar", "sfx/low_hit"),
    "dungeon": ("ambience/dungeon_room", "ambience/stone_corridor", "ambience/deep_air"),
    "forest": ("ambience/dark_forest", "ambience/night_insects", "ambience/wind_leaves"),
    "tavern": ("ambience/tavern_low", "ambience/fireplace", "sfx/mug_clink"),
    "ui": ("sfx/ui_chime", "sfx/quest_popup", "sfx/menu_tick"),
    "quest": ("sfx/quest_popup", "sfx/ui_chime", "sfx/soft_riser"),
    "level_up": ("sfx/level_up", "sfx/ui_chime", "sfx/sparkle_burst"),
    "sword": ("sfx/sword_clash", "sfx/blade_unsheathe", "sfx/metal_hit"),
    "spell": ("sfx/spell_cast", "sfx/magic_whoosh", "sfx/arcane_hit"),
    "door": ("sfx/stone_door", "sfx/wood_door_creak", "sfx/lock_click"),
    "crowd": ("ambience/arena_crowd", "sfx/crowd_gasp", "sfx/crowd_cheer"),
}


@dataclass(slots=True)
class AudioCue:
    """One semantic bracket tag extracted from a script."""

    cue_id: str
    cue_type: str
    tag: str = ""
    modifiers: dict[str, Any] = field(default_factory=dict)
    source_offset: int = 0
    clean_offset: int = 0
    line_number: int = 1
    raw_tag: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CueSheet:
    """Ordered cinematic cues plus the script with cue tags removed."""

    cues: list[AudioCue]
    clean_script: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clean_script": self.clean_script,
            "cues": [cue.to_dict() for cue in self.cues],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AssetCandidate:
    """A possible local asset path for a semantic cue."""

    semantic_tag: str
    cue_type: str
    candidates: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_cue_sheet(script: str) -> CueSheet:
    """Extract cinematic audio cues and remove bracket cue tags from a script."""
    text = str(script or "")
    cues: list[AudioCue] = []
    clean_parts: list[str] = []
    last_source_offset = 0
    removed_chars = 0

    for index, match in enumerate(CUE_TAG_PATTERN.finditer(text), start=1):
        clean_parts.append(text[last_source_offset : match.start()])
        raw_type = match.group(1).upper()
        cue_type = _CUE_TYPE_ALIASES[raw_type]
        body = (match.group(2) or "").strip()
        tag, modifiers = _parse_tag_body(body)
        clean_offset = match.start() - removed_chars
        cue = AudioCue(
            cue_id=f"cue-{index:03d}",
            cue_type=cue_type,
            tag=tag,
            modifiers=modifiers,
            source_offset=match.start(),
            clean_offset=clean_offset,
            line_number=text.count("\n", 0, match.start()) + 1,
            raw_tag=match.group(0),
        )
        cues.append(cue)
        removed_chars += match.end() - match.start()
        last_source_offset = match.end()

    clean_parts.append(text[last_source_offset:])
    clean_script = _clean_script_text("".join(clean_parts))
    metadata = {
        "cue_count": len(cues),
        "cue_types": _cue_type_counts(cues),
        "has_music": any(cue.cue_type.startswith("bgm_") for cue in cues),
        "has_ambience": any(cue.cue_type.startswith("ambience_") for cue in cues),
        "has_sfx": any(cue.cue_type == "sfx" for cue in cues),
    }
    return CueSheet(cues=cues, clean_script=clean_script, metadata=metadata)


def map_assets_for_cue(
    cue: AudioCue | Mapping[str, Any],
    *,
    asset_library: Mapping[str, Sequence[str]] | None = None,
    asset_root: str = DEFAULT_ASSET_ROOT,
    extensions: Sequence[str] = DEFAULT_EXTENSIONS,
) -> AssetCandidate:
    """Map a semantic cue to deterministic local asset candidates.

    The returned paths are future mixer hints only. The helper does not check
    whether any asset exists.
    """
    cue_type = str(_cue_value(cue, "cue_type") or "").lower()
    tag = str(_cue_value(cue, "tag") or "").strip()
    if cue_type.endswith("_stop"):
        return AssetCandidate(
            semantic_tag=tag,
            cue_type=cue_type,
            candidates=[],
            metadata={"matched_library": False, "candidate_count": 0, "control_cue": True},
        )
    library = asset_library or DEFAULT_ASSET_LIBRARY
    stems = _library_stems_for_tag(tag, library)
    matched_library = bool(stems)
    if not stems:
        stems = [_fallback_asset_stem(cue_type, tag)]
    candidates = [
        f"{asset_root.rstrip('/')}/{stem}{extension}"
        for stem in stems
        for extension in extensions
    ]
    return AssetCandidate(
        semantic_tag=tag,
        cue_type=cue_type,
        candidates=candidates,
        metadata={
            "matched_library": matched_library,
            "candidate_count": len(candidates),
        },
    )


def map_assets_for_cue_sheet(
    cue_sheet: CueSheet | Mapping[str, Any],
    *,
    asset_library: Mapping[str, Sequence[str]] | None = None,
    asset_root: str = DEFAULT_ASSET_ROOT,
) -> list[AssetCandidate]:
    cues = _cue_sheet_cues(cue_sheet)
    return [
        map_assets_for_cue(cue, asset_library=asset_library, asset_root=asset_root)
        for cue in cues
    ]


def build_mix_plan(
    cue_sheet: CueSheet | Mapping[str, Any],
    *,
    asset_mappings: Sequence[AssetCandidate | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build deterministic metadata for a future cinematic audio mixer."""
    cues = _cue_sheet_cues(cue_sheet)
    mappings = list(asset_mappings or map_assets_for_cue_sheet(cue_sheet))
    mapping_by_tag_type = {
        (
            str(_mapping_value(mapping, "semantic_tag")),
            str(_mapping_value(mapping, "cue_type")),
        ): mapping
        for mapping in mappings
    }

    layers: list[dict[str, Any]] = [
        {
            "layer_id": "dialogue",
            "type": "dialogue",
            "timing": {"anchor": "clean_script", "start": 0},
            "ducking": {"receives_priority": True},
            "pan": "center",
            "eq_intent": "voice clarity, high-pass rumble, preserve intelligibility",
        }
    ]
    automations: list[dict[str, Any]] = []
    active_music: dict[str, Any] | None = None
    active_ambience: dict[str, Any] | None = None

    for cue in cues:
        cue_type = _cue_value(cue, "cue_type")
        tag = _cue_value(cue, "tag")
        modifiers = dict(_cue_value(cue, "modifiers") or {})
        anchor = _timing_anchor(cue)
        if cue_type == "sfx":
            layers.append(_sfx_layer(cue, mapping_by_tag_type, anchor, modifiers))
            continue
        if cue_type == "bgm_start":
            active_music = _bed_layer("music", cue, mapping_by_tag_type, anchor, modifiers)
            layers.append(active_music)
            continue
        if cue_type == "bgm_stop":
            automations.append(_stop_automation("music", cue, active_music, anchor))
            active_music = None
            continue
        if cue_type == "ambience_start":
            active_ambience = _bed_layer("ambience", cue, mapping_by_tag_type, anchor, modifiers)
            layers.append(active_ambience)
            continue
        if cue_type == "ambience_stop":
            automations.append(_stop_automation("ambience", cue, active_ambience, anchor))
            active_ambience = None
            continue

    return {
        "version": 1,
        "strategy": "metadata_only_future_mixdown",
        "timing_model": "cue anchors use clean script character offsets until renderer timestamps exist",
        "layers": layers,
        "automations": automations,
        "metadata": {
            "cue_count": len(cues),
            "layer_count": len(layers),
            "ducking_policy": "dialogue priority; music and ambience may duck when requested or by default",
        },
    }


def _parse_tag_body(body: str) -> tuple[str, dict[str, Any]]:
    if not body:
        return "", {}
    normalized = body.replace(",", " ")
    parts = [part for part in normalized.split() if part]
    tag_parts: list[str] = []
    modifiers: dict[str, Any] = {}
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().lower().replace("-", "_")
            if key:
                modifiers[key] = _parse_modifier_value(value)
        else:
            tag_parts.append(part)
    return " ".join(tag_parts).strip(), modifiers


def _parse_modifier_value(value: str) -> Any:
    clean = value.strip().strip('"').strip("'")
    lower = clean.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", clean):
        number = float(clean)
        return int(number) if number.is_integer() else number
    return clean


def _clean_script_text(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _cue_type_counts(cues: Sequence[AudioCue]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cue in cues:
        counts[cue.cue_type] = counts.get(cue.cue_type, 0) + 1
    return counts


def _library_stems_for_tag(
    tag: str,
    asset_library: Mapping[str, Sequence[str]],
) -> list[str]:
    normalized = _normalize_tag(tag)
    for key, stems in asset_library.items():
        normalized_key = _normalize_tag(key)
        if normalized == normalized_key or normalized_key in normalized:
            return [str(stem).strip().lstrip("/").replace("\\", "/") for stem in stems]
    return []


def _fallback_asset_stem(cue_type: str, tag: str) -> str:
    folder = "sfx"
    if cue_type.startswith("bgm_"):
        folder = "music"
    elif cue_type.startswith("ambience_"):
        folder = "ambience"
    slug = _normalize_tag(tag) or "unassigned"
    return f"{folder}/{slug}"


def _normalize_tag(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _cue_sheet_cues(cue_sheet: CueSheet | Mapping[str, Any]) -> list[Any]:
    if isinstance(cue_sheet, CueSheet):
        return list(cue_sheet.cues)
    return list(cue_sheet.get("cues", []))


def _cue_value(cue: AudioCue | Mapping[str, Any], key: str) -> Any:
    if isinstance(cue, AudioCue):
        return getattr(cue, key)
    return cue.get(key)


def _mapping_value(mapping: AssetCandidate | Mapping[str, Any], key: str) -> Any:
    if isinstance(mapping, AssetCandidate):
        return getattr(mapping, key)
    return mapping.get(key)


def _timing_anchor(cue: AudioCue | Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cue_id": _cue_value(cue, "cue_id"),
        "line_number": _cue_value(cue, "line_number"),
        "clean_offset": _cue_value(cue, "clean_offset"),
        "source_offset": _cue_value(cue, "source_offset"),
    }


def _candidate_paths(
    cue: AudioCue | Mapping[str, Any],
    mapping_by_tag_type: Mapping[tuple[str, str], AssetCandidate | Mapping[str, Any]],
) -> list[str]:
    key = (str(_cue_value(cue, "tag")), str(_cue_value(cue, "cue_type")))
    mapping = mapping_by_tag_type.get(key)
    if mapping is None:
        return []
    return list(_mapping_value(mapping, "candidates") or [])


def _sfx_layer(
    cue: AudioCue | Mapping[str, Any],
    mapping_by_tag_type: Mapping[tuple[str, str], AssetCandidate | Mapping[str, Any]],
    anchor: Mapping[str, Any],
    modifiers: Mapping[str, Any],
) -> dict[str, Any]:
    tag = str(_cue_value(cue, "tag") or "sfx")
    return {
        "layer_id": f"sfx:{_cue_value(cue, 'cue_id')}",
        "type": "sfx",
        "semantic_tag": tag,
        "asset_candidates": _candidate_paths(cue, mapping_by_tag_type),
        "timing": {"anchor": dict(anchor), "placement": "instantaneous"},
        "volume": modifiers.get("volume", "unity"),
        "ducking": {"ducks_under_dialogue": bool(modifiers.get("duck", False))},
        "pan": modifiers.get("pan", "center"),
        "eq_intent": "transient clarity, trim masking frequencies around dialogue",
    }


def _bed_layer(
    bed_type: str,
    cue: AudioCue | Mapping[str, Any],
    mapping_by_tag_type: Mapping[tuple[str, str], AssetCandidate | Mapping[str, Any]],
    anchor: Mapping[str, Any],
    modifiers: Mapping[str, Any],
) -> dict[str, Any]:
    tag = str(_cue_value(cue, "tag") or bed_type)
    return {
        "layer_id": f"{bed_type}:{_cue_value(cue, 'cue_id')}",
        "type": bed_type,
        "semantic_tag": tag,
        "asset_candidates": _candidate_paths(cue, mapping_by_tag_type),
        "timing": {"start_anchor": dict(anchor), "end_anchor": None, "loop": True},
        "volume": modifiers.get("volume", "-12db" if bed_type == "music" else "-18db"),
        "ducking": {"ducks_under_dialogue": bool(modifiers.get("duck", True))},
        "pan": modifiers.get("pan", "wide" if bed_type == "music" else "stereo"),
        "eq_intent": (
            "wide bed, low-mid cleanup, leave center space for dialogue"
            if bed_type == "music"
            else "environment texture, high-pass rumble, avoid speech band buildup"
        ),
    }


def _stop_automation(
    bed_type: str,
    cue: AudioCue | Mapping[str, Any],
    active_layer: Mapping[str, Any] | None,
    anchor: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "automation_id": f"stop:{_cue_value(cue, 'cue_id')}",
        "type": f"{bed_type}_stop",
        "target_layer_id": active_layer.get("layer_id") if active_layer else None,
        "timing": {"anchor": dict(anchor), "fade": "short"},
        "intent": f"fade out active {bed_type} bed",
    }
