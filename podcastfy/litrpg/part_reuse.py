"""Helpers for reusing ready LitRPG chapter parts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class PartReuseDecision:
    """Deterministic explanation for whether a saved part can be reused."""

    part_id: str
    status: str
    reusable: bool
    reason: str
    source: str = ""
    script: str = ""
    stale_fields: list[str] | None = None

    def to_dict(self, *, include_script: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if payload["stale_fields"] is None:
            payload["stale_fields"] = []
        if not include_script:
            payload.pop("script", None)
        return payload


def locked_part_scripts_from_ready_parts(
    prior_result: Mapping[str, Any] | str | Path,
) -> dict[str, str]:
    """Return scripts for prior parts whose final gate or QA state is ready."""
    return {
        decision.part_id: decision.script
        for decision in explain_reusable_parts(prior_result, include_unknown=True)
        if decision.reusable and decision.script
    }


def list_reusable_parts(
    prior_result: Mapping[str, Any] | str | Path,
    *,
    expected_parts: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    """Return JSON-ready reuse decisions for a prior result."""

    return [
        decision.to_dict(include_script=False)
        for decision in explain_reusable_parts(prior_result, expected_parts=expected_parts)
    ]


def select_reusable_part_scripts(
    prior_result: Mapping[str, Any] | str | Path,
    *,
    expected_parts: Sequence[Any] | None = None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Return reusable scripts plus a JSON-ready reuse report."""

    decisions = explain_reusable_parts(prior_result, expected_parts=expected_parts)
    scripts = {
        decision.part_id: decision.script
        for decision in decisions
        if decision.reusable and decision.script
    }
    return scripts, [decision.to_dict(include_script=False) for decision in decisions]


def explain_reusable_parts(
    prior_result: Mapping[str, Any] | str | Path,
    *,
    expected_parts: Sequence[Any] | None = None,
    include_unknown: bool = False,
) -> list[PartReuseDecision]:
    """Explain reuse eligibility for each expected or previously saved part."""

    result = _load_result(prior_result)
    source = str(prior_result) if not isinstance(prior_result, Mapping) else "inline"
    prior_parts = _parts_by_id(result.get("parts"))
    expected_map = _expected_parts_by_id(expected_parts)
    ids = list(expected_map) if expected_map else list(prior_parts)
    if include_unknown:
        ids = list(dict.fromkeys([*ids, *prior_parts]))
    decisions = []
    for part_id in ids:
        decisions.append(
            explain_part_reuse(
                prior_parts.get(part_id),
                expected_part=expected_map.get(part_id),
                part_id=part_id,
                source=source,
            )
        )
    return decisions


def explain_part_reuse(
    prior_part: Mapping[str, Any] | None,
    *,
    expected_part: Any | None = None,
    part_id: str = "",
    source: str = "",
) -> PartReuseDecision:
    """Return one deterministic part reuse decision."""

    resolved_id = str(part_id or _part_value(prior_part, "part_id") or _part_value(expected_part, "part_id") or "")
    if prior_part is None:
        return PartReuseDecision(
            part_id=resolved_id,
            status="missing",
            reusable=False,
            reason="No saved part exists for this planned part.",
            source=source,
        )
    if not _part_is_ready(prior_part):
        return PartReuseDecision(
            part_id=resolved_id,
            status="blocked",
            reusable=False,
            reason="Saved part is not ready according to final gate or QA state.",
            source=source,
        )
    script = prior_part.get("revised_script") or prior_part.get("script")
    if script is None or not str(script).strip():
        return PartReuseDecision(
            part_id=resolved_id,
            status="blocked",
            reusable=False,
            reason="Saved part has no reusable script text.",
            source=source,
        )
    stale_fields = _stale_contract_fields(prior_part, expected_part)
    if stale_fields:
        return PartReuseDecision(
            part_id=resolved_id,
            status="stale",
            reusable=False,
            reason="Saved part contract no longer matches the planned part.",
            source=source,
            script=str(script),
            stale_fields=stale_fields,
        )
    return PartReuseDecision(
        part_id=resolved_id,
        status="reused",
        reusable=True,
        reason="Saved part is ready and matches the planned part contract.",
        source=source,
        script=str(script),
        stale_fields=[],
    )


def _load_result(prior_result: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    if isinstance(prior_result, Mapping):
        return prior_result

    path = Path(prior_result)
    with path.open("r", encoding="utf-8") as result_file:
        result = json.load(result_file)
    if not isinstance(result, Mapping):
        raise ValueError("Prior chapter result must contain a JSON object")
    return result


def _parts_by_id(parts: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(parts, list):
        return {}
    indexed: dict[str, Mapping[str, Any]] = {}
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        part_id = str(part.get("part_id") or "").strip()
        if part_id:
            indexed[part_id] = part
    return indexed


def _expected_parts_by_id(parts: Sequence[Any] | None) -> dict[str, Any]:
    if not parts:
        return {}
    indexed: dict[str, Any] = {}
    for part in parts:
        part_id = str(_part_value(part, "part_id") or "").strip()
        if part_id:
            indexed[part_id] = part
    return indexed


def _stale_contract_fields(prior_part: Mapping[str, Any], expected_part: Any | None) -> list[str]:
    if expected_part is None:
        return []
    stale = []
    for field_name in ("title", "purpose", "target_minutes"):
        prior_value = _part_value(prior_part, field_name)
        expected_value = _part_value(expected_part, field_name)
        if prior_value not in (None, "") and expected_value not in (None, ""):
            if str(prior_value) != str(expected_value):
                stale.append(field_name)
    prior_roles = _string_list(_part_value(prior_part, "required_roles"))
    expected_roles = _string_list(_part_value(expected_part, "required_roles"))
    if prior_roles and expected_roles and prior_roles != expected_roles:
        stale.append("required_roles")
    prior_beats = _string_list(_part_value(prior_part, "injected_beats"))
    expected_beats = _string_list(_part_value(expected_part, "injected_beats"))
    if prior_beats and expected_beats and prior_beats != expected_beats:
        stale.append("injected_beats")
    return stale


def _part_value(part: Any, key: str) -> Any:
    if part is None:
        return None
    if isinstance(part, Mapping):
        return part.get(key)
    return getattr(part, key, None)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item) for item in value]
    return [str(value)]


def _part_is_ready(part: Mapping[str, Any]) -> bool:
    gate = part.get("gate")
    if isinstance(gate, Mapping):
        final_gate = gate.get("final")
        if isinstance(final_gate, Mapping) and final_gate.get("ready") is True:
            return True
        if gate.get("ready") is True:
            return True

    qa = part.get("qa")
    if isinstance(qa, Mapping):
        final_qa = qa.get("final")
        if isinstance(final_qa, Mapping) and final_qa.get("ready") is True:
            return True
        if qa.get("ready") is True:
            return True
        if str(qa.get("state") or "").lower() == "ready":
            return True
        if str(qa.get("status") or "").lower() == "ready":
            return True

    return False
