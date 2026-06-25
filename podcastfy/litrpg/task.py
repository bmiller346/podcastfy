"""JSON task runner for local LitRPG audio episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from podcastfy.litrpg.bible import format_story_bible_summary, load_story_bible
from podcastfy.litrpg.chapter import generate_litrpg_chapter
from podcastfy.litrpg.config import LitRPGConfig
from podcastfy.litrpg.llm import OpenAIResponsesGenerator
from podcastfy.litrpg.part_reuse import locked_part_scripts_from_ready_parts
from podcastfy.litrpg.pipeline import generate_litrpg_audio_episode
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.state_store import load_series_state, save_series_state


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

    if str(task.get("mode") or "episode") == "chapter":
        chapter_task = _chapter_task_with_paths(resolved_base_dir, task)
        result = generate_litrpg_chapter(chapter_task, llm=resolved_llm)
        _save_chapter_state_if_requested(resolved_base_dir, chapter_task, result)
        _write_result_if_requested(resolved_base_dir, task, result)
        return result

    config = _config_from_task(task)

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


def _llm_from_task(task: Mapping[str, Any], *, settings: Mapping[str, Any]) -> Any:
    outline = str(task.get("outline") or "")
    script = str(task.get("script") or "")
    if outline and script:
        return TaskScriptLLM(outline=outline, script=script)
    generation = dict(task.get("generation") or {})
    provider = str(generation.get("provider") or "openai")
    if provider == "openai":
        return OpenAIResponsesGenerator(
            api_key=get_provider_api_key("openai", settings),
            model=str(generation.get("model") or "gpt-5.5"),
            reasoning_effort=str(generation.get("reasoning_effort") or "medium"),
            verbosity=str(generation.get("verbosity") or "medium"),
            max_retries=int(generation.get("max_retries") or 3),
            retry_backoff_seconds=float(generation.get("retry_backoff_seconds") or 2.0),
            timeout_seconds=(
                None
                if "timeout_seconds" in generation and generation.get("timeout_seconds") is None
                else float(generation.get("timeout_seconds"))
                if "timeout_seconds" in generation
                else 120.0
            ),
        )
    raise ValueError(
        "Task must include outline and script fields, pass an llm, or configure generation.provider=openai"
    )


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
        reused_locks = locked_part_scripts_from_ready_parts(
            _resolve_task_path(base_dir, reuse_path)
        )
        explicit_locks = task.get("locked_part_scripts") or {}
        if not isinstance(explicit_locks, Mapping):
            raise ValueError("locked_part_scripts must be a JSON object")
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


def _save_chapter_state_if_requested(
    base_dir: Path,
    task: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if task.get("persist_state") is False:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local LitRPG task JSON file.")
    parser.add_argument("task", help="Path to task.json")
    args = parser.parse_args()
    result = run_litrpg_task(args.task)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
