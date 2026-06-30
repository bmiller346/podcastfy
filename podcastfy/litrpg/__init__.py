"""Storage primitives for local LitRPG audio serials."""

from podcastfy.litrpg.artifact_registry import ArtifactRecord, ArtifactRegistry
from podcastfy.litrpg.artifact_registry import ArtifactRegistryState
from podcastfy.litrpg.artifact_registry import build_artifact_forge_prompt
from podcastfy.litrpg.artifact_registry import build_artifact_state_update_prompt
from podcastfy.litrpg.artifact_registry import merge_artifact_registry_delta
from podcastfy.litrpg.bible import CharacterBibleEntry, StoryBible
from podcastfy.litrpg.bible import format_story_bible_summary, load_story_bible
from podcastfy.litrpg.bible import merge_story_bible_updates, save_story_bible
from podcastfy.litrpg.casting import CastMember, CastPlan, VoiceProfile
from podcastfy.litrpg.casting import build_default_cast_plan, cast_plan_from_mapping
from podcastfy.litrpg.casting import build_role_tts_instructions
from podcastfy.litrpg.casting import export_voices_for_litrpg_config
from podcastfy.litrpg.casting import generate_audition_script, load_cast_plan_json
from podcastfy.litrpg.casting import validate_cast_plan
from podcastfy.litrpg.character_arc import CharacterArcEngine
from podcastfy.litrpg.character_arc import build_arc_state_update_prompt
from podcastfy.litrpg.character_arc import build_character_arc_context
from podcastfy.litrpg.character_arc import format_character_arc_context
from podcastfy.litrpg.character_arc import merge_arc_state_delta
from podcastfy.litrpg.chapter import generate_litrpg_chapter
from podcastfy.litrpg.continuity import ContinuityLedger, EmotionalArcRegistry
from podcastfy.litrpg.continuity import WorldRegister, format_chapter_memory_context
from podcastfy.litrpg.continuity import format_continuity_context
from podcastfy.litrpg.continuity import format_emotional_arc_context
from podcastfy.litrpg.continuity import format_world_register_context
from podcastfy.litrpg.continuity import load_continuity_ledger
from podcastfy.litrpg.continuity import load_emotional_arcs, load_world_register
from podcastfy.litrpg.continuity import merge_continuity_ledgers
from podcastfy.litrpg.continuity import merge_world_registers
from podcastfy.litrpg.continuity import save_continuity_ledger
from podcastfy.litrpg.continuity import save_emotional_arcs, save_world_register
from podcastfy.litrpg.continuity import upsert_emotional_arc
from podcastfy.litrpg.conspiracy_engine import ConspiracyEngine
from podcastfy.litrpg.conspiracy_engine import build_conspiracy_chapter_context
from podcastfy.litrpg.conspiracy_engine import load_conspiracy_engine, save_conspiracy_engine
from podcastfy.litrpg.effect_log import EffectLogEntry
from podcastfy.litrpg.effect_log import append_effect_log_entry, build_effect_log_entry
from podcastfy.litrpg.effect_log import effect_log_path, find_committed_effect
from podcastfy.litrpg.effect_log import make_idempotency_key, read_effect_log
from podcastfy.litrpg.effect_log import should_skip_effect
from podcastfy.litrpg.episode_store import EpisodeStore, find_bundle_by_cache_key
from podcastfy.litrpg.episode_store import stable_cache_key
from podcastfy.litrpg.foreshadowing import ForeshadowEntry, ForeshadowLedger
from podcastfy.litrpg.foreshadowing import add_plants, compute_ready_to_pay
from podcastfy.litrpg.foreshadowing import format_foreshadow_context
from podcastfy.litrpg.foreshadowing import load_foreshadow_ledger, mark_paid
from podcastfy.litrpg.foreshadowing import save_foreshadow_ledger
from podcastfy.litrpg.agent_state import QueueItem
from podcastfy.litrpg.agent_state import add_queue_item, agent_state_path
from podcastfy.litrpg.agent_state import complete_queue_item, dedupe_queue
from podcastfy.litrpg.agent_state import load_agent_state
from podcastfy.litrpg.agent_state import record_next_chapter_action
from podcastfy.litrpg.agent_state import record_quarantine_blocker, save_agent_state
from podcastfy.litrpg.handoff import generate_book_handoff
from podcastfy.litrpg.harness import HarnessDecision, HarnessStageGate
from podcastfy.litrpg.harness import check_harness_gate, default_harness_config
from podcastfy.litrpg.harness import estimate_stage_cost, load_harness_config
from podcastfy.litrpg.hooks import HookContract, MysteryLock
from podcastfy.litrpg.hooks import build_hook_context, build_hook_contract
from podcastfy.litrpg.hooks import format_ending_hook_obligations
from podcastfy.litrpg.hooks import format_mystery_lock
from podcastfy.litrpg.hooks import format_opening_hook_obligation
from podcastfy.litrpg.hooks import hook_type_for_contract
from podcastfy.litrpg.library import delete_episode, get_audio_path, get_episode
from podcastfy.litrpg.library import list_episodes, list_regenerable_parts, list_series
from podcastfy.litrpg.library import mark_episode_status
from podcastfy.litrpg.llm import GeminiGenerator, IntentRoutingGemini
from podcastfy.litrpg.llm import IntentRoutingOpenAI, OllamaGenerator, OpenAIResponsesGenerator
from podcastfy.litrpg.llm import StageRouterLLM, StageRouting
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
from podcastfy.litrpg.premise_intake import PremiseIntakeResult
from podcastfy.litrpg.premise_intake import build_premise_intake_prompt
from podcastfy.litrpg.premise_intake import extract_premise_intake_json
from podcastfy.litrpg.premise_intake import run_premise_intake
from podcastfy.litrpg.premise_intake import save_premise_intake_payload
from podcastfy.litrpg.promise_forge import build_hook_brief_prompt
from podcastfy.litrpg.promise_forge import build_promise_forge_prompt
from podcastfy.litrpg.promise_forge import format_promise_forge_context
from podcastfy.litrpg.promise_forge import normalize_promise_forge
from podcastfy.litrpg.promise_forge import validate_promise_forge_specificity
from podcastfy.litrpg.prompts import build_series_anchor_block
from podcastfy.litrpg.quarantine import QuarantineRecord
from podcastfy.litrpg.quarantine import build_rewrite_instruction
from podcastfy.litrpg.quarantine import chapter_quarantine_dir
from podcastfy.litrpg.quarantine import next_quarantine_attempt_path
from podcastfy.litrpg.quarantine import quarantine_record_to_dict
from podcastfy.litrpg.quarantine import write_quarantine_record
from podcastfy.litrpg.qa import build_chapter_qa, parse_part_qa_artifacts
from podcastfy.litrpg.models import CharacterState, EpisodeBundle, EpisodeConfig
from podcastfy.litrpg.models import ChapterContract
from podcastfy.litrpg.models import QuestState, SchemaValidationError, ScriptLine
from podcastfy.litrpg.models import SeriesArcBeat, SeriesState, VoiceConstraint
from podcastfy.litrpg.models import WorldRegisterEntry
from podcastfy.litrpg.renderer import RoleScriptRenderer
from podcastfy.litrpg.rhythm import build_prose_rhythm_prompt
from podcastfy.litrpg.rhythm import build_reader_proxy_prompt
from podcastfy.litrpg.rhythm import classify_target_rhythm
from podcastfy.litrpg.rhythm import parse_verdict_and_scores
from podcastfy.litrpg.scarcity import ScarcityDecision, ScarcityItem, ScarcityRegistry
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.series_architect import BookPlan, ChapterBeat
from podcastfy.litrpg.series_architect import ChapterOutlineEntry, SeriesArchitect
from podcastfy.litrpg.series_architect import SeriesShape, bootstrap_series
from podcastfy.litrpg.series_architect import build_series_arc_prompt
from podcastfy.litrpg.series_architect import format_chapter_contract_context
from podcastfy.litrpg.series_architect import generate_tempo_map
from podcastfy.litrpg.series_architect import load_series_shape, save_series_shape
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
from podcastfy.litrpg.voice_cards import VoiceCard, VoiceCardDeck
from podcastfy.litrpg.voice_cards import format_voice_card_context
from podcastfy.litrpg.voice_cards import load_voice_cards, merge_voice_cards
from podcastfy.litrpg.voice_cards import save_voice_cards
from podcastfy.litrpg.world_state import BEAT_SENSORY_MAP, SceneBrief
from podcastfy.litrpg.world_state import SensoryHookLibrary
from podcastfy.litrpg.world_state import WorldStateManager
from podcastfy.litrpg.world_state import build_scene_brief
from podcastfy.litrpg.world_state import build_scene_brief_prompt
from podcastfy.litrpg.world_state import build_world_state_update_prompt
from podcastfy.litrpg.world_state import format_scene_brief_context
from podcastfy.litrpg.world_state import load_world_state, save_world_state
from podcastfy.litrpg.world_state import merge_world_state_delta
from podcastfy.litrpg.world_state import validate_world_state_consistency

