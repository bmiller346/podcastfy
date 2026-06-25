"""Structured QA helpers for LitRPG chapter review artifacts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


VERDICTS = {"pass", "revise", "block"}
TONAL_SCORE_KEYS = ("stakes_seriousness", "absurdity_pressure")
SHOWMANSHIP_SCORE_KEYS = (
    "crowd_engagement",
    "brutality",
    "creativity",
    "humiliation",
    "meme_potential",
    "sponsor_appeal",
)
DESCRIPTION_SCORE_KEYS = ("score", "description_score")


def parse_part_qa_artifacts(
    *,
    director_tags: str = "",
    mechanics_audit: str = "",
    description_audit: str = "",
    tonal_audit: str = "",
    showmanship_audit: str = "",
) -> dict[str, Any]:
    """Parse raw review artifacts into best-effort structured QA data."""
    director = _parse_director(director_tags)
    mechanics = _parse_audit(mechanics_audit, score_keys=())
    description = _parse_audit(description_audit, score_keys=DESCRIPTION_SCORE_KEYS)
    tonal = _parse_audit(tonal_audit, score_keys=TONAL_SCORE_KEYS)
    showmanship = _parse_audit(showmanship_audit, score_keys=SHOWMANSHIP_SCORE_KEYS)
    return {
        "director": director,
        "mechanics": mechanics,
        "description": description,
        "tonal": tonal,
        "showmanship": showmanship,
    }


def build_chapter_qa(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build top-level chapter QA from parsed audits and deterministic gates."""
    summaries = []
    blocking_issues: list[str] = []
    revision_targets: list[dict[str, Any]] = []

    for part in parts:
        part_id = str(part.get("part_id") or "")
        title = str(part.get("title") or part_id)
        gate = _mapping(part.get("gate"))
        final_gate = _mapping(gate.get("final"))
        parsed = parse_part_qa_artifacts(
            director_tags=str(part.get("director_tags") or ""),
            mechanics_audit=str(part.get("mechanics_audit") or ""),
            description_audit=str(part.get("description_audit") or ""),
            tonal_audit=str(part.get("tonal_audit") or ""),
            showmanship_audit=str(part.get("showmanship_audit") or ""),
        )
        verdicts = {
            name: parsed[name].get("verdict")
            for name in ("mechanics", "description", "tonal", "showmanship")
            if parsed[name].get("verdict")
        }
        is_blocked = any(verdict == "block" for verdict in verdicts.values())
        gate_ready = bool(final_gate.get("ready", True))
        part_ready = gate_ready and not is_blocked
        part_blocking = _part_blocking_issues(
            part_id=part_id,
            parsed=parsed,
            final_gate=final_gate,
        )
        blocking_issues.extend(part_blocking)
        targets = _part_revision_targets(part_id=part_id, parsed=parsed)
        revision_targets.extend(targets)
        summaries.append(
            {
                "part_id": part_id,
                "title": title,
                "ready": part_ready,
                "gate_ready": gate_ready,
                "verdicts": verdicts,
                "scores": {
                    "tonal": parsed["tonal"].get("scores", {}),
                    "description": parsed["description"].get("scores", {}),
                    "showmanship": parsed["showmanship"].get("scores", {}),
                },
                "blocking_issues": part_blocking,
                "revision_targets": targets,
                "audits": parsed,
            }
        )

    return {
        "ready": all(bool(summary["ready"]) for summary in summaries),
        "parts": summaries,
        "blocking_issues": blocking_issues,
        "revision_targets": revision_targets,
    }


def _parse_director(raw: str) -> dict[str, Any]:
    data = _load_json_object(raw)
    if isinstance(data, Mapping):
        return {
            "summary": str(data.get("summary") or ""),
            "cues": _list_value(data.get("cues")),
            "render_notes": _list_or_text(data.get("render_notes")),
            "raw": raw,
        }
    return {
        "summary": _first_nonempty_line(raw),
        "cues": [],
        "render_notes": [],
        "raw": raw,
    }


def _parse_audit(raw: str, *, score_keys: Sequence[str]) -> dict[str, Any]:
    data = _load_json_object(raw)
    verdict = _extract_verdict(raw, data)
    scores = _extract_scores(raw, data, score_keys)
    blocking_issues = _extract_named_list(raw, data, "blocking_issues")
    fixes = _extract_named_list(raw, data, "fixes")
    if verdict == "block" and not blocking_issues:
        blocking_issues = [_first_nonempty_line(raw) or "Audit returned block verdict"]
    return {
        "verdict": verdict,
        "scores": scores,
        "blocking_issues": blocking_issues,
        "fixes": fixes,
        "raw": raw,
    }


