"""Storage primitives for local LitRPG audio serials."""

from podcastfy.litrpg.casting import CastMember, CastPlan, VoiceProfile
from podcastfy.litrpg.casting import build_default_cast_plan, cast_plan_from_mapping
from podcastfy.litrpg.casting import export_voices_for_litrpg_config
from podcastfy.litrpg.casting import generate_audition_script, load_cast_plan_json
from podcastfy.litrpg.casting import validate_cast_plan
from podcastfy.litrpg.chapter import generate_litrpg_chapter
from podcastfy.litrpg.episode_store import EpisodeStore, find_bundle_by_cache_key
from podcastfy.litrpg.episode_store import stable_cache_key
from podcastfy.litrpg.library import delete_episode, get_audio_path, get_episode
from podcastfy.litrpg.library import list_episodes, list_regenerable_parts, list_series
from podcastfy.litrpg.library import mark_episode_status
from podcastfy.litrpg.llm import OpenAIResponsesGenerator
from podcastfy.litrpg.pipeline import generate_litrpg_audio_episode
from podcastfy.litrpg.models import CharacterState, EpisodeBundle, EpisodeConfig
from podcastfy.litrpg.models import QuestState, ScriptLine, SeriesState
from podcastfy.litrpg.renderer import RoleScriptRenderer
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.state_store import load_series_state, next_episode_number
from podcastfy.litrpg.state_store import STATE_SCHEMA_VERSION, save_series_state

__all__ = [
    "CastMember",
    "CastPlan",
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
    "VoiceProfile",
    "build_default_cast_plan",
    "cast_plan_from_mapping",
    "delete_episode",
    "export_voices_for_litrpg_config",
    "find_bundle_by_cache_key",
    "generate_audition_script",
    "generate_litrpg_audio_episode",
    "generate_litrpg_chapter",
    "get_audio_path",
    "get_episode",
    "get_provider_api_key",
    "list_episodes",
    "list_regenerable_parts",
    "list_series",
    "load_cast_plan_json",
    "load_litrpg_task",
    "load_litrpg_settings",
    "load_series_state",
    "mark_episode_status",
    "next_episode_number",
    "run_litrpg_task",
    "save_series_state",
    "stable_cache_key",
    "validate_cast_plan",
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
