"""Helpers for reusing ready LitRPG chapter parts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def locked_part_scripts_from_ready_parts(
    prior_result: Mapping[str, Any] | str | Path,
) -> dict[str, str]:
    """Return scripts for prior parts whose final gate or QA state is ready."""
    result = _load_result(prior_result)
    parts = result.get("parts")
    if not isinstance(parts, list):
        return {}

    locked: dict[str, str] = {}
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        part_id = part.get("part_id")
        if not part_id or not _part_is_ready(part):
            continue
        script = part.get("revised_script") or part.get("script")
        if script is None:
            continue
        locked[str(part_id)] = str(script)
    return locked


def _load_result(prior_result: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    if isinstance(prior_result, Mapping):
        return prior_result

    path = Path(prior_result)
    with path.open("r", encoding="utf-8") as result_file:
        result = json.load(result_file)
    if not isinstance(result, Mapping):
        raise ValueError("Prior chapter result must contain a JSON object")
    return result


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
