"""Setpiece contracts for memorable chapter event shapes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class SetpieceContract:
    toy: str
    rule: str
    pressure: str
    exploit: str
    goes_wrong: str
    remembered_image: str
    floor_grounding: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_FIELDS = tuple(SetpieceContract.__dataclass_fields__)


def build_setpiece_contract(
    *,
    chapter_contract: Mapping[str, Any] | None = None,
    floor_identity: Mapping[str, Any] | None = None,
    encounter_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    chapter = dict(chapter_contract or {})
    floor = dict(floor_identity or {})
    encounter = dict(encounter_contract or {})
    contract = SetpieceContract(
        toy=str(chapter.get("setpiece_toy") or floor.get("traversal_constraint") or "a floor-specific rule object"),
        rule=str(chapter.get("setpiece_rule") or (encounter.get("rules") or ["one visible rule"])[0]),
        pressure=str(chapter.get("setpiece_pressure") or encounter.get("fail_condition") or "the rule tightens under time pressure"),
        exploit=str(chapter.get("setpiece_exploit") or (encounter.get("exploit_surface") or [floor.get("exploit_pattern") or "use the rule literally"])[0]),
        goes_wrong=str(chapter.get("setpiece_goes_wrong") or "the exploit works but changes the tactical problem"),
        remembered_image=str(chapter.get("remembered_image") or f"{floor.get('name') or 'the floor'} turns a practical action into a visible absurd consequence"),
        floor_grounding=str(floor.get("name") or chapter.get("setting") or "current floor"),
    )
    return contract.to_dict()


def validate_setpiece_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if not str(contract.get(field) or "").strip()]
    return {"passed": not missing, "missing": missing}
