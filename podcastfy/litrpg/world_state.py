"""Persistent sensory world-state helpers for LitRPG scene rendering."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

WORLD_STATE_FILENAME = "world_state.json"
WORLD_STATE_SCHEMA_VERSION = 1
WORLD_STATE_TOP_LEVEL_KEYS = (
    "characters",
    "locations",
    "artifacts",
    "system_items",
    "magic_signatures",
    "active_mysteries",
    "established_rules",
    "sensory_hooks",
    "visual_budget",
    "metadata",
)

BEAT_SENSORY_MAP: dict[str, dict[str, str]] = {
    "disaster": {"focus": "narrow", "time": "slowed", "dominant_sense": "sound/touch"},
    "exploration": {"focus": "wide", "time": "normal", "dominant_sense": "visual/smell"},
    "reflection": {"focus": "internal", "time": "expanded", "dominant_sense": "memory/touch"},
    "apex": {"focus": "tunnel", "time": "fragmented", "dominant_sense": "all competing"},
    "social": {"focus": "faces", "time": "normal", "dominant_sense": "voice/micro-expression"},
    "loot": {"focus": "object", "time": "slowed", "dominant_sense": "visual/tactile"},
    "combat": {"focus": "narrow", "time": "slowed", "dominant_sense": "sound/touch"},
    "mystery": {"focus": "selective", "time": "normal", "dominant_sense": "visual/silence"},
}


@dataclass(slots=True)
class SceneBrief:
    spatial_anchor: str = ""
    sensory_priority: list[str] = field(default_factory=list)
    active_characters: list[dict[str, str]] = field(default_factory=list)
    threat_geometry: str = ""
    mood_target: str = ""
    forbidden: list[str] = field(default_factory=list)
    must_establish: list[str] = field(default_factory=list)
    sensory_hooks: list[str] = field(default_factory=list)
    active_artifacts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SensoryHookLibrary:
    """Select established sensory anchors for a scene without inventing prose."""

    def __init__(self, world_state: Mapping[str, Any] | None = None) -> None:
        self.world_state = normalize_world_state(world_state or {})

    def get_hooks(
        self,
        *,
        location_id: str = "",
        character_ids: Sequence[str] | None = None,
        artifact_ids: Sequence[str] | None = None,
        beat_type: str = "",
    ) -> dict[str, Any]:
        characters = [
            _character_signature(self.world_state, character_id)
            for character_id in (character_ids or [])
        ]
        artifacts = [
            _artifact_signature(self.world_state, artifact_id)
            for artifact_id in (artifact_ids or [])
        ]
        return {
            "established_hooks": _location_hooks(self.world_state, location_id),
            "character_signatures": [item for item in characters if item],
            "artifact_signatures": [item for item in artifacts if item],
            "beat_sensory_mode": sensory_mode_for_beat(beat_type),
        }


def normalize_world_state(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a stable world-state mapping with the supported top-level keys."""

    source = copy.deepcopy(dict(data or {}))
    return {
        "schema_version": int(source.get("schema_version") or WORLD_STATE_SCHEMA_VERSION),
        "series_id": str(source.get("series_id") or "default-series"),
        "characters": _mapping(source.get("characters")),
        "locations": _mapping(source.get("locations")),
        "artifacts": _mapping(source.get("artifacts")),
        "system_items": _mapping(source.get("system_items")),
        "magic_signatures": _mapping(source.get("magic_signatures")),
        "active_mysteries": _mapping(source.get("active_mysteries")),
        "established_rules": _string_list(source.get("established_rules") or source.get("rules")),
        "sensory_hooks": _mapping(source.get("sensory_hooks")),
        "visual_budget": _mapping(source.get("visual_budget")),
        "metadata": _mapping(source.get("metadata")),
    }


