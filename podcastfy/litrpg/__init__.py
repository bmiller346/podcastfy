"""Storage primitives for local LitRPG audio serials."""

from podcastfy.litrpg.episode_store import EpisodeStore, find_bundle_by_cache_key
from podcastfy.litrpg.episode_store import stable_cache_key
from podcastfy.litrpg.llm import OpenAIResponsesGenerator
from podcastfy.litrpg.pipeline import generate_litrpg_audio_episode
from podcastfy.litrpg.models import CharacterState, EpisodeBundle, EpisodeConfig
from podcastfy.litrpg.models import QuestState, ScriptLine, SeriesState
from podcastfy.litrpg.renderer import RoleScriptRenderer
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.state_store import load_series_state, next_episode_number
from podcastfy.litrpg.state_store import STATE_SCHEMA_VERSION, save_series_state

__all__ = [
    "CharacterState",
    "EpisodeBundle",
    "EpisodeConfig",
    "EpisodeStore",
    "OpenAIResponsesGenerator",
    "QuestState",
    "RoleScriptRenderer",
    "ScriptLine",
    "SeriesState",
    "STATE_SCHEMA_VERSION",
    "find_bundle_by_cache_key",
    "generate_litrpg_audio_episode",
    "get_provider_api_key",
    "load_litrpg_task",
    "load_litrpg_settings",
    "load_series_state",
    "next_episode_number",
    "run_litrpg_task",
    "save_series_state",
    "stable_cache_key",
]


def __getattr__(name):
    if name in {"load_litrpg_task", "run_litrpg_task"}:
        from podcastfy.litrpg.task import load_litrpg_task, run_litrpg_task

        values = {
            "load_litrpg_task": load_litrpg_task,
            "run_litrpg_task": run_litrpg_task,
        }
        return values[name]
    raise AttributeError(f"module 'podcastfy.litrpg' has no attribute {name!r}")
