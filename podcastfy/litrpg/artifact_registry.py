"""Artifact registry facade for locked item identity and state tracking."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.world_state import load_world_state
from podcastfy.litrpg.world_state import merge_world_state_delta
from podcastfy.litrpg.world_state import save_world_state

ARTIFACT_REGISTRY_SCHEMA_VERSION = 1


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    locked_name: str
    type: str = ""
    owner: str = ""
    aliases_forbidden: list[str] = field(default_factory=list)
    physical_signature: dict[str, Any] = field(default_factory=dict)
    behavioral_rules: list[str] = field(default_factory=list)
    power_ceiling: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    emotional_resonance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArtifactRegistryState:
    series_id: str
    schema_version: int = ARTIFACT_REGISTRY_SCHEMA_VERSION
    artifacts: dict[str, ArtifactRecord] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "schema_version": self.schema_version,
            "artifacts": {
                artifact_id: record.to_dict()
                for artifact_id, record in self.artifacts.items()
            },
            "metadata": copy.deepcopy(self.metadata),
        }


class ArtifactRegistry:
    """Read and update the artifact slice of persistent world state."""

    def __init__(self, storage_dir: str | Path, series_id: str) -> None:
        self.storage_dir = Path(storage_dir)
        self.series_id = str(series_id or "default-series")

    def read(self) -> ArtifactRegistryState:
        return artifact_registry_from_world_state(load_world_state(self.storage_dir, self.series_id))

    def write(self, registry: ArtifactRegistryState | Mapping[str, Any]) -> Path:
        state = load_world_state(self.storage_dir, self.series_id)
        registry_state = artifact_registry_from_mapping(registry)
        state["artifacts"] = {
            artifact_id: _artifact_payload(record)
            for artifact_id, record in registry_state.artifacts.items()
        }
        state["metadata"].setdefault("artifact_registry", {}).update(registry_state.metadata)
        return save_world_state(self.storage_dir, self.series_id, state)

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        return self.read().artifacts.get(str(artifact_id))

    def upsert(self, artifact_id: str, artifact: ArtifactRecord | Mapping[str, Any]) -> ArtifactRegistryState:
        registry = self.read()
        record = artifact_record_from_mapping(artifact, fallback_id=artifact_id)
        registry.artifacts[str(artifact_id)] = record
        self.write(registry)
        return registry

    def update_delta(self, update: Mapping[str, Any]) -> ArtifactRegistryState:
        state = load_world_state(self.storage_dir, self.series_id)
        merged = merge_artifact_registry_delta(state, update)
        save_world_state(self.storage_dir, self.series_id, merged)
        return artifact_registry_from_world_state(merged)


def artifact_registry_from_world_state(world_state: Mapping[str, Any]) -> ArtifactRegistryState:
    artifacts = {}
    raw = world_state.get("artifacts") if isinstance(world_state.get("artifacts"), Mapping) else {}
    for artifact_id, payload in raw.items():
        if isinstance(payload, Mapping):
            artifacts[str(artifact_id)] = artifact_record_from_mapping(payload, fallback_id=str(artifact_id))
    metadata = {}
    world_metadata = world_state.get("metadata") if isinstance(world_state.get("metadata"), Mapping) else {}
    if isinstance(world_metadata.get("artifact_registry"), Mapping):
        metadata.update(dict(world_metadata["artifact_registry"]))
    return ArtifactRegistryState(
        series_id=str(world_state.get("series_id") or "default-series"),
        schema_version=ARTIFACT_REGISTRY_SCHEMA_VERSION,
        artifacts=artifacts,
        metadata=metadata,
    )


def artifact_registry_from_mapping(value: ArtifactRegistryState | Mapping[str, Any]) -> ArtifactRegistryState:
    if isinstance(value, ArtifactRegistryState):
        return copy.deepcopy(value)
    data = dict(value)
    artifacts = {}
    raw = data.get("artifacts") if isinstance(data.get("artifacts"), Mapping) else {}
    for artifact_id, payload in raw.items():
        if isinstance(payload, Mapping):
            artifacts[str(artifact_id)] = artifact_record_from_mapping(payload, fallback_id=str(artifact_id))
    return ArtifactRegistryState(
        series_id=str(data.get("series_id") or "default-series"),
        schema_version=int(data.get("schema_version") or ARTIFACT_REGISTRY_SCHEMA_VERSION),
        artifacts=artifacts,
        metadata=dict(data.get("metadata") or {}) if isinstance(data.get("metadata"), Mapping) else {},
    )


def artifact_record_from_mapping(value: ArtifactRecord | Mapping[str, Any], *, fallback_id: str = "") -> ArtifactRecord:
    if isinstance(value, ArtifactRecord):
        return copy.deepcopy(value)
    data = dict(value)
    artifact_id = str(data.get("artifact_id") or data.get("id") or fallback_id or "artifact")
    return ArtifactRecord(
        artifact_id=artifact_id,
        locked_name=str(data.get("locked_name") or data.get("name") or artifact_id),
        type=str(data.get("type") or ""),
        owner=str(data.get("owner") or ""),
        aliases_forbidden=_string_list(data.get("aliases_forbidden")),
        physical_signature=_mapping(data.get("physical_signature")),
        behavioral_rules=_string_list(data.get("behavioral_rules")),
        power_ceiling=_mapping(data.get("power_ceiling")),
        state=_mapping(data.get("state")),
        emotional_resonance=str(data.get("emotional_resonance") or ""),
    )


def build_artifact_forge_prompt(
    *,
    character: Mapping[str, Any] | str,
    beat_type: str = "",
    world_tone: str = "",
    power_ceiling: Mapping[str, Any] | str | None = None,
    forbidden_solutions: Sequence[str] | None = None,
    active_mysteries: Mapping[str, Any] | Sequence[str] | None = None,
    existing_registry: ArtifactRegistryState | Mapping[str, Any] | None = None,
) -> str:
    """Build a JSON-only prompt for creating one bounded artifact registry record."""

    registry = (
        artifact_registry_from_mapping(existing_registry)
        if existing_registry is not None
        else ArtifactRegistryState(series_id="default-series")
    )
    ceiling = power_ceiling if isinstance(power_ceiling, Mapping) else {"ceiling": str(power_ceiling or "")}
    return f"""Design one LitRPG artifact as structured JSON only.