class WorldStateManager:
    """Small persistence and validation facade for sensory world state."""

    def __init__(self, storage_dir: str | Path, series_id: str) -> None:
        self.storage_dir = Path(storage_dir)
        self.series_id = str(series_id or "default-series")

    def read(self) -> dict[str, Any]:
        return load_world_state(self.storage_dir, self.series_id)

    def write(self, state: Mapping[str, Any]) -> Path:
        return save_world_state(self.storage_dir, self.series_id, state)

    def update_delta(self, delta: Mapping[str, Any]) -> dict[str, Any]:
        state = self.read()
        merged = merge_world_state_delta(state, delta)
        self.write(merged)
        return merged

    def get_character(self, character_id: str) -> dict[str, Any]:
        return _entity(self.read(), "characters", character_id)

    def get_location(self, location_id: str) -> dict[str, Any]:
        return _entity(self.read(), "locations", location_id)

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        return _entity(self.read(), "artifacts", artifact_id)

    def lock_mystery(self, mystery_id: str, status: str = "DO_NOT_SPEND", **fields: Any) -> dict[str, Any]:
        state = self.read()
        mysteries = state.setdefault("active_mysteries", {})
        mystery = mysteries.setdefault(str(mystery_id), {})
        if isinstance(mystery, Mapping):
            mystery.update(fields)
            mystery["status"] = status
        self.write(state)
        return dict(mystery) if isinstance(mystery, Mapping) else {}

    def validate_consistency(self) -> dict[str, Any]:
        return validate_world_state_consistency(self.read())

    def validate_character_consistency(self, character_id: str, prose_or_event: str) -> dict[str, Any]:
        state = self.read()
        character = _entity(state, "characters", character_id)
        violations = []
        for forbidden in _string_list(character.get("aliases_forbidden")):
            if _contains_token(prose_or_event, forbidden):
                violations.append(
                    {
                        "type": "forbidden_character_alias",
                        "character_id": character_id,
                        "token": forbidden,
                    }
                )
        return _validation_result(violations=violations)

    def validate_artifact_consistency(self, artifact_id: str, prose_or_event: str) -> dict[str, Any]:
        state = self.read()
        artifact = _entity(state, "artifacts", artifact_id)
        violations = []
        for forbidden in _string_list(artifact.get("aliases_forbidden")):
            if _contains_token(prose_or_event, forbidden):
                violations.append(
                    {
                        "type": "forbidden_artifact_alias",
                        "artifact_id": artifact_id,
                        "token": forbidden,
                    }
                )
        locked_name = str(artifact.get("locked_name") or "")
        if locked_name and artifact_id in str(prose_or_event) and not _contains_token(prose_or_event, locked_name):
            violations.append(
                {
                    "type": "artifact_locked_name_missing",
                    "artifact_id": artifact_id,
                    "locked_name": locked_name,
                }
            )
        return _validation_result(violations=violations)


def load_world_state(storage_dir: str | Path, series_id: str) -> dict[str, Any]:
    path = world_state_path(storage_dir, series_id)
    if not path.exists():
        return normalize_world_state({"series_id": series_id})
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return normalize_world_state({"series_id": series_id})
    if not isinstance(payload, Mapping):
        return normalize_world_state({"series_id": series_id})
    payload = dict(payload)
    payload.setdefault("series_id", series_id)
    return normalize_world_state(payload)