__all__ = [
    "CastMember",
    "CastPlan",
    "CharacterBibleEntry",
    "ArtifactRecord",
    "ArtifactRegistry",
    "ArtifactRegistryState",
    "BookPlan",
    "ChapterBeat",
    "ChapterContract",
    "ChapterOutlineEntry",
    "CharacterState",
    "CharacterArcEngine",
    "ConspiracyEngine",
    "ContinuityLedger",
    "EffectLogEntry",
    "EmotionalArcRegistry",
    "EpisodeBundle",
    "EpisodeConfig",
    "EpisodeStore",
    "ForeshadowEntry",
    "ForeshadowLedger",
    "HookContract",
    "MysteryLock",
    "OpenAIResponsesGenerator",
    "OllamaGenerator",
    "PremiseIntakeResult",
    "QuestState",
    "QueueItem",
    "QuarantineRecord",
    "RoleScriptRenderer",
    "ScriptLine",
    "SchemaValidationError",
    "ScarcityDecision",
    "ScarcityItem",
    "ScarcityRegistry",
    "SceneBrief",
    "SeriesArcBeat",
    "SeriesState",
    "SeriesArchitect",
    "SeriesShape",
    "STATE_SCHEMA_VERSION",
    "StageRouterLLM",
    "StageRouting",
    "StoryBible",
    "NARRATIVE_ARC",
    "WANDERING_EVENTS",
    "VoiceCard",
    "VoiceCardDeck",
    "VoiceConstraint",
    "VoiceProfile",
    "BEAT_SENSORY_MAP",
    "SensoryHookLibrary",
    "WorldStateManager",
    "WorldRegister",
    "WorldRegisterEntry",
    "add_or_promote_asset",
    "add_queue_item",
    "add_plants",
    "agent_state_path",
    "apply_delta_to_state",
    "append_effect_log_entry",
    "build_prose_rhythm_prompt",
    "build_default_cast_plan",
    "build_chapter_qa",
    "build_arc_state_update_prompt",
    "build_character_arc_context",
    "build_conspiracy_chapter_context",
    "build_hook_context",
    "build_hook_brief_prompt",
    "build_hook_contract",
    "build_effect_log_entry",
    "build_local_sfx_prompt",
    "build_mix_plan",
    "build_premise_intake_prompt",
    "build_promise_forge_prompt",
    "build_reader_proxy_prompt",
    "build_role_tts_instructions",
    "build_artifact_forge_prompt",
    "build_artifact_state_update_prompt",
    "build_scene_brief",
    "build_scene_brief_prompt",
    "build_series_package_prompt",
    "build_series_anchor_block",
    "build_series_arc_prompt",
    "build_rewrite_instruction",
    "build_showrunner_payload",
    "build_world_state_update_prompt",
    "bootstrap_series",
    "cast_plan_from_mapping",
    "check_harness_gate",
    "classify_target_rhythm",
    "chapter_quarantine_dir",
    "coerce_series_package",
    "complete_queue_item",
    "compute_ready_to_pay",
    "create_generation_request",
    "delete_episode",
    "dedupe_queue",
    "default_harness_config",
    "effect_log_path",
    "estimate_stage_cost",
    "export_voices_for_litrpg_config",
    "extract_mechanics_events",
    "extract_premise_intake_json",
    "extract_state_delta",
    "extract_series_package_json",
    "find_bundle_by_cache_key",
    "find_committed_effect",
    "format_story_bible_summary",
    "format_chapter_memory_context",
    "format_character_arc_context",
    "format_series_package_summary",
    "format_chapter_contract_context",
    "format_continuity_context",
    "format_emotional_arc_context",
    "format_ending_hook_obligations",
    "format_foreshadow_context",
    "format_mystery_lock",
    "format_opening_hook_obligation",
    "format_promise_forge_context",
    "format_showrunner_context",
    "format_scene_brief_context",
    "format_voice_card_context",
    "format_world_register_context",
    "generate_tempo_map",
    "generate_audition_script",
    "generate_series_package",
    "generate_sfx_candidate",
    "generate_litrpg_audio_episode",
    "generate_litrpg_chapter",
    "generate_book_handoff",
    "GeminiGenerator",
    "HarnessDecision",
    "HarnessStageGate",
    "IntentRoutingGemini",
    "IntentRoutingOpenAI",
    "get_audio_path",
    "get_episode",
    "get_provider_api_key",
    "hook_type_for_contract",
    "list_episodes",
    "list_regenerable_parts",
    "list_series",
    "load_agent_state",
    "load_cast_plan_json",
    "load_asset_manifest",
    "load_asset_manifest_file",
    "load_conspiracy_engine",
    "load_continuity_ledger",
    "load_emotional_arcs",
    "load_foreshadow_ledger",
    "load_harness_config",
    "load_litrpg_task",
    "load_litrpg_settings",
    "load_series_state",
    "load_series_shape",
    "load_story_bible",
    "load_voice_cards",
    "load_world_register",
    "load_world_state",
    "merge_world_state_delta",
    "locked_part_scripts_from_ready_parts",
    "mark_episode_status",
    "mark_paid",
    "map_assets_for_cue",
    "map_assets_for_cue_sheet",
    "make_idempotency_key",
    "merge_story_bible_updates",
    "merge_arc_state_delta",
    "merge_artifact_registry_delta",
    "merge_continuity_ledgers",
    "merge_voice_cards",
    "merge_world_registers",
    "next_episode_number",
    "next_quarantine_attempt_path",
    "normalize_mix_plan_defaults",
    "normalize_promise_forge",
    "parse_part_qa_artifacts",
    "parse_cue_sheet",
    "parse_verdict_and_scores",
    "promote_generated_asset_request",
    "quarantine_record_to_dict",
    "read_effect_log",
    "record_next_chapter_action",
    "record_quarantine_blocker",
    "run_litrpg_task",
    "run_premise_intake",
    "roll_wandering_event",
    "save_asset_manifest_file",
    "save_agent_state",
    "save_conspiracy_engine",
    "save_continuity_ledger",
    "save_emotional_arcs",
    "save_foreshadow_ledger",
    "save_generated_series_package",
    "save_premise_intake_payload",
    "save_series_state",
    "save_series_shape",
    "save_story_bible",
    "save_voice_cards",
    "save_world_register",
    "save_world_state",
    "validate_world_state_consistency",
    "scan_asset_directory",
    "should_skip_effect",
    "sfx_cache_path",
    "stable_cache_key",
    "select_asset_candidates",
    "upsert_emotional_arc",
    "validate_asset_manifest",
    "validate_mechanics",
    "validate_promise_forge_specificity",
    "validate_mix_plan",
    "validate_series_package",
    "validate_cast_plan",
    "write_quarantine_record",
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
