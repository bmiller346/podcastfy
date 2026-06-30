"""JSON task runner for local LitRPG audio episodes."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from podcastfy.litrpg.bible import format_story_bible_summary, load_story_bible
from podcastfy.litrpg.character_arc import CharacterArcEngine
from podcastfy.litrpg.character_arc import format_character_arc_context
from podcastfy.litrpg.character_arc import merge_arc_state_delta
from podcastfy.litrpg.chapter import generate_litrpg_chapter
from podcastfy.litrpg.config import LitRPGConfig
from podcastfy.litrpg.continuity import format_chapter_memory_context
from podcastfy.litrpg.continuity import load_continuity_ledger
from podcastfy.litrpg.continuity import load_emotional_arcs
from podcastfy.litrpg.continuity import load_world_register
from podcastfy.litrpg.continuity import save_emotional_arcs
from podcastfy.litrpg.effect_log import append_effect_log_entry
from podcastfy.litrpg.effect_log import build_effect_log_entry
from podcastfy.litrpg.effect_log import effect_log_path
from podcastfy.litrpg.foreshadowing import format_foreshadow_context
from podcastfy.litrpg.foreshadowing import load_foreshadow_ledger
from podcastfy.litrpg.harness import approved_for_stage
from podcastfy.litrpg.harness import check_harness_gate
from podcastfy.litrpg.harness import harness_enabled
from podcastfy.litrpg.harness import load_harness_config
from podcastfy.litrpg.harness import normalize_harness_config
from podcastfy.litrpg.agent_state import load_agent_state
from podcastfy.litrpg.agent_state import record_next_chapter_action
from podcastfy.litrpg.agent_state import record_quarantine_blocker
from podcastfy.litrpg.agent_state import save_agent_state
from podcastfy.litrpg.handoff import generate_book_handoff
from podcastfy.litrpg.llm import (
    GeminiGenerator,
    IntentRoutingGemini,
    IntentRoutingOpenAI,
    LOCAL_PROSE_EXACT_STAGES,
    LOCAL_PROSE_STAGE_PREFIXES,
    OllamaGenerator,
    OpenAIResponsesGenerator,
    StageRouterLLM,
)
from podcastfy.litrpg.llm import StageRouting
from podcastfy.litrpg.packages import format_series_package_summary
from podcastfy.litrpg.part_reuse import list_reusable_parts, locked_part_scripts_from_ready_parts
from podcastfy.litrpg.pipeline import generate_litrpg_audio_episode
from podcastfy.litrpg.premise_intake import run_premise_intake
from podcastfy.litrpg.quarantine import next_quarantine_attempt_path
from podcastfy.litrpg.quarantine import quarantine_record_to_dict
from podcastfy.litrpg.quarantine import write_quarantine_record
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.series_architect import SeriesArchitect, format_chapter_contract_context
from podcastfy.litrpg.series_architect import load_book_plan, load_series_shape
from podcastfy.litrpg.showrunner import build_showrunner_payload, format_showrunner_context
from podcastfy.litrpg.state_delta import apply_delta_to_state, extract_state_delta
from podcastfy.litrpg.state_store import load_series_state, save_series_state
from podcastfy.litrpg.voice_cards import format_voice_card_context
from podcastfy.litrpg.voice_cards import load_voice_cards
from podcastfy.litrpg.world_state import load_world_state
from podcastfy.litrpg.world_state import merge_world_state_delta
from podcastfy.litrpg.world_state import save_world_state


class TaskScriptLLM:
    """LLM adapter backed by outline/script fields in a task file."""

    def __init__(self, *, outline: str, script: str) -> None:
        self.outline = outline
        self.script = script

    def generate(self, *, prompt: str, stage: str) -> str:
        if stage == "outline":
            return self.outline
        if stage == "script":
            return self.script
        raise ValueError(f"Unsupported generation stage: {stage}")


def load_litrpg_task(task_path: str | Path) -> dict[str, Any]:
    """Load a LitRPG task JSON file."""
    path = Path(task_path)
    with path.open("r", encoding="utf-8") as task_file:
        task = json.load(task_file)
    if not isinstance(task, dict):
        raise ValueError("LitRPG task file must contain a JSON object")
    return task


def run_litrpg_task(
    task_path: str | Path,
    *,
    llm: Any | None = None,
    tts: Any | None = None,
) -> dict[str, Any]:
    """Run a LitRPG task JSON file through the local episode pipeline."""
    task_file = Path(task_path)
    task = load_litrpg_task(task_file)
    return run_litrpg_task_data(task, task_path=task_file, llm=llm, tts=tts)


def run_litrpg_task_data(
    task: Mapping[str, Any],
    *,
    task_path: str | Path | None = None,
    base_dir: str | Path | None = None,
    llm: Any | None = None,
    tts: Any | None = None,
) -> dict[str, Any]:
    """Run a LitRPG task from an in-memory JSON object."""
    if not isinstance(task, Mapping):
        raise ValueError("LitRPG task must be a JSON object")

    task_file = Path(task_path) if task_path is not None else None
    resolved_base_dir = _task_base_dir(task_file, base_dir)
    settings = load_litrpg_settings(
        _resolve_task_path(resolved_base_dir, task["settings_path"])
        if task.get("settings_path")
        else None
    )
    resolved_llm = llm or _llm_from_task(task, settings=settings)

    mode = str(task.get("mode") or "episode")
    if mode == "premise_intake":
        result = _run_premise_intake_task(
            resolved_base_dir,
            task,
            llm=resolved_llm,
        ).to_dict()
        _write_result_if_requested(resolved_base_dir, task, result)
        return result

    if mode == "chapter":
        chapter_task = _chapter_task_with_paths(resolved_base_dir, task)
        harness_decision = _check_task_harness_gate(
            resolved_base_dir,
            chapter_task,
            stage="chapter_generation",
        )
        if harness_decision is not None and not harness_decision["allowed"]:
            result = {
                "mode": "chapter",
                "status": "approval_required",
                "series_id": str(task.get("series_id") or "default-series"),
                "harness_decision": harness_decision,
            }
            _write_result_if_requested(resolved_base_dir, task, result)
            return result
        result = generate_litrpg_chapter(chapter_task, llm=resolved_llm)
        _write_quarantine_if_needed(resolved_base_dir, chapter_task, result)
        _save_world_state_update_if_requested(resolved_base_dir, chapter_task, result)
        _save_arc_state_update_if_requested(resolved_base_dir, chapter_task, result)
        _append_chapter_effect_if_possible(
            resolved_base_dir,
            chapter_task,
            input_payload=chapter_task,
            output_payload=result,
            stage="chapter_generation",
            status="committed",
        )
        _save_chapter_state_if_requested(resolved_base_dir, chapter_task, result)
        _update_agent_state_after_chapter(resolved_base_dir, chapter_task, result)
        _generate_handoff_if_requested(resolved_base_dir, chapter_task, result)
        _write_result_if_requested(resolved_base_dir, task, result)
        _append_chapter_effect_if_possible(
            resolved_base_dir,
            chapter_task,
            input_payload={"result_path": task.get("result_path"), "result": result},
            output_payload={"result_path": task.get("result_path")},
            stage="chapter_result_write",
            status="committed" if task.get("result_path") else "skipped",
        )
        return result

    config = _config_from_task(task)
    if bool(task.get("render_audio", True)):
        harness_decision = _check_task_harness_gate(
            resolved_base_dir,
            task,
            stage="audio_render",
        )
        if harness_decision is not None and not harness_decision["allowed"]:
            result = {
                "mode": mode,
                "status": "approval_required",
                "series_id": str(task.get("series_id") or "default-series"),
                "harness_decision": harness_decision,
            }
            _write_result_if_requested(resolved_base_dir, task, result)
            return result

    result = generate_litrpg_audio_episode(
        premise=str(task.get("premise") or ""),
        series_id=str(task.get("series_id") or "default-series"),
        storage_dir=_resolve_task_path(resolved_base_dir, task.get("storage_dir", "data/litrpg")),
        episode_number=task.get("episode_number"),
        render_audio=bool(task.get("render_audio", True)),
        tts=tts,
        tts_model=task.get("tts_model"),
        tts_options=task.get("tts"),
        conversation_config=task.get("conversation_config"),
        litrpg_config=config,
        render_loop=task.get("render_loop") if isinstance(task.get("render_loop"), Mapping) else None,
        performance_directives=_performance_directives_from_task(task),
        replay_existing=bool(task.get("replay_existing", True)),
        settings_path=(
            _resolve_task_path(resolved_base_dir, task["settings_path"])
            if task.get("settings_path")
            else None
        ),
        llm=resolved_llm,
    )
    _write_result_if_requested(resolved_base_dir, task, result)
    return result


def _run_premise_intake_task(
    base_dir: Path,
    task: Mapping[str, Any],
    *,
    llm: Any,
):
    premise = str(
        task.get("source_text")
        or task.get("premise_dump")
        or task.get("premise")
        or ""
    ).strip()
    if not premise and task.get("premise_path"):
        premise_path = _resolve_task_path(base_dir, task["premise_path"])
        premise = premise_path.read_text(encoding="utf-8").strip()
    if not premise:
        raise ValueError("premise_intake mode requires premise, source_text, premise_dump, or premise_path")
    return run_premise_intake(
        storage_dir=_resolve_task_path(base_dir, task.get("storage_dir", "data/litrpg")),
        series_id=str(task.get("series_id") or "default-series"),
        premise=premise,
        llm=llm,
        target_books=int(task.get("target_books") or 1),
        chapters_per_book=int(task.get("chapters_per_book") or 30),
        book_length_mode=str(task.get("book_length_mode") or "tight"),
        arc_style=str(task.get("arc_style") or "escalating_floor_survival"),
        series_title=str(task.get("series_title") or ""),
        series_promise=str(task.get("series_promise") or ""),
        endgame_direction=str(task.get("endgame_direction") or ""),
        power_curve=str(task.get("power_curve") or "logarithmic"),
        merge_existing=bool(task.get("merge_existing", True)),
    )


def _performance_directives_from_task(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = (
        task.get("performance_directives")
        or task.get("director_cues")
        or task.get("directives")
    )
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        named = []
        for name, directive in value.items():
            if isinstance(directive, Mapping):
                item = dict(directive)
                item.setdefault("id", str(name))
                named.append(item)
        if named:
            return named
        return [dict(value)]
    return []


def _llm_from_task(task: Mapping[str, Any], *, settings: Mapping[str, Any]) -> Any:
    outline = str(task.get("outline") or "")
    script = str(task.get("script") or "")
    if outline and script:
        return TaskScriptLLM(outline=outline, script=script)
    generation = dict(task.get("generation") or {})
    provider = str(
        generation.get("provider")
        or settings.get("default_generation_provider")
        or "openai"
    ).lower()
    if provider == "openai":
        return _openai_generator_from_config(generation, settings=settings)
    if provider in {"gemini", "geminiapi", "google"}:
        return _gemini_generator_from_config(generation, settings=settings)
    if provider == "ollama":
        return _ollama_generator_from_config(generation)
    if provider == "hybrid":
        _validate_hybrid_local_provider(generation)
        return StageRouterLLM(
            local=_ollama_generator_from_config(generation),
            default=_commercial_generator_from_config(generation, settings=settings),
            routing=StageRouting(
                local_exact=_string_tuple(
                    generation.get("local_exact_stages"),
                    default=LOCAL_PROSE_EXACT_STAGES,
                ),
                local_prefixes=_string_tuple(
                    generation.get("local_stage_prefixes"),
                    default=LOCAL_PROSE_STAGE_PREFIXES,
                ),
            ),
            allow_local_fallback=bool(generation.get("allow_local_fallback", False)),
        )
    raise ValueError(
        "Task must include outline and script fields, pass an llm, or configure "
        "generation.provider=openai, generation.provider=gemini, generation.provider=ollama, "
        "or generation.provider=hybrid"
    )


def _openai_generator_from_config(
    generation: Mapping[str, Any], *, settings: Mapping[str, Any]
) -> OpenAIResponsesGenerator | IntentRoutingOpenAI:
    api_key = get_provider_api_key(str(generation.get("provider") or "openai"), settings) or get_provider_api_key(
        "openai", settings
    )
    if not api_key:
        raise ValueError(
            "OpenAI generation requires a valid API key. Set OPENAI_API_KEY or save "
            "openai_api_key in the LitRPG UI settings."
        )
    base_url = (
        str(generation.get("base_url") or generation.get("api_base_url"))
        if generation.get("base_url") or generation.get("api_base_url")
        else None
    )
    default_model = str(
        generation.get("model")
        or generation.get("commercial_model")
        or settings.get("default_model")
        or "gpt-5.4"
    )
    if bool(generation.get("auto_model_routing")):
        return IntentRoutingOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_model=str(generation.get("default_model") or generation.get("cheap_model") or "gpt-5.4-mini"),
            strong_model=str(generation.get("strong_model") or generation.get("commercial_model") or default_model),
            cheap_model=str(generation.get("cheap_model") or generation.get("mini_model") or "gpt-5.4-mini"),
            nano_model=str(generation.get("nano_model") or "gpt-5.4-nano"),
            reasoning_effort=str(generation.get("reasoning_effort") or "low"),
            strong_reasoning_effort=str(generation.get("strong_reasoning_effort") or "medium"),
            verbosity=str(generation.get("verbosity") or "medium"),
            max_retries=int(generation.get("max_retries") or 3),
            retry_backoff_seconds=float(generation.get("retry_backoff_seconds") or 2.0),
            timeout_seconds=_optional_timeout(generation, default=120.0),
            prompt_char_threshold=int(generation.get("strong_prompt_char_threshold") or 12000),
        )
    return OpenAIResponsesGenerator(
        api_key=api_key,
        model=default_model,
        base_url=base_url,
        reasoning_effort=str(generation.get("reasoning_effort") or "medium"),
        verbosity=str(generation.get("verbosity") or "medium"),
        max_retries=int(generation.get("max_retries") or 3),
        retry_backoff_seconds=float(generation.get("retry_backoff_seconds") or 2.0),
        timeout_seconds=_optional_timeout(generation, default=120.0),
    )


def _gemini_generator_from_config(
    generation: Mapping[str, Any], *, settings: Mapping[str, Any]
) -> GeminiGenerator | IntentRoutingGemini:
    api_key = get_provider_api_key(str(generation.get("provider") or "gemini"), settings) or get_provider_api_key(
        "gemini", settings
    )
    if not api_key:
        raise ValueError(
            "Gemini generation requires a valid API key. Set GEMINI_API_KEY or save "
            "gemini_api_key in the LitRPG UI settings."
        )
    base_url = str(
        generation.get("base_url")
        or generation.get("api_base_url")
        or "https://generativelanguage.googleapis.com/v1beta"
    )
    default_model = str(
        generation.get("model")
        or generation.get("commercial_model")
        or settings.get("default_model")
        or "gemini-2.5-flash"
    )
    if bool(generation.get("auto_model_routing")):
        return IntentRoutingGemini(
            api_key=api_key,
            base_url=base_url,
            default_model=str(generation.get("default_model") or generation.get("cheap_model") or "gemini-2.5-flash-lite"),
            strong_model=str(generation.get("strong_model") or generation.get("commercial_model") or default_model),
            cheap_model=str(generation.get("cheap_model") or generation.get("mini_model") or "gemini-2.5-flash-lite"),
            nano_model=str(generation.get("nano_model") or "gemini-2.5-flash-lite"),
            temperature=_optional_float(generation.get("temperature")),
            top_p=_optional_float(generation.get("top_p")),
            max_output_tokens=_optional_int(generation.get("max_output_tokens")),
            max_retries=int(generation.get("max_retries") or 3),
            retry_backoff_seconds=float(generation.get("retry_backoff_seconds") or 2.0),
            timeout_seconds=_optional_timeout(generation, default=120.0),
            prompt_char_threshold=int(generation.get("strong_prompt_char_threshold") or 12000),
        )
    return GeminiGenerator(
        api_key=api_key,
        model=default_model,
        base_url=base_url,
        system=str(generation.get("system") or generation.get("gemini_system") or "")
        or None,
        temperature=_optional_float(generation.get("temperature")),
        top_p=_optional_float(generation.get("top_p")),
        max_output_tokens=_optional_int(generation.get("max_output_tokens")),
        max_retries=int(generation.get("max_retries") or 3),
        retry_backoff_seconds=float(generation.get("retry_backoff_seconds") or 2.0),
        timeout_seconds=_optional_timeout(generation, default=120.0),
    )


def _ollama_generator_from_config(generation: Mapping[str, Any]) -> OllamaGenerator:
    options = generation.get("ollama_options") or generation.get("local_options") or {}
    if not isinstance(options, Mapping):
        raise ValueError("generation.ollama_options must be a JSON object")
    system = generation.get("local_system") or generation.get("ollama_system")
    return OllamaGenerator(
        model=str(
            generation.get("ollama_model")
            or generation.get("local_model")
            or generation.get("model")
            or "dolphin3"
        ),
        host=str(
            generation.get("ollama_host")
            or generation.get("local_base_url")
            or generation.get("local_host")
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_HOST")
            or "http://localhost:11434"
        ),
        system=str(system) if system else None,
        options=dict(options),
        timeout_seconds=_optional_timeout(generation, default=180.0, key="ollama_timeout_seconds"),
        max_retries=int(generation.get("ollama_max_retries") or generation.get("max_retries") or 2),
        retry_backoff_seconds=float(
            generation.get("ollama_retry_backoff_seconds")
            or generation.get("retry_backoff_seconds")
            or 1.0
        ),
        keep_alive=(
            str(generation.get("ollama_keep_alive"))
            if generation.get("ollama_keep_alive") is not None
            else None
        ),
    )


def _validate_hybrid_local_provider(generation: Mapping[str, Any]) -> None:
    local_provider = str(generation.get("local_provider") or "ollama").lower()
    if local_provider != "ollama":
        raise ValueError(
            "generation.provider=hybrid currently supports only local_provider=ollama. "
            "Use commercial_provider=openai or commercial_provider=gemini for the cloud backend."
        )


def _commercial_generator_from_config(generation: Mapping[str, Any], *, settings: Mapping[str, Any]) -> Any:
    config = _commercial_generation_config(generation)
    provider = str(config.get("provider") or "openai").lower()
    if provider == "openai":
        return _openai_generator_from_config(config, settings=settings)
    if provider in {"gemini", "geminiapi", "google"}:
        return _gemini_generator_from_config(config, settings=settings)
    raise ValueError("generation.commercial_provider currently supports openai or gemini")


def _commercial_generation_config(generation: Mapping[str, Any]) -> dict[str, Any]:
    provider = str(
        generation.get("commercial_provider") or generation.get("cloud_provider") or "openai"
    ).lower()
    if provider not in {"openai", "gemini", "geminiapi", "google"}:
        raise ValueError("generation.commercial_provider currently supports openai or gemini")
    config = dict(generation)
    config["provider"] = provider
    if generation.get("commercial_model") or generation.get("cloud_model"):
        config["model"] = generation.get("commercial_model") or generation["cloud_model"]
    if generation.get("commercial_base_url") or generation.get("commercial_api_base_url"):
        config["base_url"] = generation.get("commercial_base_url") or generation.get(
            "commercial_api_base_url"
        )
    if generation.get("cloud_base_url") or generation.get("cloud_api_base_url"):
        config["base_url"] = generation.get("cloud_base_url") or generation.get(
            "cloud_api_base_url"
        )
    return config


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_timeout(
    generation: Mapping[str, Any],
    *,
    default: float,
    key: str = "timeout_seconds",
) -> float | None:
    if key in generation:
        value = generation.get(key)
    elif key != "timeout_seconds" and "timeout_seconds" in generation:
        value = generation.get("timeout_seconds")
    else:
        return default
    if value is None:
        return None
    return float(value)


def _config_from_task(task: Mapping[str, Any]) -> LitRPGConfig | None:
    config = task.get("litrpg_config")
    if config is None:
        return None
    if not isinstance(config, Mapping):
        raise ValueError("litrpg_config must be a JSON object")
    return LitRPGConfig.from_mapping(config)


def _task_base_dir(task_file: Path | None, base_dir: str | Path | None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    if task_file is not None:
        return task_file.parent
    return Path.cwd()


def _resolve_task_path(base_dir: Path, value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return base_dir / path


def _chapter_task_with_paths(base_dir: Path, task: Mapping[str, Any]) -> dict[str, Any]:
    chapter_task = dict(task)
    storage_dir = (
        _resolve_task_path(base_dir, task["storage_dir"])
        if task.get("storage_dir")
        else None
    )
    series_id = str(task.get("series_id") or "default-series")
    reuse_path = task.get("reuse_ready_parts_from") or task.get("lock_ready_parts_from")
    if reuse_path:
        resolved_reuse_path = _resolve_task_path(base_dir, reuse_path)
        reused_locks = locked_part_scripts_from_ready_parts(
            resolved_reuse_path
        )
        explicit_locks = task.get("locked_part_scripts") or {}
        if not isinstance(explicit_locks, Mapping):
            raise ValueError("locked_part_scripts must be a JSON object")
        chapter_task["part_reuse_source"] = str(resolved_reuse_path)
        chapter_task["part_reuse_report"] = list_reusable_parts(resolved_reuse_path)
        chapter_task["explicit_locked_part_scripts"] = {
            str(part_id): str(script) for part_id, script in explicit_locks.items()
        }
        chapter_task["locked_part_scripts"] = {
            **reused_locks,
            **{str(part_id): str(script) for part_id, script in explicit_locks.items()},
        }
    if task.get("checkpoint_dir"):
        chapter_task["checkpoint_dir"] = str(_resolve_task_path(base_dir, task["checkpoint_dir"]))
    elif task.get("result_path"):
        result_path = _resolve_task_path(base_dir, task["result_path"])
        chapter_task["checkpoint_dir"] = str(
            result_path.parent / f"{result_path.stem}_checkpoints"
        )
    if storage_dir is not None:
        if not chapter_task.get("story_bible_summary"):
            bible = load_story_bible(storage_dir, series_id)
            chapter_task["story_bible_summary"] = format_story_bible_summary(bible)
        if not chapter_task.get("world_state"):
            try:
                chapter_task["world_state"] = load_world_state(storage_dir, series_id)
            except Exception:
                pass
        if not chapter_task.get("emotional_arcs"):
            try:
                chapter_task["emotional_arcs"] = asdict(load_emotional_arcs(storage_dir, series_id))
            except Exception:
                pass
    if not chapter_task.get("series_package_summary"):
        summary = _series_package_summary_from_task(
            base_dir,
            task,
            storage_dir=storage_dir,
            series_id=series_id,
        )
        if summary:
            chapter_task["series_package_summary"] = summary
    chapter_contract = None
    book_number = int(task.get("book_number") or task.get("book") or 1)
    if (
        storage_dir is not None
        and task.get("showrunner") is not False
        and task.get("chapter_contract") is not False
    ):
        architect = SeriesArchitect(storage_dir, series_id)
        if architect.available():
            chapter_number = int(task.get("chapter_number") or task.get("episode_number") or 1)
            chapter_contract = architect.get_chapter_contract(
                book_number=book_number,
                chapter_number=chapter_number,
            )
            chapter_task["chapter_contract"] = chapter_contract
            chapter_task.setdefault("book_number", book_number)
            if chapter_contract.get("title") and not (
                task.get("chapter_title") or task.get("title")
            ):
                chapter_task["chapter_title"] = str(chapter_contract["title"])
            if chapter_contract.get("premise") and not task.get("premise"):
                chapter_task["premise"] = str(chapter_contract["premise"])
            chapter_task.setdefault(
                "showrunner_context",
                format_chapter_contract_context(chapter_contract),
            )
            chapter_task["showrunner"] = {
                "chapter": chapter_number,
                "phase": chapter_contract.get("phase"),
                "tension": chapter_contract.get("tension"),
                "creativity": chapter_contract.get("creativity"),
                "absurdity": chapter_contract.get("absurdity"),
                "directives": list(chapter_contract.get("directives") or []),
                "contract_source": "series_architect",
            }
    if storage_dir is not None:
        _inject_stored_scarcity_sources(
            chapter_task,
            storage_dir=storage_dir,
            series_id=series_id,
            book_number=book_number,
        )
    if task.get("showrunner") is not False:
        showrunner_settings = task.get("showrunner")
        if showrunner_settings is not None and not isinstance(showrunner_settings, Mapping):
            raise ValueError("showrunner must be a JSON object or false")
        settings = dict(showrunner_settings or {})
        chapter_number = int(task.get("chapter_number") or task.get("episode_number") or 1)
        if "chapter_number" in settings:
            chapter_number = int(settings["chapter_number"])
        if chapter_contract is None:
            chapter_task["showrunner"] = build_showrunner_payload(
                chapter_number=chapter_number,
                wandering_event=settings.get("wandering_event"),
                enable_wandering=bool(settings.get("enable_wandering")),
            )
        chapter_task.setdefault(
            "showrunner_context",
            format_showrunner_context(chapter_task["showrunner"]),
        )
    if storage_dir is not None and not chapter_task.get("story_engine_context"):
        chapter_task["story_engine_context"] = _story_engine_context_from_storage(
            storage_dir=storage_dir,
            series_id=series_id,
            task=task,
            chapter_task=chapter_task,
            chapter_contract=chapter_contract,
        )
    if storage_dir is not None:
        explicit_mechanics = task.get("mechanics_context")
        if explicit_mechanics is not None and not isinstance(explicit_mechanics, Mapping):
            raise ValueError("mechanics_context must be a JSON object")
        state = load_series_state(storage_dir / "series" / series_id)
        state_mechanics = _mechanics_context_from_state(state)
        chapter_task["mechanics_context"] = {
            **state_mechanics,
            **dict(explicit_mechanics or {}),
        }
    return chapter_task


def _story_engine_context_from_storage(
    *,
    storage_dir: Path,
    series_id: str,
    task: Mapping[str, Any],
    chapter_task: Mapping[str, Any],
    chapter_contract: Mapping[str, Any] | None,
) -> str:
    contract = dict(chapter_contract or {})
    showrunner = chapter_task.get("showrunner")
    if isinstance(showrunner, Mapping):
        contract.setdefault("phase", showrunner.get("phase"))
        contract.setdefault("tension", showrunner.get("tension"))
        contract.setdefault("creativity", showrunner.get("creativity"))
        contract.setdefault("absurdity", showrunner.get("absurdity"))
    for key in ("floor", "location", "character_focus"):
        if key in task and key not in contract:
            contract[key] = task[key]
    book_number = int(task.get("book_number") or task.get("book") or contract.get("book") or 1)
    chapter_number = int(
        task.get("chapter_number")
        or task.get("episode_number")
        or contract.get("chapter")
        or 1
    )

    blocks = [
        str(task.get("continuity_context") or "").strip(),
        str(task.get("voice_card_context") or task.get("voice_context") or "").strip(),
        str(task.get("foreshadow_context") or "").strip(),
        str(task.get("world_context") or "").strip(),
        str(task.get("emotional_context") or "").strip(),
    ]
    try:
        world_register = load_world_register(storage_dir, series_id)
        emotional_arcs = load_emotional_arcs(storage_dir, series_id)
        memory_context = (
            format_chapter_memory_context(
                ledger=load_continuity_ledger(storage_dir, series_id),
                emotional_arcs=emotional_arcs,
                world_register=world_register,
                chapter_contract=contract,
            )
        )
        blocks.append(memory_context)
        blocks.append(
            format_character_arc_context(
                CharacterArcEngine(storage_dir, series_id).get_chapter_context(
                    chapter_contract=contract,
                )
            )
        )
        if "Locations:" not in memory_context and "Entity ecology:" not in memory_context:
            blocks.append(_broad_world_register_context(world_register))
    except Exception:
        pass
    try:
        deck = load_voice_cards(storage_dir, series_id)
        blocks.append(
            format_voice_card_context(
                deck,
                relevant_names=_string_list(contract.get("character_focus")),
                relevant_roles=_string_list(task.get("required_roles")),
            )
        )
    except Exception:
        pass
    try:
        blocks.append(
            format_foreshadow_context(
                load_foreshadow_ledger(storage_dir, series_id),
                book=book_number,
                chapter=chapter_number,
            )
        )
    except Exception:
        pass
    return "\n\n".join(block for block in blocks if block)


def _inject_stored_scarcity_sources(
    chapter_task: dict[str, Any],
    *,
    storage_dir: Path,
    series_id: str,
    book_number: int,
) -> None:
    if not chapter_task.get("series_plan"):
        try:
            series_plan = load_series_shape(storage_dir, series_id).to_dict()
            chapter_task["series_plan"] = series_plan
            chapter_task.setdefault("series_mysteries", list(series_plan.get("series_mysteries") or []))
        except Exception:
            pass
    if not chapter_task.get("book_plan"):
        try:
            chapter_task["book_plan"] = load_book_plan(storage_dir, series_id, book_number).to_dict()
        except Exception:
            pass
    if not chapter_task.get("foreshadow_ledger"):
        try:
            chapter_task["foreshadow_ledger"] = asdict(load_foreshadow_ledger(storage_dir, series_id))
        except Exception:
            pass


def _broad_world_register_context(world_register: Any) -> str:
    sections = []
    locations = [
        f"{item.name}: {item.detail}"
        for item in getattr(world_register, "locations", [])[:3]
        if getattr(item, "name", "") or getattr(item, "detail", "")
    ]
    entities = [
        f"{item.entity}: {item.detail}"
        for item in getattr(world_register, "entity_ecology", [])[:3]
        if getattr(item, "entity", "") or getattr(item, "detail", "")
    ]
    rules = [
        (
            f"{item.rule}: {item.detail}"
            if getattr(item, "detail", "")
            else str(getattr(item, "rule", ""))
        )
        for item in getattr(world_register, "rules", [])[:3]
        if getattr(item, "rule", "") or getattr(item, "detail", "")
    ]
    economy = [
        f"{item.name}: {item.detail}"
        for item in getattr(world_register, "economy_anchors", [])[:3]
        if getattr(item, "name", "") or getattr(item, "detail", "")
    ]
    for title, values in (
        ("Locations", locations),
        ("Entity ecology", entities),
        ("Rules", rules),
        ("Economy anchors", economy),
    ):
        if values:
            sections.append(title + ":\n" + "\n".join(f"- {value}" for value in values))
    return "\n".join(sections)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _string_tuple(value: Any, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(_string_list(value))


def _series_package_summary_from_task(
    base_dir: Path,
    task: Mapping[str, Any],
    *,
    storage_dir: Path | None,
    series_id: str,
) -> str:
    summary = str(task.get("series_package_summary") or "").strip()
    if summary:
        return summary

    package = task.get("series_package")
    if package is not None:
        if not isinstance(package, Mapping):
            raise ValueError("series_package must be a JSON object")
        return format_series_package_summary(package)

    package_path_value = (
        task.get("series_package_path")
        or task.get("series_package_file")
        or task.get("package_path")
    )
    if package_path_value:
        package_path = _resolve_task_path(base_dir, package_path_value)
        return format_series_package_summary(_load_series_package_file(package_path))

    if storage_dir is None:
        return ""

    default_path = storage_dir / "series" / series_id / "series_package.json"
    if not default_path.exists():
        return ""

    try:
        from podcastfy.litrpg.packages import load_series_package

        loaded = load_series_package(storage_dir, series_id)
        if loaded:
            return format_series_package_summary(loaded)
    except Exception:
        pass

    return format_series_package_summary(_load_series_package_file(default_path))


def _load_series_package_file(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as package_file:
        package = json.load(package_file)
    if not isinstance(package, Mapping):
        raise ValueError("series_package file must contain a JSON object")
    return package


def _save_chapter_state_if_requested(
    base_dir: Path,
    task: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if task.get("persist_state") is False:
        return
    quarantine = result.get("quarantine") if isinstance(result.get("quarantine"), Mapping) else {}
    if quarantine.get("status") in {"quarantined", "blocked"}:
        return
    if not task.get("storage_dir"):
        return

    storage_dir = _resolve_task_path(base_dir, task["storage_dir"])
    series_id = str(result.get("series_id") or task.get("series_id") or "default-series")
    series_dir = storage_dir / "series" / series_id
    state = load_series_state(series_dir)
    chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
    chapter_number = int(chapter.get("number") or task.get("chapter_number") or 0)
    if chapter_number:
        state.episode_number = max(state.episode_number, chapter_number)
    memory_entry = f"Chapter {chapter_number}: {chapter.get('title') or task.get('chapter_title') or 'Untitled'}"
    if memory_entry not in state.memory:
        state.memory.append(memory_entry)
    state = apply_delta_to_state(state, extract_state_delta(result))
    save_series_state(series_dir, state)


def _mechanics_context_from_state(state: Any) -> dict[str, Any]:
    character = state.character
    return {
        "inventory": list(character.inventory),
        "skills": list(character.skills),
        "class": character.character_class,
        "level": character.level,
        "stats": dict(character.stats),
    }


def _apply_chapter_mechanics_to_state(state: Any, result: Mapping[str, Any]) -> None:
    character = state.character
    stats = dict(character.stats)
    xp_total = _optional_int(stats.get("xp"))
    inventory = list(character.inventory)
    skills = list(character.skills)

    for event in _chapter_mechanics_events(result):
        kind = str(event.get("kind") or "")
        display = str(event.get("display") or event.get("term") or "").strip()
        term = str(event.get("term") or display).strip()
        amount = _optional_int(event.get("amount"))
        if kind == "xp_gain" and amount is not None:
            xp_total = (xp_total or 0) + amount
        elif kind == "xp_spend" and amount is not None:
            xp_total = max(0, (xp_total or 0) - amount)
        elif kind == "xp_total" and amount is not None:
            xp_total = amount
        elif kind == "loot_gain" and display:
            _append_unique(inventory, display)
        elif kind in {"item_consumed", "inventory_remove"} and (term or display):
            _remove_normalized(inventory, term or display)
        elif kind == "skill_learned" and display:
            _append_unique(skills, display)

    if xp_total is not None:
        stats["xp"] = xp_total
    character.stats = stats
    character.inventory = inventory
    character.skills = skills


def _chapter_mechanics_events(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    events: list[Mapping[str, Any]] = []
    parts = result.get("parts")
    if not isinstance(parts, list):
        return events
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        gate = part.get("gate")
        if not isinstance(gate, Mapping):
            continue
        final_gate = gate.get("final")
        if not isinstance(final_gate, Mapping):
            continue
        mechanics = final_gate.get("mechanics")
        if not isinstance(mechanics, Mapping):
            continue
        raw_events = mechanics.get("events")
        if not isinstance(raw_events, list):
            continue
        events.extend(event for event in raw_events if isinstance(event, Mapping))
    return events


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _append_unique(values: list[str], value: str) -> None:
    normalized = _normalize_state_term(value)
    if not normalized:
        return
    if normalized not in {_normalize_state_term(item) for item in values}:
        values.append(value)


def _remove_normalized(values: list[str], value: str) -> None:
    normalized = _normalize_state_term(value)
    if not normalized:
        return
    values[:] = [item for item in values if _normalize_state_term(item) != normalized]


def _normalize_state_term(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _write_result_if_requested(
    base_dir: Path, task: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    result_path = task.get("result_path")
    if not result_path:
        return
    path = _resolve_task_path(base_dir, result_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as result_file:
        json.dump(result, result_file, ensure_ascii=True, indent=2, sort_keys=True)
        result_file.write("\n")


def _save_world_state_update_if_requested(
    base_dir: Path,
    task: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if not task.get("update_world_state") or not task.get("storage_dir"):
        return
    update_text = str(result.get("world_state_update") or "").strip()
    if not update_text:
        return
    try:
        update = json.loads(update_text)
    except json.JSONDecodeError:
        return
    if not isinstance(update, Mapping):
        return
    storage_dir = _resolve_task_path(base_dir, task["storage_dir"])
    series_id = str(result.get("series_id") or task.get("series_id") or "default-series")
    current = dict(task.get("world_state") or load_world_state(storage_dir, series_id))
    merged = _merge_world_state_delta(current, update)
    save_world_state(storage_dir, series_id, merged)


def _save_arc_state_update_if_requested(
    base_dir: Path,
    task: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if not task.get("update_arc_state") or not task.get("storage_dir"):
        return
    update_text = str(result.get("arc_state_update") or "").strip()
    if not update_text:
        return
    try:
        update = json.loads(update_text)
    except json.JSONDecodeError:
        return
    if not isinstance(update, Mapping):
        return
    storage_dir = _resolve_task_path(base_dir, task["storage_dir"])
    series_id = str(result.get("series_id") or task.get("series_id") or "default-series")
    current = task.get("emotional_arcs")
    if not isinstance(current, Mapping):
        current = asdict(load_emotional_arcs(storage_dir, series_id))
    merged = merge_arc_state_delta(current, update)
    save_emotional_arcs(storage_dir, series_id, merged)


def _merge_world_state_delta(
    current: Mapping[str, Any],
    update: Mapping[str, Any],
) -> dict[str, Any]:
    return merge_world_state_delta(current, update)


def _write_quarantine_if_needed(
    base_dir: Path,
    task: Mapping[str, Any],
    result: dict[str, Any],
) -> None:
    quarantine = result.get("quarantine")
    if not isinstance(quarantine, Mapping):
        return
    if quarantine.get("status") != "quarantined":
        return
    if not task.get("storage_dir"):
        return
    storage_dir = _resolve_task_path(base_dir, task["storage_dir"])
    series_id = str(result.get("series_id") or task.get("series_id") or "default-series")
    chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
    book_number = int(quarantine.get("book_number") or task.get("book_number") or chapter.get("book") or 1)
    chapter_number = int(
        quarantine.get("chapter_number")
        or chapter.get("number")
        or task.get("chapter_number")
        or 1
    )
    path = next_quarantine_attempt_path(storage_dir, series_id, book_number, chapter_number)
    attempt = _attempt_from_quarantine_path(path)
    max_attempts = int(quarantine.get("max_rewrite_attempts") or task.get("max_rewrite_attempts") or 3)
    status = "blocked" if attempt > max_attempts else "quarantined"
    payload = quarantine_record_to_dict(
        {
            **dict(quarantine),
            "status": status,
            "series_id": series_id,
            "book_number": book_number,
            "chapter_number": chapter_number,
            "attempt": attempt,
            "max_rewrite_attempts": max_attempts,
            "chapter": dict(chapter),
            "parts": list(result.get("parts") or []),
            "combined_script": str(result.get("combined_script") or ""),
        }
    )
    write_quarantine_record(path, payload)
    result["quarantine"] = payload
    result["quarantine"]["path"] = str(path)
    if status == "blocked":
        result["blocked"] = {
            "status": "blocked",
            "reason": "max_rewrite_attempts_exceeded",
            "quarantine_path": str(path),
        }


def _append_chapter_effect_if_possible(
    base_dir: Path,
    task: Mapping[str, Any],
    *,
    input_payload: Any,
    output_payload: Any,
    stage: str,
    status: str,
) -> None:
    if not task.get("storage_dir"):
        return
    storage_dir = _resolve_task_path(base_dir, task["storage_dir"])
    series_id = str(task.get("series_id") or "default-series")
    generation = task.get("generation") if isinstance(task.get("generation"), Mapping) else {}
    chapter_contract = task.get("chapter_contract") if isinstance(task.get("chapter_contract"), Mapping) else {}
    entry = build_effect_log_entry(
        series_id=series_id,
        book_number=int(task.get("book_number") or chapter_contract.get("book") or 1),
        chapter_number=int(task.get("chapter_number") or chapter_contract.get("chapter") or task.get("episode_number") or 1),
        stage=stage,
        input_payload=input_payload,
        output_payload=output_payload,
        provider=str(generation.get("provider") or ""),
        model=str(
            generation.get("model")
            or generation.get("commercial_model")
            or generation.get("local_model")
            or generation.get("ollama_model")
            or ""
        ),
        status=status,
    )
    append_effect_log_entry(effect_log_path(storage_dir, series_id), entry)


def _attempt_from_quarantine_path(path: Path) -> int:
    try:
        return int(path.stem.rsplit("_attempt_", 1)[1])
    except (IndexError, ValueError):
        return 1


def _update_agent_state_after_chapter(
    base_dir: Path,
    task: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if not task.get("storage_dir"):
        return
    storage_dir = _resolve_task_path(base_dir, task["storage_dir"])
    series_id = str(result.get("series_id") or task.get("series_id") or "default-series")
    state = load_agent_state(storage_dir, series_id)
    chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
    chapter_number = int(chapter.get("number") or task.get("chapter_number") or 0)
    book_number = int(task.get("book_number") or chapter.get("book") or 1)
    quarantine = result.get("quarantine") if isinstance(result.get("quarantine"), Mapping) else {}
    if quarantine.get("status") == "blocked":
        state = record_quarantine_blocker(
            state,
            series_id=series_id,
            chapter_number=chapter_number or int(quarantine.get("chapter_number") or 0),
            quarantine_path=str(quarantine.get("path") or ""),
            reason=str(result.get("blocked", {}).get("reason") if isinstance(result.get("blocked"), Mapping) else quarantine.get("reason") or ""),
        )
    elif quarantine.get("status") not in {"quarantined", "blocked"} and chapter_number:
        hook = result.get("hook_review") or quarantine.get("rewrite_instruction") or ""
        state = record_next_chapter_action(
            state,
            series_id=series_id,
            book_number=book_number,
            chapter_number=chapter_number,
            opener=str(hook),
        )
    save_agent_state(storage_dir, state)


def _generate_handoff_if_requested(
    base_dir: Path,
    task: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if not task.get("storage_dir"):
        return
    if not (task.get("generate_handoff") or task.get("book_complete")):
        return
    storage_dir = _resolve_task_path(base_dir, task["storage_dir"])
    series_id = str(result.get("series_id") or task.get("series_id") or "default-series")
    chapter = result.get("chapter") if isinstance(result.get("chapter"), Mapping) else {}
    book_number = int(task.get("book_number") or chapter.get("book") or 1)
    generate_book_handoff(storage_dir, series_id, book_number)


def _check_task_harness_gate(
    base_dir: Path,
    task: Mapping[str, Any],
    *,
    stage: str,
) -> dict[str, Any] | None:
    if not harness_enabled(task):
        return None
    config = _harness_config_for_task(base_dir, task)
    decision = check_harness_gate(
        stage,
        task,
        config,
        approved=approved_for_stage(task, stage),
    )
    return decision.to_dict()


def _harness_config_for_task(base_dir: Path, task: Mapping[str, Any]) -> Mapping[str, Any]:
    inline = task.get("harness")
    if isinstance(inline, Mapping) and inline.get("stages"):
        return normalize_harness_config(inline)
    if task.get("harness_path"):
        path = _resolve_task_path(base_dir, task["harness_path"])
        with path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        if not isinstance(payload, Mapping):
            raise ValueError("harness_path must point to a JSON object")
        return normalize_harness_config(payload)
    storage_dir = (
        _resolve_task_path(base_dir, task["storage_dir"])
        if task.get("storage_dir")
        else base_dir
    )
    series_id = str(task.get("series_id") or "default-series")
    book_number = _optional_int(task.get("book_number") or task.get("book"))
    return load_harness_config(storage_dir, series_id, book_number=book_number)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local LitRPG task JSON file.")
    parser.add_argument("task", help="Path to task.json")
    args = parser.parse_args()
    result = run_litrpg_task(args.task)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
