"""Gate scene-rendering audits into pass, bounded rewrite, or quarantine."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


REVISION_TYPES = {
    "missing_spatial_anchor",
    "ignored_threat_geometry",
    "forbidden_alias_use",
    "artifact_locked_name_failure",
    "resource_state_reset",
    "missing_required_sensory_priority",
}


def parse_scene_rendering_audit(raw: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        try:
            payload = json.loads(str(raw or "{}"))
        except json.JSONDecodeError:
            payload = {"verdict": "block", "violations": ["scene rendering audit did not return valid JSON"]}
    violations = _string_list(payload.get("violations"))
    verdict = str(payload.get("verdict") or "").lower()
    if verdict not in {"pass", "revise", "block"}:
        verdict = _verdict_from_violations(violations)
    return {
        "verdict": verdict,
        "violations": violations,
        "warnings": _string_list(payload.get("warnings")),
        "raw": raw if isinstance(raw, str) else json.dumps(payload, sort_keys=True),
    }


def apply_scene_rendering_audit_gate(
    *,
    audit: str | Mapping[str, Any],
    script: str,
    llm: Any | None = None,
    scene_brief: Mapping[str, Any] | None = None,
    scarcity_locks: Mapping[str, Any] | None = None,
    max_rewrite_attempts: int = 1,
) -> dict[str, Any]:
    parsed = parse_scene_rendering_audit(audit)
    if parsed["verdict"] == "pass":
        return {"status": "passed", "script": script, "audit": parsed, "rewrite_attempts": []}
    if parsed["verdict"] == "block" or llm is None or max_rewrite_attempts <= 0:
        return _blocked(script=script, parsed=parsed)

    attempts = []
    current = script
    for attempt in range(1, max_rewrite_attempts + 1):
        prompt = build_scene_rendering_rewrite_prompt(
            script=current,
            audit=parsed,
            scene_brief=scene_brief,
            scarcity_locks=scarcity_locks,
        )
        rewritten = str(llm.generate(prompt=prompt, stage="scene_rendering_rewrite"))
        attempts.append({"attempt": attempt, "prompt": prompt, "script": rewritten})
        current = rewritten
        break
    return {"status": "revised", "script": current, "audit": parsed, "rewrite_attempts": attempts}


def build_scene_rendering_rewrite_prompt(
    *,
    script: str,
    audit: Mapping[str, Any],
    scene_brief: Mapping[str, Any] | None = None,
    scarcity_locks: Mapping[str, Any] | None = None,
) -> str:
    return (
        "Rewrite only the scene-rendering failures listed below.\n"
        "Preserve plot, dialogue intent, established scarcity locks, and mystery locks.\n"
        "Do not rewrite for style preference alone.\n\n"
        f"Violations:\n{_bullet_lines(_string_list(audit.get('violations')))}\n\n"
        f"Scene brief:\n{json.dumps(dict(scene_brief or {}), ensure_ascii=True, indent=2, sort_keys=True)}\n\n"
        f"Scarcity locks:\n{json.dumps(dict(scarcity_locks or {}), ensure_ascii=True, indent=2, sort_keys=True)}\n\n"
        f"Script:\n{script}\n\nReturn only the revised script."
    )


def _blocked(*, script: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "quarantined",
        "script": script,
        "audit": dict(parsed),
        "rewrite_attempts": [],
        "quarantine": {
            "status": "quarantined",
            "reason": "scene_rendering_audit_failed",
            "violation_notes": list(parsed.get("violations") or []),
        },
    }


def _verdict_from_violations(violations: Sequence[str]) -> str:
    text = " ".join(violations).lower()
    if not text:
        return "pass"
    if any(token in text for token in ("truth_document", "scarcity reveal", "locked mystery revealed")):
        return "block"
    if any(token in text for token in REVISION_TYPES):
        return "revise"
    return "revise"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value).strip() else []


def _bullet_lines(values: Sequence[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- None"