No prose outside JSON. Do not solve locked mysteries. Do not bypass forbidden solutions.
The output must be directly insertable into ArtifactRegistryState.artifacts.

Output JSON schema:
{{
  "artifact_id": "stable_snake_case_id",
  "locked_name": "",
  "type": "weapon|tool|consumable|vehicle|armor|key|system_item|other",
  "owner": "",
  "aliases_forbidden": [],
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
  "behavioral_rules": [],
  "power_ceiling": {{
    "can_do": [],
    "cannot_do": [],
    "narrative_cost": "",
    "DO_NOT_ESCALATE_BEYOND": ""
  }},
  "state": {{
    "condition": "",
    "ammo": null,
    "charges": null,
    "location": "",
    "separated_from_owner": false
  }},
  "emotional_resonance": ""
}}

Rules:
- Create a locked name that must remain stable in prose.
- Add forbidden aliases for generic or misleading names the prose must not use.
- Make physical signatures specific enough for scene rendering and QA.
- Power ceilings must include what the artifact cannot do.
- State must include scarce resources when relevant: ammo, charges, condition, owner, location.

Character / user need:
{json.dumps(character if isinstance(character, Mapping) else {"character": str(character)}, indent=2, sort_keys=True)}

Beat type:
{beat_type or "unspecified"}

World tone:
{world_tone or "unspecified"}

Power ceiling:
{json.dumps(ceiling, indent=2, sort_keys=True)}

Forbidden solutions:
{json.dumps(_string_list(forbidden_solutions), indent=2, sort_keys=True)}

Active mysteries:
{json.dumps(active_mysteries if isinstance(active_mysteries, Mapping) else _string_list(active_mysteries), indent=2, sort_keys=True)}

Existing artifact registry:
{json.dumps(registry.to_dict(), indent=2, sort_keys=True)}
"""


def build_artifact_state_update_prompt(
    *,
    final_script: str,
    current_registry: ArtifactRegistryState | Mapping[str, Any] | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
) -> str:
    """Build the post-chapter artifact-state extraction prompt."""

    registry = (
        artifact_registry_from_mapping(current_registry)
        if current_registry is not None
        else ArtifactRegistryState(series_id="default-series")
    )
    return f"""You are the Artifact State Updater for a long-form LitRPG story engine.
Extract only artifact changes that were actually established on page.
Do not invent off-page upgrades, repairs, refills, ownership changes, or new powers.

Output ONLY a JSON object with this schema:
{{
  "new_artifacts": {{
    "artifact_id": {{
      "artifact_id": "",
      "locked_name": "",
      "type": "",
      "owner": "",
      "aliases_forbidden": [],
      "physical_signature": {{}},
      "behavioral_rules": [],
      "power_ceiling": {{}},
      "state": {{}},
      "emotional_resonance": ""
    }}
  }},
  "artifact_updates": {{
    "artifact_id": {{
      "owner": "",
      "physical_signature": {{}},
      "behavioral_rules": [],
      "power_ceiling": {{}},
      "state": {{}}
    }}
  }},
  "artifact_state_updates": {{
    "artifact_id": {{
      "ammo": null,
      "charges": null,
      "condition": "",
      "location": "",
      "separated_from_owner": false
    }}
  }},
  "artifact_uses": {{
    "artifact_id": {{"chapter_use": "", "resources_spent": ""}}
  }}
}}

Rules:
- Preserve locked names and forbidden aliases unless a rename is explicitly established as a story event.
- Track every spent charge/ammo/resource if the script states or implies a concrete spend.
- Track condition changes, breakage, repairs, ownership transfers, location changes, and separations.
- Do not refill or repair artifacts unless the final script explicitly does so.
- If nothing durable changed, return {{"new_artifacts": {{}}, "artifact_updates": {{}}, "artifact_state_updates": {{}}, "artifact_uses": {{}}}}.

Current artifact registry:
{json.dumps(registry.to_dict(), indent=2, sort_keys=True)}

Chapter contract:
{json.dumps(dict(chapter_contract or {}), indent=2, sort_keys=True)}

Final script:
{final_script}
"""


def merge_artifact_registry_delta(
    current_world_state: Mapping[str, Any],
    update: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply artifact updater output to the artifact slice of world state."""

    artifact_update = {
        "new_artifacts": _mapping(update.get("new_artifacts")),
        "artifact_updates": _mapping(update.get("artifact_updates")),
        "artifact_state_updates": _mapping(update.get("artifact_state_updates")),
        "artifact_uses": _mapping(update.get("artifact_uses")),
    }
    return merge_world_state_delta(current_world_state, artifact_update)


def _artifact_payload(record: ArtifactRecord) -> dict[str, Any]:
    data = record.to_dict()
    data.pop("artifact_id", None)
    return data


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