def _load_json_object(raw: str) -> Mapping[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, Mapping) else None


def _extract_verdict(raw: str, data: Mapping[str, Any] | None) -> str | None:
    if isinstance(data, Mapping):
        value = data.get("verdict")
        if isinstance(value, str) and value.strip().lower() in VERDICTS:
            return value.strip().lower()
    match = re.search(r"\bverdict\s*[:=\-]\s*(pass|revise|block)\b", raw, flags=re.I)
    if match:
        return match.group(1).lower()
    match = re.search(r"\b(pass|revise|block)\b", raw, flags=re.I)
    if match:
        return match.group(1).lower()
    return None


def _extract_scores(
    raw: str,
    data: Mapping[str, Any] | None,
    score_keys: Sequence[str],
) -> dict[str, int | float]:
    scores: dict[str, int | float] = {}
    nested = data.get("scores") if isinstance(data, Mapping) else None
    sources = [value for value in (nested, data) if isinstance(value, Mapping)]
    for key in score_keys:
        value = _first_score_value(key, sources)
        if value is None:
            value = _extract_text_score(raw, key)
        if value is not None:
            scores[key] = value
    return scores


def _first_score_value(
    key: str,
    sources: Sequence[Mapping[str, Any]],
) -> int | float | None:
    labels = {_normalize_label(key), key}
    for source in sources:
        for source_key, source_value in source.items():
            if _normalize_label(str(source_key)) in labels:
                return _number_or_none(source_value)
    return None


def _extract_text_score(raw: str, key: str) -> int | float | None:
    label = re.escape(key).replace("_", r"[\s_\-]+")
    pattern = rf"\b{label}\b\s*(?:score|rating)?\s*[:=\-]?\s*(\d+(?:\.\d+)?)"
    match = re.search(pattern, raw, flags=re.I)
    if match:
        return _number_or_none(match.group(1))
    words = re.escape(key.replace("_", " "))
    pattern = rf"\b{words}\b\s*(?:score|rating)?\s*[:=\-]?\s*(\d+(?:\.\d+)?)"
    match = re.search(pattern, raw, flags=re.I)
    if match:
        return _number_or_none(match.group(1))
    return None


def _extract_named_list(
    raw: str,
    data: Mapping[str, Any] | None,
    key: str,
) -> list[str]:
    if isinstance(data, Mapping):
        if key in data:
            return _list_or_text(data.get(key))
        for data_key, value in data.items():
            if _normalize_label(str(data_key)) == _normalize_label(key):
                return _list_or_text(value)

    label = re.escape(key).replace("_", r"[\s_\-]+")
    match = re.search(
        rf"\b{label}\b\s*[:=\-]\s*(.+?)(?=\n\s*[A-Za-z_ -]+\s*[:=\-]|\Z)",
        raw,
        flags=re.I | re.DOTALL,
    )
    if not match:
        return []
    return _split_list_text(match.group(1))


def _part_blocking_issues(
    *,
    part_id: str,
    parsed: Mapping[str, Any],
    final_gate: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = []
    for issue in _list_or_text(final_gate.get("issues")):
        issues.append(f"{part_id}: {issue}")
    for audit_name in ("mechanics", "description", "tonal", "showmanship"):
        audit = _mapping(parsed.get(audit_name))
        if audit.get("verdict") != "block":
            continue
        audit_issues = _list_or_text(audit.get("blocking_issues"))
        if not audit_issues:
            audit_issues = [f"{audit_name} audit returned block verdict"]
        for issue in audit_issues:
            issues.append(f"{part_id}: {audit_name}: {issue}")
    return issues


def _part_revision_targets(
    *,
    part_id: str,
    parsed: Mapping[str, Any],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for audit_name in ("mechanics", "description", "tonal", "showmanship"):
        audit = _mapping(parsed.get(audit_name))
        verdict = audit.get("verdict")
        fixes = _list_or_text(audit.get("fixes"))
        if verdict in {"revise", "block"} or fixes:
            targets.append(
                {
                    "part_id": part_id,
                    "audit": audit_name,
                    "verdict": verdict,
                    "fixes": fixes,
                }
            )
    return targets


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _list_or_text(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return _split_list_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _split_list_text(value: str) -> list[str]:
    items = []
    for line in value.strip().splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned:
            items.append(cleaned)
    if len(items) == 1 and ";" in items[0]:
        items = [item.strip() for item in items[0].split(";") if item.strip()]
    return items


def _first_nonempty_line(raw: str) -> str:
    for line in raw.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _number_or_none(value: Any) -> int | float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
