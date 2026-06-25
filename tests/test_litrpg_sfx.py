from podcastfy.litrpg.sfx import (
    build_mix_plan,
    map_assets_for_cue,
    map_assets_for_cue_sheet,
    parse_cue_sheet,
)


def test_parse_cue_sheet_extracts_ordered_cues_and_cleans_script():
    script = """[BGM_START: battle volume=-9db duck=true]
<NARRATOR>The arena doors opened.</NARRATOR>
<SYSTEM>[SFX: ui quest pan=left]QUEST UPDATED.</SYSTEM>
[AMBIENCE_START: dungeon pan=wide]
<HERO>I hate bonus objectives.</HERO>
[BGM_STOP]"""

    cue_sheet = parse_cue_sheet(script)

    assert [cue.cue_type for cue in cue_sheet.cues] == [
        "bgm_start",
        "sfx",
        "ambience_start",
        "bgm_stop",
    ]
    assert cue_sheet.cues[0].tag == "battle"
    assert cue_sheet.cues[1].tag == "ui quest"
    assert "[BGM_START" not in cue_sheet.clean_script
    assert "[SFX:" not in cue_sheet.clean_script
    assert "<SYSTEM>QUEST UPDATED.</SYSTEM>" in cue_sheet.clean_script
    assert cue_sheet.metadata["cue_count"] == 4
    assert cue_sheet.metadata["has_music"] is True
    assert cue_sheet.metadata["has_sfx"] is True


def test_parse_cue_sheet_modifiers_parse_basic_value_types():
    cue_sheet = parse_cue_sheet(
        '<HERO>[SFX: sword clash pan=left volume=-6db duck=true repeats=2 gain=0.5]Hit.</HERO>'
    )

    cue = cue_sheet.cues[0]

    assert cue.tag == "sword clash"
    assert cue.modifiers == {
        "pan": "left",
        "volume": "-6db",
        "duck": True,
        "repeats": 2,
        "gain": 0.5,
    }
    assert cue.line_number == 1
    assert cue.raw_tag.startswith("[SFX:")


def test_asset_mapping_uses_curated_candidates_without_requiring_files():
    cue_sheet = parse_cue_sheet("[SFX: sword clash]<HERO>Parry.</HERO>")

    mapping = map_assets_for_cue(cue_sheet.cues[0], asset_root="local/assets")

    assert mapping.semantic_tag == "sword clash"
    assert mapping.cue_type == "sfx"
    assert mapping.metadata["matched_library"] is True
    assert "local/assets/sfx/sword_clash.wav" in mapping.candidates
    assert "local/assets/sfx/blade_unsheathe.mp3" in mapping.candidates


def test_asset_mapping_falls_back_to_layer_slug_for_unknown_tags():
    cue_sheet = parse_cue_sheet("[AMBIENCE_START: crystal elevator]")

    mapping = map_assets_for_cue_sheet(cue_sheet, asset_root="local/assets")[0]

    assert mapping.metadata["matched_library"] is False
    assert mapping.candidates[:3] == [
        "local/assets/ambience/crystal_elevator.wav",
        "local/assets/ambience/crystal_elevator.mp3",
        "local/assets/ambience/crystal_elevator.ogg",
    ]


def test_asset_mapping_treats_stop_cues_as_control_metadata():
    cue_sheet = parse_cue_sheet("[BGM_STOP]")

    mapping = map_assets_for_cue_sheet(cue_sheet)[0]

    assert mapping.candidates == []
    assert mapping.metadata["control_cue"] is True


def test_mix_plan_describes_layers_ducking_panning_eq_and_timing_anchors():
    cue_sheet = parse_cue_sheet(
        """[BGM_START: boss volume=-10db]
<NARRATOR>The boss health bar arrived.</NARRATOR>
[SFX: spell pan=right duck=true]
[AMBIENCE_START: dungeon volume=-20db]
<SYSTEM>PHASE TWO.</SYSTEM>
[AMBIENCE_STOP]
[BGM_STOP]"""
    )

    plan = build_mix_plan(cue_sheet)

    assert plan["version"] == 1
    assert plan["layers"][0]["type"] == "dialogue"
    music = next(layer for layer in plan["layers"] if layer["type"] == "music")
    sfx = next(layer for layer in plan["layers"] if layer["type"] == "sfx")
    ambience = next(layer for layer in plan["layers"] if layer["type"] == "ambience")

    assert music["semantic_tag"] == "boss"
    assert music["volume"] == "-10db"
    assert music["ducking"]["ducks_under_dialogue"] is True
    assert "leave center space" in music["eq_intent"]
    assert sfx["pan"] == "right"
    assert sfx["ducking"]["ducks_under_dialogue"] is True
    assert sfx["timing"]["anchor"]["cue_id"] == "cue-002"
    assert ambience["volume"] == "-20db"
    assert ambience["timing"]["start_anchor"]["line_number"] == 4
    assert [automation["type"] for automation in plan["automations"]] == [
        "ambience_stop",
        "music_stop",
    ]
    assert plan["metadata"]["cue_count"] == 5
