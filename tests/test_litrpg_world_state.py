import json

from podcastfy.litrpg.world_state import SensoryHookLibrary
from podcastfy.litrpg.world_state import WorldStateManager
from podcastfy.litrpg.world_state import build_artifact_forge_prompt
from podcastfy.litrpg.world_state import build_scene_brief
from podcastfy.litrpg.world_state import build_scene_brief_prompt
from podcastfy.litrpg.world_state import build_world_state_update_prompt
from podcastfy.litrpg.world_state import load_world_state
from podcastfy.litrpg.world_state import save_world_state


def _world_state():
    return {
        "series_id": "paper-cuts",
        "characters": {
            "hero": {
                "appearance": ["crawler bracelet on left wrist", "limps from copier mimic bite"],
                "voice": "flat affect under pressure",
                "signature_behaviors": ["checks exits first"],
                "emotional_tells": {"fear": "goes still", "anger": "gets quieter"},
                "last_known_state": {
                    "injuries": ["cracked rib"],
                    "equipment": ["jammed stapler shield"],
                    "emotional_arc": "competence hiding panic",
                },
            }
        },
        "locations": {
            "floor_4_market": {
                "name": "Floor 4 Market",
                "sensory": {
                    "visual": "amber moss light, no clean sightlines",
                    "audio": "crowd noise and distant grinding",
                    "smell": "copper and spoiled mushroom",
                    "spatial": "ceiling 40ft, three visible exits",
                },
                "threat_geometry": "ambush-friendly, poor retreat east",
            }
        },
        "active_mysteries": {
            "system_true_purpose": {"status": "DO_NOT_SPEND"}
        },
        "established_rules": ["System notifications lag two seconds"],
        "sensory_hooks": {
            "floor_4_market": ["sweet copper means tier-2 flesh constructs"]
        },
        "artifacts": {
            "stapler_bow": {
                "type": "weapon",
                "owner": "hero",
                "acquired": "chapter 1",
                "locked_name": "Redline Stapler",
                "aliases_forbidden": ["staple gun", "office bow"],
                "physical_signature": {
                    "appearance": "red enamel jaw with brass teeth",
                    "weight": "too heavy for its size",
                    "sound_fire": "chunk-thwip",
                    "sound_load": "angry spring rattle",
                    "smell": "hot toner",
                    "recoil": "wrist-snapping bite",
                    "primary_sense": "sound",
                    "behavioral_quirk": "chatters when pointed at forms",
                },
                "behavioral_rules": ["misfires at unsigned paperwork"],
                "power_ceiling": {
                    "can_do": ["pin small constructs"],
                    "cannot_do": ["kill bosses outright"],
                    "narrative_cost": "jams under panic",
                    "DO_NOT_ESCALATE_BEYOND": "single-target control",
                },
                "state": {
                    "condition": "jammed but usable",
                    "ammo": 7,
                    "charges": None,
                    "location": "hero belt",
                    "separated_from_owner": False,
                },
            }
        },
    }


def test_scene_brief_renders_spatial_sensory_and_forbidden_contract():
    brief = build_scene_brief(
        world_state=_world_state(),
        chapter_contract={
            "location": "floor_4_market",
            "scene_type": "apex",
            "character_focus": ["hero"],
        },
        prior_chapter_tail="The market lights went out.",
    )

    payload = brief.to_dict()
    assert "ceiling 40ft" in payload["spatial_anchor"]
    assert payload["sensory_priority"][0] in {"visual", "audio", "smell"}
    assert payload["active_characters"][0]["id"] == "hero"
    assert "system_true_purpose: DO_NOT_SPEND" in payload["forbidden"]
    assert "sweet copper" in " ".join(payload["sensory_hooks"])
    assert "time feels fragmented" in " ".join(payload["sensory_hooks"])


def test_scene_brief_includes_active_artifact_contract():
    brief = build_scene_brief(
        world_state=_world_state(),
        chapter_contract={
            "location": "floor_4_market",
            "active_artifacts": ["stapler_bow"],
            "character_focus": ["hero"],
        },
    )

    payload = brief.to_dict()
    artifact = payload["active_artifacts"][0]
    assert artifact["locked_name"] == "Redline Stapler"
    assert artifact["physical_signature"]["sound_fire"] == "chunk-thwip"
    assert "staple gun" in artifact["aliases_forbidden"]
    assert artifact["state"]["ammo"] == 7
    assert artifact["state"]["condition"] == "jammed but usable"
    assert "Redline Stapler" in " ".join(payload["sensory_hooks"])


