"""JSON task runner for local LitRPG audio episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from podcastfy.litrpg.config import LitRPGConfig
from podcastfy.litrpg.llm import OpenAIResponsesGenerator
from podcastfy.litrpg.pipeline import generate_litrpg_audio_episode
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings


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
    settings = load_litrpg_settings(
        _resolve_task_path(task_file, task["settings_path"])
        if task.get("settings_path")
        else None
    )
    resolved_llm = llm or _llm_from_task(task, settings=settings)
    config = _config_from_task(task)

    result = generate_litrpg_audio_episode(
        premise=str(task.get("premise") or ""),
        series_id=str(task.get("series_id") or "default-series"),
        storage_dir=_resolve_task_path(task_file, task.get("storage_dir", "data/litrpg")),
        episode_number=task.get("episode_number"),
        render_audio=bool(task.get("render_audio", True)),
        tts=tts,
        tts_model=task.get("tts_model"),
        tts_options=task.get("tts"),
        conversation_config=task.get("conversation_config"),
        litrpg_config=config,
        replay_existing=bool(task.get("replay_existing", True)),
        settings_path=(
            _resolve_task_path(task_file, task["settings_path"])
            if task.get("settings_path")
            else None
        ),
        llm=resolved_llm,
    )
    _write_result_if_requested(task_file, task, result)
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


def _resolve_task_path(task_file: Path, value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return task_file.parent / path


def _write_result_if_requested(
    task_file: Path, task: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    result_path = task.get("result_path")
    if not result_path:
        return
    path = _resolve_task_path(task_file, result_path)
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
