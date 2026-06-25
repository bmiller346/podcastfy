"""Chapter production orchestration for render-ready LitRPG scripts."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.casting import build_role_tts_instructions
from podcastfy.litrpg.casting import cast_plan_from_mapping
from podcastfy.litrpg.mechanics import validate_mechanics
from podcastfy.litrpg.qa import build_chapter_qa
from podcastfy.litrpg.production import ChapterPart
from podcastfy.litrpg.production import build_chapter_part_prompt
from podcastfy.litrpg.production import build_chapter_plan
from podcastfy.litrpg.production import build_chapter_review_prompt
from podcastfy.litrpg.production import build_description_audit_prompt
from podcastfy.litrpg.production import build_director_pass_prompt
from podcastfy.litrpg.production import build_mechanics_audit_prompt
from podcastfy.litrpg.production import build_part_review_prompt
from podcastfy.litrpg.production import build_part_revision_prompt
from podcastfy.litrpg.production import build_showmanship_audit_prompt
from podcastfy.litrpg.production import build_tonal_audit_prompt
from podcastfy.litrpg.production import build_visual_state_extraction_prompt
from podcastfy.litrpg.sfx import build_mix_plan
from podcastfy.litrpg.sfx import map_assets_for_cue_sheet
from podcastfy.litrpg.sfx import parse_cue_sheet


def generate_litrpg_chapter(task: Mapping[str, Any], *, llm: Any) -> dict[str, Any]:
    """Generate a chapter plan, part scripts, reviews, and combined render text."""
    if llm is None:
        raise ValueError("Chapter tasks require an llm or generation provider")

    chapter_number = int(task.get("chapter_number") or 1)
    title = str(task.get("chapter_title") or task.get("title") or f"Chapter {chapter_number}")
    premise = str(task.get("premise") or "")
    target_minutes = int(task.get("target_minutes") or 30)
    injected_beats = _string_list(task.get("injected_beats"))

    plan = build_chapter_plan(
        premise=premise,
        chapter_number=chapter_number,
        title=title,
        target_minutes=target_minutes,
        cast_roles=_mapping_or_none(task.get("cast_roles")),
        injected_beats=injected_beats,
    )
    plan.parts = _apply_part_overrides(
        plan.parts,
        _mapping_or_none(task.get("part_overrides")) or {},
    )

    reviews_enabled = _reviews_enabled(task)
    revision_enabled = _revision_enabled(task)
    locked_part_scripts = _mapping_or_none(task.get("locked_part_scripts")) or {}
    target_tone = str(task.get("tone") or task.get("target_tone") or "")
    story_bible_summary = str(task.get("story_bible_summary") or "")
    series_package_summary = _series_package_summary_from_task(task)
    mechanics_context = _mapping_or_none(task.get("mechanics_context")) or {}
    retry_options = _retry_options(task)
    checkpoint_dir = _checkpoint_dir(task)
    generated_parts: list[dict[str, Any]] = []
    part_scripts: list[str] = []

    for part_index, part in enumerate(plan.parts, 1):
        prompt = build_chapter_part_prompt(
            chapter_plan=plan,
            part=part,
            prior_parts_summary=_prior_parts_summary(generated_parts),
            story_bible_summary=story_bible_summary,
            series_package_summary=series_package_summary,
        )
        locked_script = locked_part_scripts.get(part.part_id)
        script = (
            str(locked_script)
            if locked_script is not None
            else _generate_with_retry(
                llm,
                prompt=prompt,
                stage=f"part:{part.part_id}",
                retry_options=retry_options,
            )
        )

        review_prompt = ""
        review = ""
        director_prompt = ""
        director_tags = ""
        mechanics_audit_prompt = ""
        mechanics_audit = ""
        description_audit_prompt = ""
        description_audit = ""
        tonal_audit_prompt = ""
        tonal_audit = ""
        showmanship_audit_prompt = ""
        showmanship_audit = ""
        revision_prompt = ""
        revised_script = script
        deterministic_gate = _deterministic_part_gate(
            part_script=script,
            required_roles=part.required_roles,
            mechanics_context=mechanics_context,
        )
        if reviews_enabled:
            review_prompt = build_part_review_prompt(
                part_script=script,
                required_roles=part.required_roles,
                series_package_summary=series_package_summary,
            )
            review = _generate_with_retry(
                llm,
                prompt=review_prompt,
                stage=f"review:{part.part_id}",
                retry_options=retry_options,
            )
            director_prompt = build_director_pass_prompt(
                part_script=script,
                required_roles=part.required_roles,
                series_package_summary=series_package_summary,
            )
            director_tags = _generate_with_retry(
                llm,
                prompt=director_prompt,
                stage=f"director:{part.part_id}",
                retry_options=retry_options,
            )
            mechanics_audit_prompt = build_mechanics_audit_prompt(
                part_script=script,
                chapter_premise=premise,
                prior_parts_summary=_prior_parts_summary(generated_parts),
                story_bible_summary=story_bible_summary,
                series_package_summary=series_package_summary,
            )
            mechanics_audit = _generate_with_retry(
                llm,
                prompt=mechanics_audit_prompt,
                stage=f"mechanics:{part.part_id}",
                retry_options=retry_options,
            )
            description_audit_prompt = build_description_audit_prompt(
                part_script=script,
                story_bible_summary=story_bible_summary,
            )
            description_audit = _generate_with_retry(
                llm,
                prompt=description_audit_prompt,
                stage=f"description:{part.part_id}",
                retry_options=retry_options,
            )
            tonal_audit_prompt = build_tonal_audit_prompt(
                part_script=script,
                target_tone=target_tone,
            )
            tonal_audit = _generate_with_retry(
                llm,
                prompt=tonal_audit_prompt,
                stage=f"tonal:{part.part_id}",
                retry_options=retry_options,
            )
            showmanship_audit_prompt = build_showmanship_audit_prompt(part_script=script)
            showmanship_audit = _generate_with_retry(
                llm,
                prompt=showmanship_audit_prompt,
                stage=f"showmanship:{part.part_id}",
                retry_options=retry_options,
            )
            if revision_enabled:
                revision_prompt = build_part_revision_prompt(
                    draft_script=script,
                    director_tags=director_tags,
                    mechanics_audit=mechanics_audit,
                    tonal_audit=tonal_audit,
                    showmanship_audit=showmanship_audit,
                    required_roles=part.required_roles,
                    description_audit=description_audit,
                    series_package_summary=series_package_summary,
                )
                revised_script = _generate_with_retry(
                    llm,
                    prompt=revision_prompt,
                    stage=f"revise:{part.part_id}",
                    retry_options=retry_options,
                )

        final_gate = _deterministic_part_gate(
            part_script=revised_script,
            required_roles=part.required_roles,
            mechanics_context=mechanics_context,
        )
        part_scripts.append(revised_script)
        part_record = {
            "part_id": part.part_id,
            "title": part.title,
            "purpose": part.purpose,
            "target_minutes": part.target_minutes,
            "required_roles": list(part.required_roles),
            "injected_beats": list(part.injected_beats),
            "prompt": prompt,
            "locked": locked_script is not None,
            "script": script,
            "review_prompt": review_prompt,
            "review": review,
            "director_prompt": director_prompt,
            "director_tags": director_tags,
            "mechanics_audit_prompt": mechanics_audit_prompt,
            "mechanics_audit": mechanics_audit,
            "description_audit_prompt": description_audit_prompt,
            "description_audit": description_audit,
            "tonal_audit_prompt": tonal_audit_prompt,
            "tonal_audit": tonal_audit,
            "showmanship_audit_prompt": showmanship_audit_prompt,
            "showmanship_audit": showmanship_audit,
            "revision_prompt": revision_prompt,
            "revised_script": revised_script,
            "gate": {
                "draft": deterministic_gate,
                "final": final_gate,
                "ready": final_gate["ready"],
            },
        }
        generated_parts.append(part_record)
        _write_part_checkpoint(
            checkpoint_dir=checkpoint_dir,
            part_index=part_index,
            chapter_number=chapter_number,
            chapter_title=title,
            series_id=str(task.get("series_id") or "default-series"),
            part_record=part_record,
        )

    chapter_review_prompt = ""
    chapter_review = ""
    if reviews_enabled:
        chapter_review_prompt = build_chapter_review_prompt(
            part_scripts=part_scripts,
            cast_roles=plan.cast_roles,
            series_package_summary=series_package_summary,
        )
        chapter_review = _generate_with_retry(
            llm,
            prompt=chapter_review_prompt,
            stage="chapter_review",
            retry_options=retry_options,
        )

    combined_script = _combine_part_scripts(generated_parts)
    visual_state_update_prompt = ""
    visual_state_update = ""
    if reviews_enabled:
        visual_state_update_prompt = build_visual_state_extraction_prompt(
            final_script=combined_script,
            story_bible_summary=story_bible_summary,
        )
        visual_state_update = _generate_with_retry(
            llm,
            prompt=visual_state_update_prompt,
            stage="visual_state_update",
            retry_options=retry_options,
        )
    cue_sheet = parse_cue_sheet(combined_script)
    asset_mappings = map_assets_for_cue_sheet(cue_sheet)
    mix_plan = build_mix_plan(cue_sheet, asset_mappings=asset_mappings)
    qa = build_chapter_qa(generated_parts)
    render_ready = bool(qa["ready"])
    role_instructions = _build_render_role_instructions(
        task=task,
        qa=qa,
        cast_roles=plan.cast_roles,
    )
    return {
        "mode": "chapter",
        "series_id": str(task.get("series_id") or "default-series"),
        "chapter": {
            "number": chapter_number,
            "title": title,
            "premise": premise,
            "target_minutes": target_minutes,
            "injected_beats": injected_beats,
            "story_bible_summary": story_bible_summary,
            "series_package_summary": series_package_summary,
            "mechanics_context": dict(mechanics_context),
            "plan": plan.to_dict(),
            "generation": dict(task.get("generation") or {}),
            "reviews_enabled": reviews_enabled,
            "revision_enabled": revision_enabled,
        },
        "parts": generated_parts,
        "chapter_review_prompt": chapter_review_prompt,
        "chapter_review": chapter_review,
        "visual_state_update_prompt": visual_state_update_prompt,
        "visual_state_update": visual_state_update,
        "qa": qa,
        "combined_script": combined_script,
        "render": {
            "ready": render_ready,
            "audio_rendered": False,
            "script": cue_sheet.clean_script,
            "script_with_cues": combined_script,
            "cue_sheet": cue_sheet.to_dict(),
            "asset_mappings": [mapping.to_dict() for mapping in asset_mappings],
            "mix_plan": mix_plan,
            "role_tags": sorted(plan.cast_roles),
            "role_instructions": role_instructions,
            "metadata": {
                "series_id": str(task.get("series_id") or "default-series"),
                "chapter_number": chapter_number,
                "chapter_title": title,
            },
        },
    }


def _apply_part_overrides(
    parts: Sequence[ChapterPart], overrides: Mapping[str, Any]
) -> list[ChapterPart]:
    updated: list[ChapterPart] = []
    for part in parts:
        override = overrides.get(part.part_id)
        if not isinstance(override, Mapping):
            updated.append(part)
            continue

        values: dict[str, Any] = {}
        for field_name in ("title", "purpose"):
            if field_name in override:
                values[field_name] = str(override[field_name])
        if "target_minutes" in override:
            values["target_minutes"] = int(override["target_minutes"])
        if "required_roles" in override:
            values["required_roles"] = [
                str(role).upper() for role in _string_list(override["required_roles"])
            ]
        if "injected_beats" in override:
            values["injected_beats"] = _string_list(override["injected_beats"])
        if "extra_injected_beats" in override:
            values["injected_beats"] = list(values.get("injected_beats", part.injected_beats))
            values["injected_beats"].extend(_string_list(override["extra_injected_beats"]))

        updated.append(replace(part, **values))
    return updated


def _reviews_enabled(task: Mapping[str, Any]) -> bool:
    for key in ("reviews", "review_settings"):
        settings = task.get(key)
        if isinstance(settings, Mapping) and "enabled" in settings:
            return bool(settings["enabled"])
    if "reviews_enabled" in task:
        return bool(task["reviews_enabled"])
    return True


def _revision_enabled(task: Mapping[str, Any]) -> bool:
    for key in ("reviews", "review_settings"):
        settings = task.get(key)
        if isinstance(settings, Mapping) and "rewrite" in settings:
            return bool(settings["rewrite"])
        if isinstance(settings, Mapping) and "revision_enabled" in settings:
            return bool(settings["revision_enabled"])
    if "revision_enabled" in task:
        return bool(task["revision_enabled"])
    return True


def _retry_options(task: Mapping[str, Any]) -> dict[str, Any]:
    settings = task.get("generation")
    if not isinstance(settings, Mapping):
        settings = task.get("retry")
    if not isinstance(settings, Mapping):
        settings = {}
    return {
        "max_retries": max(1, int(settings.get("max_retries") or 3)),
        "retry_backoff_seconds": max(
            0.0,
            float(settings.get("retry_backoff_seconds") or 2.0),
        ),
    }


def _generate_with_retry(
    llm: Any,
    *,
    prompt: str,
    stage: str,
    retry_options: Mapping[str, Any],
) -> str:
    max_retries = int(retry_options.get("max_retries") or 3)
    backoff = float(retry_options.get("retry_backoff_seconds") or 2.0)
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return str(llm.generate(prompt=prompt, stage=stage))
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise RuntimeError(
        f"Chapter generation failed for stage {stage!r} after {max_retries} attempts"
    ) from last_error


def _checkpoint_dir(task: Mapping[str, Any]) -> Path | None:
    value = task.get("checkpoint_dir")
    if not value:
        return None
    return Path(str(value))


def _write_part_checkpoint(
    *,
    checkpoint_dir: Path | None,
    part_index: int,
    chapter_number: int,
    chapter_title: str,
    series_id: str,
    part_record: Mapping[str, Any],
) -> None:
    if checkpoint_dir is None:
        return
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    safe_part_id = _safe_filename(str(part_record["part_id"]))
    prefix = f"{part_index:02d}_{safe_part_id}"
    payload = {
        "series_id": series_id,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "part_index": part_index,
        "part": dict(part_record),
    }
    json_path = checkpoint_dir / f"{prefix}.json"
    script_path = checkpoint_dir / f"{prefix}_approved.xml"
    with json_path.open("w", encoding="utf-8") as checkpoint_file:
        json.dump(payload, checkpoint_file, ensure_ascii=True, indent=2, sort_keys=True)
        checkpoint_file.write("\n")
    script_path.write_text(
        str(part_record.get("revised_script") or part_record.get("script") or ""),
        encoding="utf-8",
    )


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return safe.strip("-_") or "part"


def _deterministic_part_gate(
    *,
    part_script: str,
    required_roles: Sequence[str],
    mechanics_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    upper_script = part_script.upper()
    missing_roles = [
        role for role in required_roles if f"<{role}" not in upper_script
    ]
    mechanics_result = validate_mechanics(part_script, mechanics_context)
    mechanics_terms = mechanics_result.get("normalized_terms", {})
    issues = []
    if missing_roles:
        issues.append(f"Missing required role tags: {', '.join(missing_roles)}")
    issues.extend(str(issue) for issue in mechanics_result.get("issues", []))
    return {
        "ready": not issues,
        "issues": issues,
        "missing_roles": missing_roles,
        "mechanics_terms": mechanics_terms,
        "mechanics": mechanics_result,
    }


def _build_render_role_instructions(
    *,
    task: Mapping[str, Any],
    qa: Mapping[str, Any],
    cast_roles: Mapping[str, str],
) -> dict[str, str]:
    manifest_entries = _casting_manifest_entries(task)
    director_cues = _director_cues_by_role(qa)
    instructions: dict[str, str] = {}
    for role in sorted(cast_roles):
        entry = dict(manifest_entries.get(role) or {})
        if "instructions" not in entry and cast_roles.get(role):
            entry["instructions"] = cast_roles[role]
        cue = director_cues.get(role)
        if not entry and not cue:
            continue
        instructions[role] = build_role_tts_instructions(role, entry, cue)
    return instructions


def _casting_manifest_entries(task: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    value = (
        task.get("casting_manifest")
        or task.get("audio_casting_manifest")
        or task.get("cast_manifest")
        or task.get("cast_plan")
    )
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Casting manifest must be a JSON object")
    if any(key in value for key in ("cast_members", "members", "provider_defaults")):
        plan = cast_plan_from_mapping(value, merge_defaults=False)
        return {
            member.role: member.voice_profile.to_renderer_dict()
            for member in plan.cast_members
        }
    entries: dict[str, Mapping[str, Any]] = {}
    for role, entry in value.items():
        normalized_role = str(role).upper()
        if isinstance(entry, Mapping):
            entries[normalized_role] = entry
        else:
            entries[normalized_role] = {"voice": str(entry)}
    return entries


def _director_cues_by_role(qa: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cues: dict[str, Mapping[str, Any]] = {}
    for part in qa.get("parts", []):
        if not isinstance(part, Mapping):
            continue
        audits = part.get("audits")
        if not isinstance(audits, Mapping):
            continue
        director = audits.get("director")
        if not isinstance(director, Mapping):
            continue
        raw_cues = director.get("cues")
        if not isinstance(raw_cues, Sequence) or isinstance(raw_cues, (str, bytes)):
            continue
        for cue in raw_cues:
            if not isinstance(cue, Mapping):
                continue
            role = str(cue.get("role") or "").upper()
            if role and role not in cues:
                cues[role] = cue
    return cues


def _prior_parts_summary(parts: Sequence[Mapping[str, Any]]) -> str:
    if not parts:
        return ""
    return "\n".join(
        f"- {part['title']}: generated {len(str(part['script']))} characters."
        for part in parts
    )


def _combine_part_scripts(parts: Sequence[Mapping[str, Any]]) -> str:
    sections = []
    for part in parts:
        script = str(part.get("revised_script") or part["script"])
        sections.append(f"<!-- {part['part_id']}: {part['title']} -->\n{script}")
    return "\n\n".join(sections).strip()


def _series_package_summary_from_task(task: Mapping[str, Any]) -> str:
    summary = str(task.get("series_package_summary") or "").strip()
    if summary:
        return summary
    package = task.get("series_package")
    if not isinstance(package, Mapping):
        return ""
    return _format_series_package_summary(package)


def _format_series_package_summary(package: Mapping[str, Any]) -> str:
    try:
        from podcastfy.litrpg.packages import format_series_package_summary

        return str(format_series_package_summary(package)).strip()
    except Exception:
        pass

    lines: list[str] = []
    metadata = package.get("metadata")
    if isinstance(metadata, Mapping):
        title = metadata.get("title") or metadata.get("series_title")
        logline = metadata.get("logline")
        if title:
            lines.append(f"Title: {title}")
        if logline:
            lines.append(f"Logline: {logline}")

    system = package.get("system_announcer")
    if isinstance(system, Mapping):
        lines.append(_named_package_line("System announcer", system))

    characters = package.get("characters") or package.get("character_packages")
    if isinstance(characters, Mapping):
        character_lines = [
            _named_package_line(str(name), value)
            for name, value in characters.items()
            if isinstance(value, Mapping)
        ]
        if character_lines:
            lines.append("Characters: " + "; ".join(character_lines))

    for key, label in (
        ("familiar", "Familiar"),
        ("home_base", "Home base"),
        ("floor_rules", "Floor rules"),
        ("faction_map", "Faction map"),
    ):
        value = package.get(key)
        if isinstance(value, Mapping):
            lines.append(_named_package_line(label, value))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            values = [str(item) for item in value if str(item).strip()]
            if values:
                lines.append(f"{label}: {', '.join(values[:5])}")

    return "\n".join(line for line in lines if line).strip()


def _named_package_line(label: str, value: Mapping[str, Any]) -> str:
    pieces = []
    name = value.get("name") or value.get("title")
    if name:
        pieces.append(str(name))
    for key in ("voice", "tone", "role", "purpose", "summary", "rules"):
        raw = value.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            compact = ", ".join(str(item) for item in raw[:3])
        else:
            compact = str(raw or "")
        if compact:
            pieces.append(compact)
    return f"{label}: {' | '.join(pieces)}" if pieces else f"{label}: configured"


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("Expected a JSON object")
    return value


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence):
        raise ValueError("Expected a JSON array")
    return [str(item) for item in value]
