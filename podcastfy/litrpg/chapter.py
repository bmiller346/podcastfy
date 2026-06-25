"""Chapter production orchestration for render-ready LitRPG scripts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.production import ChapterPart
from podcastfy.litrpg.production import build_chapter_part_prompt
from podcastfy.litrpg.production import build_chapter_plan
from podcastfy.litrpg.production import build_chapter_review_prompt
from podcastfy.litrpg.production import build_part_review_prompt


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
    generated_parts: list[dict[str, Any]] = []
    part_scripts: list[str] = []

    for part in plan.parts:
        prompt = build_chapter_part_prompt(
            chapter_plan=plan,
            part=part,
            prior_parts_summary=_prior_parts_summary(generated_parts),
        )
        script = llm.generate(prompt=prompt, stage=f"part:{part.part_id}")

        review_prompt = ""
        review = ""
        if reviews_enabled:
            review_prompt = build_part_review_prompt(
                part_script=script,
                required_roles=part.required_roles,
            )
            review = llm.generate(prompt=review_prompt, stage=f"review:{part.part_id}")

        part_scripts.append(script)
        generated_parts.append(
            {
                "part_id": part.part_id,
                "title": part.title,
                "purpose": part.purpose,
                "target_minutes": part.target_minutes,
                "required_roles": list(part.required_roles),
                "injected_beats": list(part.injected_beats),
                "prompt": prompt,
                "script": script,
                "review_prompt": review_prompt,
                "review": review,
            }
        )

    chapter_review_prompt = ""
    chapter_review = ""
    if reviews_enabled:
        chapter_review_prompt = build_chapter_review_prompt(
            part_scripts=part_scripts,
            cast_roles=plan.cast_roles,
        )
        chapter_review = llm.generate(prompt=chapter_review_prompt, stage="chapter_review")

    combined_script = _combine_part_scripts(generated_parts)
    return {
        "mode": "chapter",
        "series_id": str(task.get("series_id") or "default-series"),
        "chapter": {
            "number": chapter_number,
            "title": title,
            "premise": premise,
            "target_minutes": target_minutes,
            "injected_beats": injected_beats,
            "plan": plan.to_dict(),
            "generation": dict(task.get("generation") or {}),
            "reviews_enabled": reviews_enabled,
        },
        "parts": generated_parts,
        "chapter_review_prompt": chapter_review_prompt,
        "chapter_review": chapter_review,
        "combined_script": combined_script,
        "render": {
            "ready": True,
            "audio_rendered": False,
            "script": combined_script,
            "role_tags": sorted(plan.cast_roles),
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
        sections.append(f"<!-- {part['part_id']}: {part['title']} -->\n{part['script']}")
    return "\n\n".join(sections).strip()


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