def save_world_state(storage_dir: str | Path, series_id: str, state: Mapping[str, Any]) -> Path:
    path = world_state_path(storage_dir, series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_world_state({**dict(state), "series_id": series_id})
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def world_state_path(storage_dir: str | Path, series_id: str) -> Path:
    return Path(storage_dir) / "series" / str(series_id) / WORLD_STATE_FILENAME


def merge_world_state_delta(
    current: Mapping[str, Any],
    update: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge a post-generation world-state delta into a normalized state."""

    merged = normalize_world_state(current)
    for character, payload in (update.get("character_updates") or {}).items():
        _merge_mapping_entity(merged, "characters", character, payload)
    for character, payload in (update.get("characters") or {}).items():
        _merge_mapping_entity(merged, "characters", character, payload)
    for location, payload in (update.get("new_locations") or {}).items():
        _merge_mapping_entity(merged, "locations", location, payload)
    for location, payload in (update.get("locations") or {}).items():
        _merge_mapping_entity(merged, "locations", location, payload)
    for artifact, payload in (update.get("new_artifacts") or {}).items():
        _merge_mapping_entity(merged, "artifacts", artifact, payload)
    for artifact, payload in (update.get("artifact_updates") or {}).items():
        _merge_mapping_entity(merged, "artifacts", artifact, payload)
    for artifact, payload in (update.get("artifact_state_updates") or {}).items():
        if isinstance(payload, Mapping):
            existing = merged["artifacts"].setdefault(str(artifact), {})
            if isinstance(existing, Mapping):
                state = existing.setdefault("state", {})
                if isinstance(state, Mapping):
                    state.update(payload)
    for item, payload in (update.get("system_items") or update.get("new_system_items") or {}).items():
        _merge_mapping_entity(merged, "system_items", item, payload)
    for signature, payload in (update.get("magic_signatures") or update.get("new_magic_signatures") or {}).items():
        _merge_mapping_entity(merged, "magic_signatures", signature, payload)
    for location, hooks in (update.get("new_sensory_hooks") or {}).items():
        values = merged["sensory_hooks"].setdefault(str(location), [])
        if isinstance(values, list):
            for hook in _string_list(hooks):
                _append_unique(values, hook)
    for hook_id, payload in (update.get("sensory_hooks") or {}).items():
        existing = merged["sensory_hooks"].get(str(hook_id))
        if isinstance(existing, list):
            for hook in _string_list(payload):
                _append_unique(existing, hook)
        elif isinstance(payload, Mapping):
            merged["sensory_hooks"][str(hook_id)] = dict(payload)
        else:
            merged["sensory_hooks"][str(hook_id)] = _string_list(payload)
    for mystery, payload in (update.get("mysteries_touched") or {}).items():
        _merge_mapping_entity(merged, "active_mysteries", mystery, payload)
    for mystery, payload in (update.get("active_mysteries") or {}).items():
        _merge_mapping_entity(merged, "active_mysteries", mystery, payload)
    for rule in _string_list(update.get("new_rules")):
        _append_unique(merged["established_rules"], rule)
    for rule in _string_list(update.get("established_rules")):
        _append_unique(merged["established_rules"], rule)
    if isinstance(update.get("visual_budget"), Mapping):
        merged["visual_budget"].update(dict(update["visual_budget"]))
    if isinstance(update.get("visual_budget_additions"), Mapping):
        additions = merged["visual_budget"].setdefault("additions", {})
        if isinstance(additions, Mapping):
            additions.update(dict(update["visual_budget_additions"]))
    if isinstance(update.get("artifact_uses"), Mapping):
        uses = merged["metadata"].setdefault("artifact_uses", {})
        if isinstance(uses, Mapping):
            uses.update(dict(update["artifact_uses"]))
    if isinstance(update.get("arcs_progressed"), Mapping):
        merged["metadata"]["arcs_progressed"] = dict(update["arcs_progressed"])
    if isinstance(update.get("metadata"), Mapping):
        merged["metadata"].update(dict(update["metadata"]))
    return normalize_world_state(merged)


def validate_world_state_consistency(state: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_world_state(state)
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    violations.extend(_visual_budget_violations(normalized))
    violations.extend(_artifact_alias_violations(normalized))
    violations.extend(_locked_name_violations(normalized))
    violations.extend(_mystery_spend_violations(normalized))
    return _validation_result(violations=violations, warnings=warnings)


def sensory_mode_for_beat(beat_type: str) -> dict[str, str]:
    normalized = _normalize(beat_type)
    for key, value in BEAT_SENSORY_MAP.items():
        if key in normalized:
            return dict(value)
    return {"focus": "grounded", "time": "normal", "dominant_sense": "visual/sound"}


def build_scene_brief(
    *,
    world_state: Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
    prior_chapter_tail: str = "",
) -> SceneBrief:
    """Build a deterministic rendering contract from world state and chapter metadata."""

    state = normalize_world_state(world_state or {})
    contract = dict(chapter_contract or {})
    location_id = str(contract.get("location") or contract.get("setting") or "")
    location = _select_location(state, location_id)
    beat_type = str(contract.get("beat_type") or contract.get("scene_type") or contract.get("phase") or "")
    mode = sensory_mode_for_beat(beat_type)
    character_ids = _string_list(contract.get("character_focus") or contract.get("characters"))
    artifact_ids = _active_artifact_ids(state, contract, character_ids)
    library = SensoryHookLibrary(state)
    hooks = library.get_hooks(
        location_id=location_id or str(location.get("id") or location.get("name") or ""),
        character_ids=character_ids,
        artifact_ids=artifact_ids,
        beat_type=beat_type,
    )
    forbidden = [
        *_forbidden_mysteries(state),
        *_contract_forbidden_revelations(contract),
    ]
    artifact_contracts = _active_artifact_entries(state, artifact_ids)
    for artifact in artifact_contracts:
        for alias in _string_list(artifact.get("aliases_forbidden")):
            forbidden.append(f"{artifact.get('id')}: forbidden alias {alias}")
    must_establish = _must_establish(location, state, prior_chapter_tail)
    if artifact_contracts:
        must_establish.append("re-anchor active artifacts on first meaningful use")
    return SceneBrief(
        spatial_anchor=_spatial_anchor(location, contract),
        sensory_priority=_sensory_priority(location, mode),
        active_characters=_active_character_entries(state, character_ids),
        threat_geometry=str(
            location.get("threat_geometry")
            or contract.get("threat_geometry")
            or "Ground exits, distances, cover, and retreat options before action."
        ),
        mood_target=str(contract.get("mood_target") or contract.get("phase") or "grounded urgency"),
        forbidden=forbidden,
        must_establish=must_establish,
        sensory_hooks=_dedupe(
            [
                *hooks.get("established_hooks", []),
                *hooks.get("character_signatures", []),
                *hooks.get("artifact_signatures", []),
                f"{mode['focus']} focus; {mode['dominant_sense']} leads; time feels {mode['time']}",
            ]
        )[:8],
        active_artifacts=artifact_contracts,
    )


def build_scene_brief_prompt(
    *,
    world_state: Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
    prior_chapter_tail: str = "",
) -> str:
    """Build the optional LLM prepass prompt for scene-brief generation."""

    return f"""You are a scene director, not a prose writer.
Given the world state and chapter beat, produce a SCENE BRIEF only.
No prose. No narrative. Just the rendering contract for this scene.

The brief must orient spatial + sensory + threat before action. Re-trigger established character anchors; do not re-describe everyone from scratch. Preserve injuries, gear damage, physical degradation, and locked mysteries.

Output JSON:
{{
  "spatial_anchor": "one sentence: where we are, ceiling/scale, exit count or retreat geometry",
  "sensory_priority": ["most important sense first", "second", "third"],
  "active_characters": [{{"id": "character_id", "entry_state": "", "emotional_tell_active": ""}}],
  "threat_geometry": "what the danger looks like spatially",
  "mood_target": "the emotional texture the scene must achieve",
  "forbidden": ["things the prose must NOT do: spend mysteries, resolve arcs early, reset injuries"],
  "must_establish": ["facts that must be grounded before action starts"],
  "sensory_hooks": ["3-5 specific details that make this scene lived-in, not generic"],
  "active_artifacts": [{{"id": "artifact_id", "locked_name": "", "physical_signature": {{}}, "power_ceiling": {{}}, "aliases_forbidden": [], "state": {{}}}}]
}}

Artifact rules:
- Use locked artifact names and do not rename artifacts.
- Re-anchor active artifacts on first meaningful use.
- Obey artifact power ceiling and current resource state: ammo, charges, condition, location, and separation.

World state:
{json.dumps(normalize_world_state(world_state or {}), indent=2, sort_keys=True)}

Chapter contract:
{json.dumps(dict(chapter_contract or {}), indent=2, sort_keys=True)}

Prior chapter tail:
{prior_chapter_tail or "No prior tail supplied."}
"""


def format_scene_brief_context(
    scene_brief: SceneBrief | Mapping[str, Any],
    *,
    world_state: Mapping[str, Any] | None = None,
) -> str:
    brief = scene_brief.to_dict() if isinstance(scene_brief, SceneBrief) else dict(scene_brief)
    state = normalize_world_state(world_state or {})
    characters = state.get("characters") if isinstance(state.get("characters"), Mapping) else {}
    active = brief.get("active_characters") if isinstance(brief.get("active_characters"), Sequence) else []
    active_artifacts = brief.get("active_artifacts") if isinstance(brief.get("active_artifacts"), Sequence) else []
    character_lines = []
    for item in active:
        if isinstance(item, Mapping):
            character_lines.append(
                f"{item.get('id')}: entry={item.get('entry_state')}; tell={item.get('emotional_tell_active')}"
            )
    if not character_lines and characters:
        for name in list(characters)[:4]:
            signature = _character_signature(state, str(name))
            if signature:
                character_lines.append(f"{name}: {signature}")
    artifact_lines = []
    for item in active_artifacts:
        if isinstance(item, Mapping):
            physical = _mapping(item.get("physical_signature"))
            ceiling = _mapping(item.get("power_ceiling"))
            resource_state = _mapping(item.get("state"))
            artifact_lines.append(
                _compact(
                    f"{item.get('id')}: locked_name={item.get('locked_name')}; "
                    f"signature={_format_mapping_values(physical)}; "
                    f"power_ceiling={_format_mapping_values(ceiling)}; "
                    f"forbidden_aliases={', '.join(_string_list(item.get('aliases_forbidden')))}; "
                    f"state={_format_mapping_values(resource_state)}",
                    limit=420,
                )
            )
    return "\n".join(
        [
            "Scene rendering contract:",
            f"- Spatial anchor: {brief.get('spatial_anchor') or 'Ground the reader before action.'}",
            f"- Sensory priority: {', '.join(_string_list(brief.get('sensory_priority'))) or 'visual, sound, smell'}",
            f"- Threat geometry: {brief.get('threat_geometry') or 'Clarify exits, cover, and danger radius.'}",
            f"- Mood target: {brief.get('mood_target') or 'grounded urgency'}",
            _format_lines("Active character rendering", character_lines),
            _format_lines("Active artifact rendering", artifact_lines),
            _format_lines("Must establish before action", _string_list(brief.get("must_establish"))),
            _format_lines("Forbidden rendering moves", _string_list(brief.get("forbidden"))),
            _format_lines("Sensory hooks to re-trigger", _string_list(brief.get("sensory_hooks"))),
            "- Artifact naming/resource contract: use locked names; do not rename artifacts; re-anchor active artifacts on first meaningful use; obey artifact power ceilings and ammo/charges/condition.",
        ]
    )


def build_world_state_update_prompt(
    *,
    final_script: str,
    current_world_state: Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
) -> str:
    """Build the post-chapter delta prompt for a world-state updater pass."""

    return f"""Read this chapter. Output ONLY the world state delta: changes, additions, and newly established rendering facts.
Do not summarize the chapter. Do not rewrite prose. Do not invent off-page facts.

Return JSON:
{{
  "character_updates": {{"character_id": {{"last_known_state": {{"injuries": [], "equipment": [], "emotional_arc": ""}}}}}},
  "new_locations": {{}},
  "new_artifacts": {{"artifact_id": {{"locked_name": "", "physical_signature": {{}}, "power_ceiling": {{}}, "state": {{}}}}}},
  "artifact_updates": {{"artifact_id": {{"state": {{"condition": "", "ammo": null, "charges": null, "location": "", "separated_from_owner": false}}}}}},
  "artifact_state_updates": {{"artifact_id": {{"ammo": null, "charges": null, "condition": ""}}}},
  "artifact_uses": {{"artifact_id": {{"chapter_use": "", "resources_spent": ""}}}},
  "system_items": {{"item_id": {{"display_name": "", "system_description": "", "actual_behavior": "", "irony_flag": true, "carl_commentary": ""}}}},
  "magic_signatures": {{"signature_id": {{"signature": "", "primary_sense": "", "shared_signature_group": ""}}}},
  "new_sensory_hooks": {{"location_id": ["specific detail established in this chapter"]}},
  "visual_budget_additions": {{"signature_id": "light/color/sound token added or reserved"}},
  "mysteries_touched": {{"mystery_id": {{"hints_dropped": []}}}},
  "new_rules": [],
  "arcs_progressed": {{}}
}}

Artifact updates must preserve locked names, forbidden aliases, resource state, and power ceilings.

Current world state:
{json.dumps(normalize_world_state(current_world_state or {}), indent=2, sort_keys=True)}

Chapter contract:
{json.dumps(dict(chapter_contract or {}), indent=2, sort_keys=True)}

Chapter script:
{final_script}
"""


def build_artifact_forge_prompt(
    *,
    character: Mapping[str, Any] | str,
    beat_type: str = "",
    world_tone: str = "",
    power_ceiling: Mapping[str, Any] | str | None = None,
    forbidden_solutions: Sequence[str] | None = None,
    active_mysteries: Mapping[str, Any] | Sequence[str] | None = None,
) -> str:
    """Build a structured prompt for designing a bounded artifact."""

    return f"""Design one LitRPG artifact as structured JSON only.
No prose outside JSON. Do not solve locked mysteries. Do not create a power that bypasses forbidden solutions.

Output JSON schema:
{{
  "locked_name": "",
  "physical_signature": {{
    "appearance": "",
    "weight": "",
    "sound_fire": "",
    "sound_load": "",
    "smell": "",
    "recoil": "",
    "primary_sense": "",
    "behavioral_quirk": ""
  }},
  "power_ceiling": {{
    "can_do": [],
    "cannot_do": [],
    "narrative_cost": "",
    "DO_NOT_ESCALATE_BEYOND": ""
  }},
  "personality": "",
  "first_appearance_hook": "",
  "state": {{
    "condition": "",
    "ammo": null,
    "charges": null,
    "location": "",
    "separated_from_owner": false
  }}
}}

Character:
{json.dumps(character if isinstance(character, Mapping) else {"description": str(character)}, indent=2, sort_keys=True)}

Beat type: {beat_type or "unspecified"}
World tone: {world_tone or "grounded, specific, limited"}
Power ceiling:
{json.dumps(power_ceiling if isinstance(power_ceiling, Mapping) else {"ceiling": str(power_ceiling or "")}, indent=2, sort_keys=True)}
Forbidden solutions:
{json.dumps(_string_list(forbidden_solutions), indent=2, sort_keys=True)}
Active mysteries:
{json.dumps(active_mysteries if isinstance(active_mysteries, Mapping) else _string_list(active_mysteries), indent=2, sort_keys=True)}
"""


def _select_location(state: Mapping[str, Any], location_id: str) -> dict[str, Any]:
    locations = state.get("locations") if isinstance(state.get("locations"), Mapping) else {}
    if location_id and isinstance(locations.get(location_id), Mapping):
        return dict(locations[location_id])
    for key, value in locations.items():
        if isinstance(value, Mapping):
            item = dict(value)
            item.setdefault("id", key)
            return item
    return {}


def _spatial_anchor(location: Mapping[str, Any], contract: Mapping[str, Any]) -> str:
    sensory = _mapping(location.get("sensory"))
    spatial = str(sensory.get("spatial") or location.get("spatial") or "")
    name = str(location.get("name") or location.get("id") or contract.get("location") or contract.get("setting") or "the scene")
    if spatial:
        return f"{name}: {spatial}"
    return f"{name}: establish scale, sightlines, exits, and nearest threat before action."


def _sensory_priority(location: Mapping[str, Any], mode: Mapping[str, str]) -> list[str]:
    sensory = _mapping(location.get("sensory"))
    available = [key for key in ("visual", "audio", "smell", "touch", "spatial") if sensory.get(key)]
    dominant = str(mode.get("dominant_sense") or "")
    ordered = []
    for token in dominant.replace("/", " ").split():
        if token == "sound":
            token = "audio"
        if token in available:
            ordered.append(token)
    return _dedupe([*ordered, *available, "visual", "audio", "smell"])[:3]


def _active_character_entries(state: Mapping[str, Any], character_ids: Sequence[str]) -> list[dict[str, str]]:
    characters = state.get("characters") if isinstance(state.get("characters"), Mapping) else {}
    entries = []
    for character_id in character_ids:
        character = characters.get(character_id)
        if not isinstance(character, Mapping):
            continue
        tells = _mapping(character.get("emotional_tells"))
        state_map = _mapping(character.get("last_known_state"))
        entries.append(
            {
                "id": str(character_id),
                "entry_state": _compact(
                    "; ".join(
                        _string_list(state_map.get("injuries"))
                        + _string_list(state_map.get("equipment"))
                        + [str(state_map.get("emotional_arc") or "")]
                    )
                ),
                "emotional_tell_active": _compact("; ".join(f"{key}: {value}" for key, value in list(tells.items())[:2])),
            }
        )
    return entries


def _character_signature(state: Mapping[str, Any], character_id: str) -> str:
    characters = state.get("characters") if isinstance(state.get("characters"), Mapping) else {}
    character = characters.get(character_id)
    if not isinstance(character, Mapping):
        return ""
    values = [
        *_string_list(character.get("appearance"))[:2],
        *_string_list(character.get("signature_behaviors"))[:2],
    ]
    if character.get("voice"):
        values.append(f"voice: {character['voice']}")
    return _compact("; ".join(values))


def _artifact_signature(state: Mapping[str, Any], artifact_id: str) -> str:
    artifact = _entity(state, "artifacts", artifact_id)
    if not artifact:
        return ""
    physical = _mapping(artifact.get("physical_signature"))
    values = [
        str(artifact.get("locked_name") or artifact_id),
        *_string_list(physical.get("appearance"))[:1],
        *_string_list(physical.get("sound_fire"))[:1],
        *_string_list(physical.get("smell"))[:1],
        *_string_list(physical.get("behavioral_quirk"))[:1],
    ]
    return _compact("; ".join(value for value in values if value))


def _active_artifact_ids(
    state: Mapping[str, Any],
    contract: Mapping[str, Any],
    character_ids: Sequence[str],
) -> list[str]:
    ids = _string_list(contract.get("active_artifacts"))
    ids.extend(_string_list(contract.get("artifact_focus")))
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), Mapping) else {}
    for character_id in character_ids:
        character = _entity(state, "characters", character_id)
        owned = _string_list(character.get("owned_artifacts") or character.get("artifacts"))
        for artifact_id, artifact in artifacts.items():
            if not isinstance(artifact, Mapping):
                continue
            owner = str(artifact.get("owner") or "")
            if owner and _normalize(owner) == _normalize(character_id):
                owned.append(str(artifact_id))
        ids.extend(owned)
    return _dedupe(ids)


def _active_artifact_entries(state: Mapping[str, Any], artifact_ids: Sequence[str]) -> list[dict[str, Any]]:
    entries = []
    for artifact_id in artifact_ids:
        artifact = _entity(state, "artifacts", artifact_id)
        if not artifact:
            continue
        entries.append(
            {
                "id": str(artifact_id),
                "type": str(artifact.get("type") or ""),
                "owner": str(artifact.get("owner") or ""),
                "locked_name": str(artifact.get("locked_name") or artifact.get("name") or artifact_id),
                "aliases_forbidden": _string_list(artifact.get("aliases_forbidden")),
                "physical_signature": _mapping(artifact.get("physical_signature")),
                "behavioral_rules": _string_list(artifact.get("behavioral_rules")),
                "power_ceiling": _mapping(artifact.get("power_ceiling")),
                "state": _mapping(artifact.get("state")),
                "emotional_resonance": str(artifact.get("emotional_resonance") or ""),
            }
        )
    return entries


def _location_hooks(state: Mapping[str, Any], location_id: str) -> list[str]:
    hooks = state.get("sensory_hooks") if isinstance(state.get("sensory_hooks"), Mapping) else {}
    values = _string_list(hooks.get(location_id))
    location = _select_location(state, location_id)
    sensory = _mapping(location.get("sensory"))
    values.extend(str(value) for value in sensory.values() if value)
    return _dedupe(values)


def _forbidden_mysteries(state: Mapping[str, Any]) -> list[str]:
    mysteries = state.get("active_mysteries") if isinstance(state.get("active_mysteries"), Mapping) else {}
    forbidden = []
    for name, payload in mysteries.items():
        if not isinstance(payload, Mapping):
            continue
        status = str(payload.get("status") or "").upper()
        if status in {"DO_NOT_SPEND", "LOCKED", "HINT_ONLY"}:
            forbidden.append(f"{name}: {status}")
    return forbidden


def _contract_forbidden_revelations(contract: Mapping[str, Any]) -> list[str]:
    conspiracy = contract.get("conspiracy") if isinstance(contract.get("conspiracy"), Mapping) else {}
    forbidden = _string_list(conspiracy.get("forbidden_revelations"))
    reader = conspiracy.get("reader_position") if isinstance(conspiracy.get("reader_position"), Mapping) else {}
    forbidden.extend(
        f"reader must not confirm: {item}" for item in _string_list(reader.get("must_not_know_yet"))
    )
    return _dedupe(forbidden)


def _must_establish(location: Mapping[str, Any], state: Mapping[str, Any], prior_tail: str) -> list[str]:
    values = [
        "spatial orientation before action",
        "sensory anchor before exposition",
        "current physical state before heroics",
    ]
    if location.get("threat_geometry"):
        values.append(str(location["threat_geometry"]))
    rules = _string_list(state.get("established_rules"))
    values.extend(rules[:2])
    if prior_tail:
        values.append("honor prior chapter tail before moving on")
    return _dedupe(values)


def _format_lines(title: str, values: Sequence[str]) -> str:
    clean = [value for value in values if str(value or "").strip()]
    if not clean:
        return f"- {title}: none supplied"
    return f"- {title}: " + " | ".join(clean)


def _format_mapping_values(value: Mapping[str, Any]) -> str:
    parts = []
    for key, item in value.items():
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            text = ", ".join(str(part) for part in item if str(part or "").strip())
        else:
            text = str(item)
        if text.strip():
            parts.append(f"{key}={text}")
    return "; ".join(parts) or "none"


def _entity(state: Mapping[str, Any], collection: str, entity_id: str) -> dict[str, Any]:
    values = state.get(collection) if isinstance(state.get(collection), Mapping) else {}
    item = values.get(str(entity_id)) if isinstance(values, Mapping) else None
    return dict(item) if isinstance(item, Mapping) else {}


def _merge_mapping_entity(
    state: dict[str, Any],
    collection: str,
    entity_id: str,
    payload: Any,
) -> None:
    if not isinstance(payload, Mapping):
        return
    existing = state.setdefault(collection, {}).setdefault(str(entity_id), {})
    if isinstance(existing, Mapping):
        _deep_merge(existing, payload)


def _deep_merge(target: dict[str, Any], payload: Mapping[str, Any]) -> None:
    for key, value in payload.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), Mapping):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _append_unique(values: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and _normalize(text) not in {_normalize(item) for item in values}:
        values.append(text)


def _validation_result(
    *,
    violations: Sequence[Mapping[str, Any]] | None = None,
    warnings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    violation_list = [dict(item) for item in violations or []]
    warning_list = [dict(item) for item in warnings or []]
    return {
        "passed": not violation_list,
        "violations": violation_list,
        "warnings": warning_list,
    }


def _visual_budget_violations(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    token_owners: dict[str, list[dict[str, str]]] = {}
    for owner in _collect_signature_tokens(state):
        token_owners.setdefault(_normalize(owner["token"]), []).append(owner)
    violations = []
    for normalized_token, owners in token_owners.items():
        if not normalized_token or len(owners) < 2:
            continue
        groups = {owner.get("shared_signature_group", "") for owner in owners if owner.get("shared_signature_group")}
        allowed = any(owner.get("allowed_reuse") for owner in owners)
        owner_ids = {f"{owner['kind']}:{owner['id']}" for owner in owners}
        if len(owner_ids) > 1 and not allowed and not groups:
            violations.append(
                {
                    "type": "duplicate_sensory_token",
                    "token": owners[0]["token"],
                    "owners": sorted(owner_ids),
                }
            )
    return violations


def _collect_signature_tokens(state: Mapping[str, Any]) -> list[dict[str, str]]:
    owners: list[dict[str, str]] = []
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), Mapping) else {}
    for artifact_id, artifact in artifacts.items():
        if isinstance(artifact, Mapping):
            _add_signature_tokens(
                owners,
                kind="artifact",
                owner_id=str(artifact_id),
                payload=_mapping(artifact.get("physical_signature")),
                metadata=artifact,
            )
    signatures = state.get("magic_signatures") if isinstance(state.get("magic_signatures"), Mapping) else {}
    for signature_id, signature in signatures.items():
        if isinstance(signature, Mapping):
            _add_signature_tokens(
                owners,
                kind="magic_signature",
                owner_id=str(signature_id),
                payload=signature,
                metadata=signature,
            )
    hooks = state.get("sensory_hooks") if isinstance(state.get("sensory_hooks"), Mapping) else {}
    for hook_id, hook in hooks.items():
        if isinstance(hook, Mapping):
            _add_signature_tokens(owners, kind="sensory_hook", owner_id=str(hook_id), payload=hook, metadata=hook)
    return owners


def _add_signature_tokens(
    owners: list[dict[str, str]],
    *,
    kind: str,
    owner_id: str,
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> None:
    for key in ("appearance", "visual", "color", "light", "sound", "sound_fire", "sound_load", "audio", "signature"):
        for token in _string_list(payload.get(key)):
            owners.append(
                {
                    "kind": kind,
                    "id": owner_id,
                    "token": token,
                    "shared_signature_group": str(metadata.get("shared_signature_group") or ""),
                    "allowed_reuse": str(metadata.get("allowed_reuse") or ""),
                }
            )


def _artifact_alias_violations(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    violations = []
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), Mapping) else {}
    for artifact_id, artifact in artifacts.items():
        if not isinstance(artifact, Mapping):
            continue
        locked_name = str(artifact.get("locked_name") or "")
        for alias in _string_list(artifact.get("aliases_forbidden")):
            if locked_name and _normalize(alias) == _normalize(locked_name):
                violations.append(
                    {
                        "type": "artifact_alias_forbids_locked_name",
                        "artifact_id": str(artifact_id),
                        "alias": alias,
                    }
                )
    return violations


def _locked_name_violations(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    violations = []
    for collection in ("artifacts", "system_items"):
        values = state.get(collection) if isinstance(state.get(collection), Mapping) else {}
        for item_id, item in values.items():
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("locked_name") or item.get("display_name") or "")
            normalized = _normalize(name)
            if not normalized:
                continue
            owner = f"{collection}:{item_id}"
            if normalized in seen and seen[normalized] != owner:
                violations.append(
                    {
                        "type": "duplicate_locked_name",
                        "locked_name": name,
                        "owners": sorted([seen[normalized], owner]),
                    }
                )
            seen[normalized] = owner
    return violations


def _mystery_spend_violations(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    violations = []
    mysteries = state.get("active_mysteries") if isinstance(state.get("active_mysteries"), Mapping) else {}
    for mystery_id, mystery in mysteries.items():
        if not isinstance(mystery, Mapping):
            continue
        status = str(mystery.get("status") or "").upper()
        if status not in {"SPENT", "REVEALED", "RESOLVED"}:
            continue
        allowed_stage = str(mystery.get("allowed_stage") or "")
        allowed_book = mystery.get("allowed_book")
        current_stage = str(state.get("metadata", {}).get("stage") or mystery.get("current_stage") or "")
        current_book = state.get("metadata", {}).get("book") or mystery.get("current_book")
        if allowed_stage and current_stage and _normalize(current_stage) != _normalize(allowed_stage):
            violations.append(
                {
                    "type": "mystery_spent_before_allowed_stage",
                    "mystery_id": str(mystery_id),
                    "allowed_stage": allowed_stage,
                    "current_stage": current_stage,
                }
            )
        if allowed_book is not None and current_book is not None:
            try:
                if int(current_book) < int(allowed_book):
                    violations.append(
                        {
                            "type": "mystery_spent_before_allowed_book",
                            "mystery_id": str(mystery_id),
                            "allowed_book": allowed_book,
                            "current_book": current_book,
                        }
                    )
            except (TypeError, ValueError):
                pass
    return violations


def _contains_token(text: str, token: str) -> bool:
    return _normalize(token) in _normalize(text)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(item) for item in value.values() if str(item or "").strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _dedupe(values: Sequence[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = _normalize(text)
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _normalize(value: str) -> str:
    return " ".join(str(value or "").lower().replace("-", "_").split())


def _compact(value: str, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
