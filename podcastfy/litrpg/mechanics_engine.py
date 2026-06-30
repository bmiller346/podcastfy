"""Inspectable encounter contracts for mechanically bounded chapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class EncounterContract:
    objective: str
    rules: list[str] = field(default_factory=list)
    fail_condition: str = ""
    exploit_surface: list[str] = field(default_factory=list)
    cost: str = ""
    reward_possibility: str = ""
    system_restriction: str = ""
    resource_pressure: str = ""
    environmental_affordance: str = ""
    artifact_interaction: str = ""
    comedy_angle: str = ""
    character_state_refs: list[str] = field(default_factory=list)
    artifact_state_refs: list[str] = field(default_factory=list)
    threat: dict[str, Any] = field(default_factory=dict)
    loot_needs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_FIELDS = (
    "objective",
    "rules",
    "fail_condition",
    "exploit_surface",
    "cost",
    "reward_possibility",
    "system_restriction",
    "resource_pressure",
    "environmental_affordance",
    "artifact_interaction",
    "comedy_angle",
)


def build_encounter_contract(
    *,
    chapter_contract: Mapping[str, Any] | None = None,
    character_state: Mapping[str, Any] | None = None,
    artifact_state: Mapping[str, Any] | None = None,
    threat_contract: Mapping[str, Any] | None = None,
    floor_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    chapter = dict(chapter_contract or {})
    floor = dict(floor_identity or {})
    threat = dict(threat_contract or {})
    characters = dict(character_state or {})
    artifacts = dict(artifact_state or {})
    objective = str(
        chapter.get("encounter_objective")
        or chapter.get("objective")
        or chapter.get("premise")
        or "survive the floor rule without earning a free upgrade"
    )
    contract = EncounterContract(
        objective=objective,
        rules=_string_list(chapter.get("encounter_rules")) or _string_list(floor.get("social_rules"))[:2] or ["the hazard obeys its stated rule"],
        fail_condition=str(chapter.get("fail_condition") or "failure costs position, resources, or information; it does not end the series"),
        exploit_surface=_string_list(chapter.get("exploit_surface")) or _string_list(threat.get("exploit_path")) or _string_list(floor.get("exploit_pattern")),
        cost=str(chapter.get("cost") or "spend time, expose a vulnerability, damage gear, or worsen pressure"),
        reward_possibility=str(chapter.get("reward_possibility") or "may earn information, access, or a loot need; no artifact is created here"),
        system_restriction=str(chapter.get("system_restriction") or "no unearned power, no mystery reveal, no direct artifact creation"),
        resource_pressure=str(chapter.get("resource_pressure") or "track charges, injury, time, position, or social leverage before reward"),
        environmental_affordance=str(chapter.get("environmental_affordance") or floor.get("traversal_constraint") or threat.get("weakness") or "the environment offers one legible affordance with a cost"),
        artifact_interaction=str(chapter.get("artifact_interaction") or _artifact_interaction(artifacts)),
        comedy_angle=str(chapter.get("comedy_angle") or threat.get("comedic_angle") or floor.get("system_joke_style") or "the rule is absurd but tactically real"),
        character_state_refs=_character_refs(characters),
        artifact_state_refs=_artifact_refs(artifacts),
        threat=threat,
        loot_needs=_string_list(chapter.get("loot_needs")),
    )
    return contract.to_dict()


def validate_encounter_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if contract.get(field) in (None, "", [], {})]
    warnings = []
    reward = str(contract.get("reward_possibility") or "").lower()
    if any(token in reward for token in ("creates artifact", "new artifact", "legendary weapon")):
        warnings.append("reward_possibility appears to create artifacts directly; route through Artifact Forge")
    return {"passed": not missing and not warnings, "missing": missing, "warnings": warnings}


def format_encounter_context(contract: Mapping[str, Any]) -> str:
    data = dict(contract or {})
    lines = ["[mechanics_engine] encounter contract"]
    for key in REQUIRED_FIELDS:
        value = data.get(key)
        text = "; ".join(_string_list(value)) if isinstance(value, (list, tuple, set)) else str(value or "")
        if text:
            lines.append(f"- {key}: {text}")
    if data.get("threat"):
        threat = data["threat"]
        if isinstance(threat, Mapping):
            lines.append(f"- threat: {threat.get('name')}; weakness={threat.get('weakness')}; exploit={threat.get('exploit_path')}")
    return "\n".join(lines)


def _artifact_interaction(artifacts: Mapping[str, Any]) -> str:
    refs = _artifact_refs(artifacts)
    if not refs:
        return "no artifact may solve the encounter without an earned setup"
    return f"active artifact constraint: {refs[0]}"


def _character_refs(characters: Mapping[str, Any]) -> list[str]:
    refs = []
    for key, value in characters.items():
        if isinstance(value, Mapping):
            bits = _string_list(value.get("injuries")) + _string_list(value.get("current_coping_mode")) + _string_list(value.get("skills"))
            if bits:
                refs.append(f"{key}: {'; '.join(bits[:3])}")
    return refs[:6]


def _artifact_refs(artifacts: Mapping[str, Any]) -> list[str]:
    refs = []
    for key, value in artifacts.items():
        if isinstance(value, Mapping):
            state = value.get("state") if isinstance(value.get("state"), Mapping) else {}
            refs.append(f"{key}: name={value.get('locked_name') or key}; state={dict(state)}")
    return refs[:6]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(item) for item in value.values() if str(item or "").strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value).strip() else []
