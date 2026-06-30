"""Deterministic HANDOFF.md generation from persisted LitRPG state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from podcastfy.litrpg.effect_log import effect_log_path, read_effect_log
from podcastfy.litrpg.render_feedback import collect_render_feedback_records
from podcastfy.litrpg.series_architect import book_dir, series_dir


HANDOFF_FILENAME = "HANDOFF.md"


def generate_book_handoff(storage_dir: str | Path, series_id: str, book_number: int) -> Path:
    """Generate a deterministic book handoff markdown file."""

    storage = Path(storage_dir)
    root = series_dir(storage, series_id)
    book_root = book_dir(storage, series_id, book_number)
    book_root.mkdir(parents=True, exist_ok=True)
    series_plan = _read_json_object(root / "series_plan.json")
    book_plan = _read_json_object(book_root / "book_plan.json")
    if not book_plan:
        book_plan = _book_plan_from_arc(root / "series_arc.json", book_number)
    chapter_outline = _read_json_list(book_root / "chapter_outline.json")
    chapter_results = _chapter_results(book_root)
    quarantine_records = _quarantine_records(book_root)
    effects = read_effect_log(effect_log_path(storage, series_id))
    render_feedback = _render_feedback_records(chapter_results, effects)

    lines = [
        f"# HANDOFF: {series_plan.get('series_title') or series_id} Book {int(book_number)}",
        "",
        "## Book status",
        f"- Series: {series_plan.get('series_title') or series_id}",
        f"- Book role: {book_plan.get('role') or 'Unknown'}",
        f"- Power ceiling: {book_plan.get('power_ceiling') or 'Unknown'}",
        f"- Chapter outline entries: {len(chapter_outline)}",
        f"- Chapter result files: {len(chapter_results)}",
        "",
        "## Approved chapters",
        *_approved_chapter_lines(chapter_results),
        "",
        "## Quarantined/blocked chapters",
        *_quarantine_lines(quarantine_records),
        "",
        "## Open hooks",
        *_open_hook_lines(chapter_results),
        "",
        "## Locked mysteries",
        *_locked_mystery_lines(series_plan, book_plan, chapter_results),
        "",
        "## Spent/revealed mysteries",
        *_spent_mystery_lines(chapter_results, quarantine_records),
        "",
        "## Character/state changes",
        *_state_change_lines(chapter_results),
        "",
        "## Pending human decisions",
        *_pending_decision_lines(quarantine_records),
        "",
        "## Render feedback",
        *_render_feedback_lines(render_feedback),
        "",
        "## Effect log",
        *_effect_lines(effects),
        "",
        "## Recommended next action",
        _recommended_next_action(chapter_results, quarantine_records, chapter_outline, render_feedback),
        "",
    ]
    path = book_root / HANDOFF_FILENAME
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _approved_chapter_lines(results: list[Mapping[str, Any]]) -> list[str]:
    lines = []
    for result in results:
        quarantine = result.get("quarantine") if isinstance(result.get("quarantine"), Mapping) else {}
        render = result.get("render") if isinstance(result.get("render"), Mapping) else {}
        chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
        if quarantine.get("status") in {"quarantined", "blocked"} or render.get("ready") is False:
            continue
        number = chapter.get("number") or "?"
        lines.append(f"- Chapter {number}: {chapter.get('title') or 'Untitled'}")
    return lines or ["- None"]


def _quarantine_lines(records: list[Mapping[str, Any]]) -> list[str]:
    if not records:
        return ["- None"]
    return [
        (
            f"- Chapter {record.get('chapter_number')}: {record.get('status')} "
            f"attempt {record.get('attempt')} - "
            f"{'; '.join(str(item) for item in record.get('violation_notes') or []) or record.get('reason')}"
        )
        for record in records
    ]


def _open_hook_lines(results: list[Mapping[str, Any]]) -> list[str]:
    lines = []
    for result in results:
        hook_review = str(result.get("hook_review") or "")
        chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
        if hook_review:
            lines.append(f"- Chapter {chapter.get('number') or '?'} hook review: {_compact(hook_review)}")
        quarantine = result.get("quarantine") if isinstance(result.get("quarantine"), Mapping) else {}
        instruction = quarantine.get("rewrite_instruction") if isinstance(quarantine, Mapping) else ""
        if instruction:
            lines.append(f"- Chapter {chapter.get('number') or '?'} rewrite opener: {_compact(str(instruction))}")
    return lines or ["- None"]


def _locked_mystery_lines(
    series_plan: Mapping[str, Any],
    book_plan: Mapping[str, Any],
    results: list[Mapping[str, Any]],
) -> list[str]:
    mysteries = [
        *[str(item) for item in series_plan.get("series_mysteries") or []],
        *[str(item) for item in book_plan.get("must_preserve") or []],
    ]
    for result in results:
        chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
        registry = chapter.get("scarcity_registry") if isinstance(chapter.get("scarcity_registry"), Mapping) else {}
        for item in registry.get("items") or []:
            if isinstance(item, Mapping):
                mysteries.append(str(item.get("name") or ""))
    return [f"- {item}" for item in _dedupe([item for item in mysteries if item])] or ["- None"]


def _spent_mystery_lines(
    results: list[Mapping[str, Any]],
    records: list[Mapping[str, Any]],
) -> list[str]:
    spent = []
    for result in results:
        audit = result.get("scarcity_audit") if isinstance(result.get("scarcity_audit"), Mapping) else {}
        spent.extend(str(item) for item in audit.get("spent_mysteries") or [])
    for record in records:
        audit = record.get("scarcity_audit") if isinstance(record.get("scarcity_audit"), Mapping) else {}
        spent.extend(str(item) for item in audit.get("spent_mysteries") or [])
    return [f"- {item}" for item in _dedupe(spent)] or ["- None"]


def _state_change_lines(results: list[Mapping[str, Any]]) -> list[str]:
    lines = []
    for result in results:
        visual = str(result.get("visual_state_update") or "").strip()
        chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
        if visual:
            lines.append(f"- Chapter {chapter.get('number') or '?'}: {_compact(visual)}")
    return lines or ["- None"]


def _pending_decision_lines(records: list[Mapping[str, Any]]) -> list[str]:
    pending = [
        f"- Resolve Chapter {record.get('chapter_number')} quarantine: {record.get('rewrite_instruction') or record.get('reason')}"
        for record in records
        if record.get("status") in {"quarantined", "blocked"}
    ]
    return pending or ["- None"]


def _render_feedback_records(
    results: list[Mapping[str, Any]], effects: list[Any]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for result in results:
        chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
        for record in collect_render_feedback_records(result):
            enriched = dict(record)
            if chapter.get("number") is not None:
                enriched.setdefault("chapter_number", chapter.get("number"))
            records.append(enriched)
    for entry in effects:
        if getattr(entry, "stage", "") != "audio_render":
            continue
        for record in collect_render_feedback_records(entry.to_dict()):
            enriched = dict(record)
            enriched.setdefault("chapter_number", getattr(entry, "chapter_number", None))
            records.append(enriched)
    return records


def _render_feedback_lines(records: list[Mapping[str, Any]]) -> list[str]:
    if not records:
        return ["- None"]
    lines: list[str] = []
    scores = [
        float(record["score"])
        for record in records
        if record.get("score") is not None
    ]
    if scores:
        average = sum(scores) / len(scores)
        lines.append(
            f"- Score range: {min(scores):.2f}-{max(scores):.2f}; average {average:.2f}"
        )
    review_records = [
        record for record in records if bool(record.get("human_review_required"))
    ]
    if review_records:
        lines.append("- Human review required:")
        for record in review_records:
            lines.append(f"  - {_render_feedback_label(record)}")
    invalid = [
        record
        for record in records
        if record.get("directive_valid") is False
        or str(record.get("verdict") or "") == "directive_invalid"
    ]
    if invalid:
        lines.append("- Invalid directives:")
        for record in invalid:
            lines.append(f"  - {_render_feedback_label(record)}")
    low_score = [
        record
        for record in records
        if record.get("score") is not None and float(record.get("score")) < 0.72
    ]
    if low_score:
        lines.append("- Low-score segments:")
        for record in low_score:
            lines.append(f"  - {_render_feedback_label(record)}")
    if not review_records and not invalid and not low_score:
        lines.append("- All recorded audio feedback is accepted.")
    return lines


def _render_feedback_label(record: Mapping[str, Any]) -> str:
    chapter = record.get("chapter_number")
    chapter_text = f"Chapter {chapter} " if chapter not in {None, ""} else ""
    segment = record.get("segment_id") or "unknown segment"
    score = record.get("score")
    score_text = f" score {float(score):.2f}" if score is not None else ""
    verdict = str(record.get("verdict") or "unknown")
    return f"{chapter_text}{segment}{score_text} verdict {verdict}".strip()


def _effect_lines(effects: list[Any]) -> list[str]:
    if not effects:
        return ["- None"]
    return [
        f"- {entry.stage}: {entry.status} ({entry.provider or 'unknown'} {entry.model or ''})".rstrip()
        for entry in effects[-10:]
    ]


def _recommended_next_action(
    results: list[Mapping[str, Any]],
    records: list[Mapping[str, Any]],
    outline: list[Any],
    render_feedback: list[Mapping[str, Any]] | None = None,
) -> str:
    blocked = [record for record in records if record.get("status") in {"quarantined", "blocked"}]
    if blocked:
        first = blocked[0]
        return f"- Fix Chapter {first.get('chapter_number')} quarantine before approving more prose."
    review_audio = [
        record for record in render_feedback or [] if bool(record.get("human_review_required"))
    ]
    if review_audio:
        first = review_audio[0]
        return f"- Review audio for {_render_feedback_label(first)} before the next render pass."
    approved_numbers = [
        int(result.get("chapter", {}).get("number"))
        for result in results
        if isinstance(result.get("chapter"), Mapping) and str(result.get("chapter", {}).get("number") or "").isdigit()
    ]
    next_number = max(approved_numbers, default=0) + 1
    if outline:
        return f"- Prepare Chapter {next_number} using the next outline beat."
    return f"- Prepare Chapter {next_number}."


def _chapter_results(book_root: Path) -> list[Mapping[str, Any]]:
    results = []
    for path in sorted(book_root.glob("chapter*.json")):
        payload = _read_json_object(path)
        if payload:
            results.append(payload)
    return results


def _quarantine_records(book_root: Path) -> list[Mapping[str, Any]]:
    return [
        payload
        for path in sorted((book_root / "quarantine").glob("chapter_*_attempt_*.json"))
        if (payload := _read_json_object(path))
    ]


def _book_plan_from_arc(path: Path, book_number: int) -> dict[str, Any]:
    for item in _read_json_list(path):
        if isinstance(item, Mapping) and int(item.get("book") or 0) == int(book_number):
            return dict(item)
    return {}


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else {}


def _read_json_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload) if isinstance(payload, list) else []


def _compact(value: str, limit: int = 180) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        result.append(value)
        seen.add(key)
    return result
