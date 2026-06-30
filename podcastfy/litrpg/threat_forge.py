"""Threat contracts consumed by encounter planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class ThreatContract:
    name: str
    sensory_signature: str
    behavior_rule: str
    punishes: str
    weakness: str
    exploit_path: str
    ecology_reason: str
    comedic_angle: str
    escalation_ceiling: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_FIELDS = tuple(ThreatContract.__dataclass_fields__)


def forge_threat_contract(
    *,
    floor_identity: Mapping[str, Any] | None = None,
    threat_seed: Mapping[str, Any] | str | None = None,
    chapter_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    floor = dict(floor_identity or {})
    contract = dict(chapter_contract or {})
    seed = {"name": str(threat_seed)} if isinstance(threat_seed, str) else dict(threat_seed or {})
    common = _string_list(floor.get("common_threats"))
    name = str(seed.get("name") or seed.get("entity") or (common[0] if common else "Rule-Bound Hazard"))
    identity_name = str(floor.get("name") or contract.get("setting") or "this floor")
    threat = ThreatContract(
        name=name,
        sensory_signature=str(seed.get("sensory_signature") or seed.get("signature") or f"{name} announces itself through one specific sensory tell"),
        behavior_rule=str(seed.get("behavior_rule") or seed.get("rule") or f"{name} follows one legible rule before it harms anyone"),
        punishes=str(seed.get("punishes") or seed.get("what_it_punishes") or "careless repetition of the floor's main mistake"),
        weakness=str(seed.get("weakness") or "a constraint already visible in the scene"),
        exploit_path=str(seed.get("exploit_path") or floor.get("exploit_pattern") or "turn the rule against itself after paying a cost"),
        ecology_reason=str(seed.get("ecology_reason") or f"belongs to {identity_name}, not a generic wandering monster"),
        comedic_angle=str(seed.get("comedic_angle") or floor.get("system_joke_style") or "absurd rule enforced with a straight face"),
        escalation_ceiling=str(seed.get("escalation_ceiling") or "may injure, separate, or tax characters; may not solve long-term mysteries"),
    )
    return threat.to_dict()


def validate_threat_contract(threat: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if not str(threat.get(field) or "").strip()]
    generic = []
    if "monster attacks" in str(threat.get("behavior_rule") or "").lower():
        generic.append("behavior_rule")
    return {"passed": not missing and not generic, "missing": missing, "generic_fields": generic}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value).strip() else []
