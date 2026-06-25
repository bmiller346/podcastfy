"""Storage primitives for local LitRPG audio serials."""

from podcastfy.litrpg.bible import CharacterBibleEntry, StoryBible
from podcastfy.litrpg.bible import format_story_bible_summary, load_story_bible
from podcastfy.litrpg.bible import merge_story_bible_updates, save_story_bible
from podcastfy.litrpg.casting import CastMember, CastPlan, VoiceProfile
from podcastfy.litrpg.casting import build_default_cast_plan, cast_plan_from_mapping
from podcastfy.litrpg.casting import build_role_tts_instructions
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
from podcastfy.litrpg.mechanics import extract_mechanics_events, validate_mechanics
from podcastfy.litrpg.package_generator import build_series_package_prompt
from podcastfy.litrpg.package_generator import coerce_series_package
from podcastfy.litrpg.package_generator import extract_series_package_json
from podcastfy.litrpg.package_generator import format_series_package_summary
from podcastfy.litrpg.package_generator import generate_series_package
from podcastfy.litrpg.package_generator import save_generated_series_package
from podcastfy.litrpg.package_generator import validate_series_package
from podcastfy.litrpg.pipeline import generate_litrpg_audio_episode
from podcastfy.litrpg.part_reuse import locked_part_scripts_from_ready_parts
from podcastfy.litrpg.qa import build_chapter_qa, parse_part_qa_artifacts
from podcastfy.litrpg.models import CharacterState, EpisodeBundle, EpisodeConfig
from podcastfy.litrpg.models import QuestState, ScriptLine, SeriesState
from podcastfy.litrpg.renderer import RoleScriptRenderer
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.showrunner import NARRATIVE_ARC, WANDERING_EVENTS
from podcastfy.litrpg.showrunner import build_showrunner_payload
from podcastfy.litrpg.showrunner import format_showrunner_context
from podcastfy.litrpg.showrunner import roll_wandering_event
from podcastfy.litrpg.sfx import build_mix_plan, generate_sfx_candidate
from podcastfy.litrpg.sfx import load_asset_manifest, map_assets_for_cue
from podcastfy.litrpg.sfx import map_assets_for_cue_sheet, parse_cue_sheet
from podcastfy.litrpg.sfx_generation import build_local_sfx_prompt
from podcastfy.litrpg.sfx_generation import create_generation_request
from podcastfy.litrpg.sfx_generation import promote_generated_asset_request
from podcastfy.litrpg.sfx_generation import sfx_cache_path
from podcastfy.litrpg.sfx_manifest import add_or_promote_asset
from podcastfy.litrpg.sfx_manifest import load_asset_manifest_file
from podcastfy.litrpg.sfx_manifest import save_asset_manifest_file
from podcastfy.litrpg.sfx_manifest import scan_asset_directory
from podcastfy.litrpg.sfx_manifest import validate_asset_manifest
from podcastfy.litrpg.sfx_mix import normalize_mix_plan_defaults
from podcastfy.litrpg.sfx_mix import select_asset_candidates, validate_mix_plan
from podcastfy.litrpg.state_delta import apply_delta_to_state, extract_state_delta
from podcastfy.litrpg.state_store import load_series_state, next_episode_number
from podcastfy.litrpg.state_store import STATE_SCHEMA_VERSION, save_series_state

__all__ = [
    "CastMember",
    "CastPlan",
    "CharacterBibleEntry",
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
    "StoryBible",
    "NARRATIVE_ARC",
    "WANDERING_EVENTS",
    "VoiceProfile",
    "add_or_promote_asset",
    "apply_delta_to_state",
    "build_default_cast_plan",
    "build_chapter_qa",
    "build_local_sfx_prompt",
    "build_mix_plan",
    "build_role_tts_instructions",
    "build_series_package_prompt",
    "build_showrunner_payload",
    "cast_plan_from_mapping",
    "coerce_series_package",
    "create_generation_request",
    "delete_episode",
    "export_voices_for_litrpg_config",
    "extract_mechanics_events",
    "extract_state_delta",
    "extract_series_package_json",
    "find_bundle_by_cache_key",
    "format_story_bible_summary",
    "format_series_package_summary",
    "format_showrunner_context",
    "generate_audition_script",
    "generate_series_package",
    "generate_sfx_candidate",
    "generate_litrpg_audio_episode",
    "generate_litrpg_chapter",
    "get_audio_path",
    "get_episode",
    "get_provider_api_key",
    "list_episodes",
    "list_regenerable_parts",
    "list_series",
    "load_cast_plan_json",
    "load_asset_manifest",
    "load_asset_manifest_file",
    "load_litrpg_task",
    "load_litrpg_settings",
    "load_series_state",
    "load_story_bible",
    "locked_part_scripts_from_ready_parts",
    "mark_episode_status",
    "map_assets_for_cue",
    "map_assets_for_cue_sheet",
    "merge_story_bible_updates",
    "next_episode_number",
    "normalize_mix_plan_defaults",
    "parse_part_qa_artifacts",
    "parse_cue_sheet",
    "promote_generated_asset_request",
    "run_litrpg_task",
    "roll_wandering_event",
    "save_asset_manifest_file",
    "save_generated_series_package",
    "save_series_state",
    "save_story_bible",
    "scan_asset_directory",
    "sfx_cache_path",
    "stable_cache_key",
    "select_asset_candidates",
    "validate_asset_manifest",
    "validate_mechanics",
    "validate_mix_plan",
    "validate_series_package",
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
