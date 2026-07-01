"""Text-only multi-chapter dry-run harness for state drift detection."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from podcastfy.litrpg.conspiracy_engine import load_conspiracy_engine
from podcastfy.litrpg.continuity import load_emotional_arcs
from podcastfy.litrpg.foreshadowing import load_foreshadow_ledger
from podcastfy.litrpg.promise_ledger import build_promise_report
from podcastfy.litrpg.world_state import load_world_state, validate_world_state_consistency


ChapterRunner = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def run_simulation_dry_run(
    *,
    storage_dir: str | Path,
    series_id: str,
    chapter_tasks: Sequence[Mapping[str, Any]],
    chapter_runner: ChapterRunner,
    commit: bool = False,
    max_world_state_bytes: int = 120_000,
) -> dict[str, Any]:
    """Run N chapters text-only and report state drift.

    Non-commit mode copies the storage tree to a temporary directory and rewrites
    task storage paths to that copy when a task contains ``storage_dir``.
    """

    source_storage = Path(storage_dir)
    if commit:
        run_storage = source_storage
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="litrpg-sim-")
        run_storage = Path(cleanup.name) / "storage"
        if source_storage.exists():
            shutil.copytree(source_storage, run_storage)
        else:
            run_storage.mkdir(parents=True)

    try:
        before = _snapshot(run_storage, series_id)
        reports = []
        scene_types = []
        previous = before
        for index, raw_task in enumerate(chapter_tasks, 1):
            task = _simulation_task(raw_task, run_storage, series_id)
            scene_types.append(_scene_type(task))
            runner_error = None
            try:
                result = dict(chapter_runner(task))
            except Exception as exc:  # pragma: no cover - covered through integration behavior.
                runner_error = {
                    "type": "chapter_generation_exception",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
                result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            current = _snapshot(run_storage, series_id)
            drift = detect_state_drift(
                previous,
                current,
                result=result,
                scene_types=scene_types,
                book_number=int(task.get("book_number") or task.get("book") or 1),
                chapter_number=int(task.get("chapter_number") or task.get("chapter") or index),
                max_world_state_bytes=max_world_state_bytes,
            )
            if runner_error:
                drift["issues"].append(runner_error)
                drift["passed"] = False
            reports.append(
                {
                    "chapter_index": index,
                    "chapter_number": int(task.get("chapter_number") or task.get("chapter") or index),
                    "scene_type": scene_types[-1],
                    "result_status": result.get("status") or result.get("quarantine", {}).get("status") if isinstance(result.get("quarantine"), Mapping) else result.get("status"),
                    "drift": drift,
                }
            )
            if runner_error:
                break
            previous = current
        summary = {
            "passed": not any(item["drift"]["issues"] for item in reports),
            "series_id": series_id,
            "commit": bool(commit),
            "chapters_run": len(chapter_tasks),
            "chapters": reports,
            "report": _flatten_reports(reports),
        }
        return summary
    finally:
        if cleanup is not None:
            cleanup.cleanup()


def detect_state_drift(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    result: Mapping[str, Any] | None = None,
    scene_types: Sequence[str] = (),
    book_number: int = 1,
    chapter_number: int = 1,
    max_world_state_bytes: int = 120_000,
) -> dict[str, Any]:
    result = dict(result or {})
    issues = []
    warnings = []
    issues.extend(_mystery_leakage(before, after))
    issues.extend(_artifact_resource_resets(before, after))
    issues.extend(_arc_resets(before, after))
    world_validation = validate_world_state_consistency(after.get("world_state") or {})
    for violation in world_validation.get("violations", []):
        if isinstance(violation, Mapping) and violation.get("type") == "duplicate_locked_name":
            issues.append({"type": "duplicate_locked_name", **dict(violation)})
    world_size = len(json.dumps(after.get("world_state") or {}, sort_keys=True))
    if world_size > max_world_state_bytes:
        warnings.append({"type": "world_state_bloat", "bytes": world_size, "limit": max_world_state_bytes})
    repeated = _repeated_scene_types(scene_types)
    if repeated:
        issues.append(repeated)
    issues.extend(_overdue_promises(after, book_number=book_number, chapter_number=chapter_number))
    issues.extend(_scene_rendering_failures(result))
    if before == after and not _has_state_update(result):
        issues.append({"type": "missing_state_updates", "detail": "no tracked state changed and result carried no updater payload"})
    return {"passed": not issues, "issues": issues, "warnings": warnings}


def write_simulation_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(report), ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _snapshot(storage_dir: Path, series_id: str) -> dict[str, Any]:
    return {
        "world_state": load_world_state(storage_dir, series_id),
        "emotional_arcs": _safe_arcs(storage_dir, series_id),
        "conspiracy_engine": load_conspiracy_engine(storage_dir, series_id),
        "foreshadow_ledger": _safe_foreshadow(storage_dir, series_id),
    }


def _safe_arcs(storage_dir: Path, series_id: str) -> dict[str, Any]:
    from dataclasses import asdict

    try:
        return asdict(load_emotional_arcs(storage_dir, series_id))
    except Exception:
        return {"series_id": series_id, "characters": {}}


def _safe_foreshadow(storage_dir: Path, series_id: str) -> dict[str, Any]:
    from dataclasses import asdict

    try:
        return asdict(load_foreshadow_ledger(storage_dir, series_id))
    except Exception:
        return {"series_id": series_id, "planted": [], "ready_to_pay": []}


def _simulation_task(task: Mapping[str, Any], storage_dir: Path, series_id: str) -> dict[str, Any]:
    payload = copy.deepcopy(dict(task))
    payload["series_id"] = str(payload.get("series_id") or series_id)
    payload["render_audio"] = False
    payload["storage_dir"] = str(storage_dir)
    return payload


def _scene_type(task: Mapping[str, Any]) -> str:
    contract = task.get("chapter_contract") if isinstance(task.get("chapter_contract"), Mapping) else {}
    return str(task.get("scene_type") or contract.get("scene_type") or contract.get("beat_type") or contract.get("phase") or "unspecified")


def _mystery_leakage(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues = []
    before_mysteries = ((before.get("world_state") or {}).get("active_mysteries") or {})
    after_mysteries = ((after.get("world_state") or {}).get("active_mysteries") or {})
    if isinstance(before_mysteries, Mapping) and isinstance(after_mysteries, Mapping):
        for key, value in before_mysteries.items():
            if not isinstance(value, Mapping):
                continue
            old = str(value.get("status") or "").upper()
            new = str((after_mysteries.get(key) or {}).get("status") if isinstance(after_mysteries.get(key), Mapping) else "").upper()
            if old in {"DO_NOT_SPEND", "LOCKED", "HINT_ONLY"} and new in {"SPENT", "REVEALED", "RESOLVED"}:
                issues.append({"type": "mystery_leakage", "mystery_id": str(key), "from": old, "to": new})
    before_reader = ((before.get("conspiracy_engine") or {}).get("reader_position") or {}).get("must_not_know_yet") or []
    after_reader = ((after.get("conspiracy_engine") or {}).get("reader_position") or {}).get("must_not_know_yet") or []
    removed = sorted(set(map(str, before_reader)) - set(map(str, after_reader)))
    if removed:
        issues.append({"type": "mystery_leakage", "removed_must_not_know_yet": removed})
    return issues


def _artifact_resource_resets(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues = []
    before_artifacts = ((before.get("world_state") or {}).get("artifacts") or {})
    after_artifacts = ((after.get("world_state") or {}).get("artifacts") or {})
    if not isinstance(before_artifacts, Mapping) or not isinstance(after_artifacts, Mapping):
        return issues
    for artifact_id, artifact in before_artifacts.items():
        if not isinstance(artifact, Mapping) or not isinstance(after_artifacts.get(artifact_id), Mapping):
            continue
        before_state = artifact.get("state") if isinstance(artifact.get("state"), Mapping) else {}
        after_state = after_artifacts[artifact_id].get("state") if isinstance(after_artifacts[artifact_id].get("state"), Mapping) else {}
        for key in ("ammo", "charges"):
            old = _optional_int(before_state.get(key))
            new = _optional_int(after_state.get(key))
            if old is not None and new is not None and new > old:
                issues.append({"type": "artifact_resource_reset", "artifact_id": str(artifact_id), "resource": key, "from": old, "to": new})
    return issues


def _arc_resets(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues = []
    before_chars = ((before.get("emotional_arcs") or {}).get("characters") or {})
    after_chars = ((after.get("emotional_arcs") or {}).get("characters") or {})
    if not isinstance(before_chars, Mapping) or not isinstance(after_chars, Mapping):
        return issues
    for character, arc in before_chars.items():
        if not isinstance(arc, Mapping) or not isinstance(after_chars.get(character), Mapping):
            continue
        after_arc = after_chars[character]
        for key in ("wound", "current_coping_mode"):
            old = str(arc.get(key) or "").strip()
            new = str(after_arc.get(key) or "").strip()
            if old and not new:
                issues.append({"type": "wound_coping_mode_reset", "character": str(character), "field": key, "from": old, "to": new})
    return issues


def _repeated_scene_types(scene_types: Sequence[str]) -> dict[str, Any] | None:
    if len(scene_types) < 3:
        return None
    tail = [str(item).casefold() for item in scene_types[-3:]]
    if tail[0] and len(set(tail)) == 1:
        return {"type": "repeated_scene_types", "scene_type": scene_types[-1], "count": 3}
    return None


def _overdue_promises(snapshot: Mapping[str, Any], *, book_number: int, chapter_number: int) -> list[dict[str, Any]]:
    ledger = snapshot.get("foreshadow_ledger")
    if not isinstance(ledger, Mapping):
        return []
    report = build_promise_report(ledger, book=book_number, chapter=chapter_number)
    issues = []
    for item in report.get("overdue") or []:
        if isinstance(item, Mapping):
            issues.append(
                {
                    "type": "overdue_promise",
                    "promise_type": item.get("type"),
                    "reader_facing_wording": item.get("reader_facing_wording"),
                    "intended_payoff_window": item.get("intended_payoff_window"),
                }
            )
    return issues


def _scene_rendering_failures(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    gate = result.get("scene_rendering_gate") if isinstance(result.get("scene_rendering_gate"), Mapping) else {}
    audit = gate.get("audit") if isinstance(gate.get("audit"), Mapping) else {}
    violations = audit.get("violations") if isinstance(audit.get("violations"), list) else []
    if not violations:
        return []
    return [
        {
            "type": "scene_rendering_failure",
            "status": gate.get("status"),
            "violations": [str(item) for item in violations],
        }
    ]


def _has_state_update(result: Mapping[str, Any]) -> bool:
    return any(str(result.get(key) or "").strip() for key in ("world_state_update", "arc_state_update")) or bool(result.get("state_delta"))


def _flatten_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    issues = []
    warnings = []
    for report in reports:
        drift = report.get("drift") if isinstance(report.get("drift"), Mapping) else {}
        for issue in drift.get("issues") or []:
            if isinstance(issue, Mapping):
                issues.append({"chapter_index": report.get("chapter_index"), **dict(issue)})
        for warning in drift.get("warnings") or []:
            if isinstance(warning, Mapping):
                warnings.append({"chapter_index": report.get("chapter_index"), **dict(warning)})
    return {"issues": issues, "warnings": warnings}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
