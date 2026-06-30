from podcastfy.litrpg.artifact_registry import ArtifactRecord
from podcastfy.litrpg.artifact_registry import ArtifactRegistry
from podcastfy.litrpg.artifact_registry import ArtifactRegistryState
from podcastfy.litrpg.artifact_registry import build_artifact_forge_prompt
from podcastfy.litrpg.artifact_registry import build_artifact_state_update_prompt
from podcastfy.litrpg.artifact_registry import merge_artifact_registry_delta
from podcastfy.litrpg.world_state import build_scene_brief
from podcastfy.litrpg.world_state import load_world_state
from podcastfy.litrpg.world_state import save_world_state


def _world_state():
    return {
        "series_id": "paper-cuts",
        "artifacts": {
            "stapler_bow": {
                "type": "weapon",
                "owner": "hero",
                "locked_name": "Redline Stapler",
                "aliases_forbidden": ["staple gun", "office bow"],
                "physical_signature": {"sound_fire": "chunk-thwip", "smell": "hot toner"},
                "behavioral_rules": ["misfires at unsigned paperwork"],
                "power_ceiling": {"cannot_do": ["kill bosses outright"]},
                "state": {"ammo": 4, "condition": "jammed", "location": "hero belt"},
            }
        },
    }


def test_artifact_registry_reads_and_writes_world_state_slice(tmp_path):
    save_world_state(tmp_path, "paper-cuts", _world_state())
    registry = ArtifactRegistry(tmp_path, "paper-cuts")

    state = registry.read()
    assert state.artifacts["stapler_bow"].locked_name == "Redline Stapler"
    assert state.artifacts["stapler_bow"].state["ammo"] == 4

    registry.upsert(
        "toner_knife",
        ArtifactRecord(
            artifact_id="toner_knife",
            locked_name="Toner Knife",
            aliases_forbidden=["printer dagger"],
            physical_signature={"appearance": "black blade that dusts paper"},
            power_ceiling={"cannot_do": ["cut through floor boss armor"]},
            state={"condition": "sharp", "location": "hero boot"},
        ),
    )
    stored = load_world_state(tmp_path, "paper-cuts")

    assert stored["artifacts"]["toner_knife"]["locked_name"] == "Toner Knife"
    assert stored["artifacts"]["toner_knife"]["state"]["condition"] == "sharp"


def test_artifact_registry_delta_updates_resources_and_scene_brief_contract():
    merged = merge_artifact_registry_delta(
        _world_state(),
        {
            "artifact_state_updates": {
                "stapler_bow": {"ammo": 2, "condition": "smoking", "location": "floor"}
            },
            "artifact_uses": {
                "stapler_bow": {"chapter_use": "pinned a construct", "resources_spent": "2 staples"}
            },
        },
    )
    brief = build_scene_brief(
        world_state=merged,
        chapter_contract={"active_artifacts": ["stapler_bow"]},
    )

    artifact = brief.to_dict()["active_artifacts"][0]
    assert artifact["locked_name"] == "Redline Stapler"
    assert artifact["state"]["ammo"] == 2
    assert artifact["state"]["condition"] == "smoking"
    assert "stapler_bow: forbidden alias staple gun" in brief.to_dict()["forbidden"]
    assert merged["metadata"]["artifact_uses"]["stapler_bow"]["resources_spent"] == "2 staples"


def test_artifact_forge_and_update_prompts_use_registry_schema():
    registry = ArtifactRegistryState(
        series_id="paper-cuts",
        artifacts={
            "stapler_bow": ArtifactRecord(
                artifact_id="stapler_bow",
                locked_name="Redline Stapler",
                state={"ammo": 4},
            )
        },
    )

    forge_prompt = build_artifact_forge_prompt(
        character={"id": "hero", "need": "survive paperwork"},
        beat_type="loot",
        world_tone="bureaucratic horror comedy",
        power_ceiling={"cannot_do": ["solve boss fight"]},
        forbidden_solutions=["teleport out"],
        active_mysteries={"sponsor": {"status": "DO_NOT_SPEND"}},
        existing_registry=registry,
    )
    update_prompt = build_artifact_state_update_prompt(
        final_script="<HERO>The Redline Stapler fired twice and started smoking.</HERO>",
        current_registry=registry,
        chapter_contract={"chapter": 4, "active_artifacts": ["stapler_bow"]},
    )

    assert '"artifact_id"' in forge_prompt
    assert "directly insertable into ArtifactRegistryState.artifacts" in forge_prompt
    assert "Redline Stapler" in forge_prompt
    assert "teleport out" in forge_prompt
    assert "artifact_state_updates" in update_prompt
    assert "Track every spent charge/ammo/resource" in update_prompt
    assert "Redline Stapler" in update_prompt