def test_scene_brief_prompt_and_world_update_prompt_are_schema_focused():
    scene_prompt = build_scene_brief_prompt(
        world_state=_world_state(),
        chapter_contract={"location": "floor_4_market", "scene_type": "social"},
    )
    update_prompt = build_world_state_update_prompt(
        final_script="<NARRATOR>The market smells like copper.</NARRATOR>",
        current_world_state=_world_state(),
        chapter_contract={"chapter": 4},
    )

    assert "scene director, not a prose writer" in scene_prompt
    assert '"spatial_anchor"' in scene_prompt
    assert "sensory_hooks" in scene_prompt
    assert "Output ONLY the world state delta" in update_prompt
    assert "new_sensory_hooks" in update_prompt
    assert "Do not summarize" in update_prompt


def test_sensory_hook_library_selects_location_character_and_beat_mode():
    hooks = SensoryHookLibrary(_world_state()).get_hooks(
        location_id="floor_4_market",
        character_ids=["hero"],
        beat_type="disaster",
    )

    assert "sweet copper means tier-2 flesh constructs" in hooks["established_hooks"]
    assert "crawler bracelet" in hooks["character_signatures"][0]
    assert hooks["beat_sensory_mode"]["focus"] == "narrow"


def test_world_state_storage_round_trips(tmp_path):
    path = save_world_state(tmp_path, "paper-cuts", _world_state())
    loaded = load_world_state(tmp_path, "paper-cuts")

    assert path.name == "world_state.json"
    assert loaded["characters"]["hero"]["voice"] == "flat affect under pressure"
    assert json.loads(path.read_text(encoding="utf-8"))["series_id"] == "paper-cuts"


def test_world_state_manager_read_write_update_delta_and_lookup(tmp_path):
    manager = WorldStateManager(tmp_path, "paper-cuts")
    manager.write(_world_state())
    updated = manager.update_delta(
        {
            "artifact_state_updates": {
                "stapler_bow": {"ammo": 3, "condition": "smoking"}
            },
            "system_items": {
                "coupon": {
                    "display_name": "Mandatory Coupon",
                    "system_description": "A reward.",
                    "actual_behavior": "Expires before use.",
                    "irony_flag": True,
                    "carl_commentary": "That tracks.",
                }
            },
        }
    )

    assert updated["artifacts"]["stapler_bow"]["state"]["ammo"] == 3
    assert manager.get_artifact("stapler_bow")["state"]["condition"] == "smoking"
    assert manager.get_character("hero")["voice"] == "flat affect under pressure"
    assert manager.read()["system_items"]["coupon"]["display_name"] == "Mandatory Coupon"


def test_validate_consistency_catches_duplicate_sensory_token_across_artifacts(tmp_path):
    manager = WorldStateManager(tmp_path, "paper-cuts")
    state = _world_state()
    state["artifacts"]["toner_knife"] = {
        "locked_name": "Toner Knife",
        "physical_signature": {"sound_fire": "chunk-thwip"},
    }
    manager.write(state)

    result = manager.validate_consistency()

    assert result["passed"] is False
    assert result["violations"][0]["type"] == "duplicate_sensory_token"
    assert "artifact:stapler_bow" in result["violations"][0]["owners"]


def test_validate_consistency_allows_shared_signature_group(tmp_path):
    manager = WorldStateManager(tmp_path, "paper-cuts")
    state = _world_state()
    state["artifacts"]["stapler_bow"]["shared_signature_group"] = "office-weapons"
    state["artifacts"]["toner_knife"] = {
        "locked_name": "Toner Knife",
        "shared_signature_group": "office-weapons",
        "physical_signature": {"sound_fire": "chunk-thwip"},
    }
    manager.write(state)

    assert manager.validate_consistency()["passed"] is True


def test_artifact_forge_prompt_contains_constraints():
    prompt = build_artifact_forge_prompt(
        character={"id": "hero", "need": "survive paperwork"},
        beat_type="loot",
        world_tone="bureaucratic horror comedy",
        power_ceiling={"cannot_do": ["solve boss fight"]},
        forbidden_solutions=["teleport out", "identify sponsor"],
        active_mysteries={"sponsor": {"status": "DO_NOT_SPEND"}},
    )

    assert '"locked_name"' in prompt
    assert "forbidden solutions" in prompt.lower()
    assert "teleport out" in prompt
    assert "active mysteries" in prompt.lower()
    assert "sponsor" in prompt
