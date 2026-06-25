from podcastfy.litrpg.sfx import build_mix_plan, map_assets_for_cue, parse_cue_sheet
from podcastfy.litrpg.sfx_mix import (
    normalize_mix_plan_defaults,
    select_asset_candidates,
    validate_mix_plan,
)


def test_select_asset_candidates_prefers_trusted_assets_deterministically():
    mapping = {
        "semantic_tag": "battle",
        "cue_type": "bgm_start",
        "candidates": [
            "assets/litrpg/music/battle_placeholder.wav",
            "assets/litrpg/music/battle_final.wav",
            "assets/litrpg/sfx/battle_hit.wav",
        ],
        "metadata": {
            "assets": [
                {
                    "stem": "music/battle_placeholder",
                    "cue_types": ["bgm_start"],
                    "trusted": False,
                    "loopable": True,
                },
                {
                    "stem": "music/battle_final",
                    "cue_types": ["bgm_start"],
                    "trusted": True,
                    "loopable": True,
                },
                {
                    "stem": "sfx/battle_hit",
                    "cue_types": ["sfx"],
                    "trusted": True,
                    "loopable": False,
                },
            ]
        },
    }

    selected = select_asset_candidates(mapping, cue_type="bgm_start", semantic_tag="battle")

    assert selected == [
        "assets/litrpg/music/battle_final.wav",
        "assets/litrpg/music/battle_placeholder.wav",
    ]


def test_select_asset_candidates_preserves_stable_order_without_trust_metadata():
    mapping = map_assets_for_cue(parse_cue_sheet("[SFX: sword]").cues[0], asset_root="local")

    selected = select_asset_candidates(mapping, cue_type="sfx", max_candidates=3)

    assert selected == [
        "local/sfx/sword_clash.wav",
        "local/sfx/sword_clash.mp3",
        "local/sfx/sword_clash.ogg",
    ]


def test_normalize_mix_plan_defaults_fills_volume_ducking_and_pan_without_mutating_input():
    plan = {
        "layers": [
            {"layer_id": "music:cue-001", "type": "music", "ducking": {}},
            {"layer_id": "sfx:cue-002", "type": "sfx"},
        ]
    }

    normalized = normalize_mix_plan_defaults(plan)

    assert "volume" not in plan["layers"][0]
    assert normalized["layers"][0]["volume"] == "-12db"
    assert normalized["layers"][0]["ducking"]["ducks_under_dialogue"] is True
    assert normalized["layers"][0]["pan"] == "wide"
    assert normalized["layers"][1]["volume"] == "-9db"
    assert normalized["layers"][1]["ducking"]["ducks_under_dialogue"] is False
    assert normalized["layers"][1]["pan"] == "center"


def test_validate_mix_plan_reports_missing_assets_on_non_control_layers():
    plan = {
        "layers": [
            {"layer_id": "dialogue", "type": "dialogue"},
            {"layer_id": "sfx:cue-001", "type": "sfx", "asset_candidates": []},
        ],
        "automations": [],
        "issues": [],
    }

    validation = validate_mix_plan(plan)

    assert validation["ready"] is False
    assert validation["issues"] == ["sfx:cue-001: missing asset candidates for sfx cue"]


def test_validate_mix_plan_reports_untrusted_assets_in_final_mode():
    mapping = {
        "semantic_tag": "ui",
        "cue_type": "sfx",
        "candidates": ["assets/litrpg/sfx/ui_chime.wav"],
        "metadata": {"assets": [{"stem": "sfx/ui_chime", "trusted": False}]},
    }
    plan = {
        "layers": [
            {
                "layer_id": "sfx:cue-001",
                "type": "sfx",
                "semantic_tag": "ui",
                "asset_candidates": ["assets/litrpg/sfx/ui_chime.wav"],
                "volume": "-12db",
            }
        ],
        "automations": [],
        "issues": [],
    }

    validation = validate_mix_plan(plan, asset_mappings=[mapping], final_mode=True)

    assert validation["ready"] is False
    assert validation["issues"] == [
        "sfx:cue-001: untrusted asset in final mode: assets/litrpg/sfx/ui_chime.wav"
    ]


def test_validate_mix_plan_reports_stop_cues_without_targets():
    plan = build_mix_plan(parse_cue_sheet("[BGM_STOP]\n[AMBIENCE_STOP]"))

    validation = validate_mix_plan(plan)

    assert any("BGM_STOP without active BGM_START" in issue for issue in validation["issues"])
    assert "stop:cue-001: stop cue without target layer" in validation["issues"]
    assert "stop:cue-002: stop cue without target layer" in validation["issues"]


def test_validate_mix_plan_reports_non_loopable_assets_on_beds():
    mapping = {
        "semantic_tag": "battle",
        "cue_type": "bgm_start",
        "candidates": ["assets/litrpg/music/battle_sting.wav"],
        "metadata": {"assets": [{"stem": "music/battle_sting", "trusted": True, "loopable": False}]},
    }
    plan = {
        "layers": [
            {
                "layer_id": "music:cue-001",
                "type": "music",
                "asset_candidates": ["assets/litrpg/music/battle_sting.wav"],
            }
        ],
        "automations": [],
        "issues": [],
    }

    validation = validate_mix_plan(plan, asset_mappings=[mapping])

    assert validation["issues"] == [
        "music:cue-001: non-loopable asset used as music bed: assets/litrpg/music/battle_sting.wav"
    ]


def test_validate_mix_plan_warns_for_loud_sfx_over_dialogue_risk():
    plan = {
        "layers": [
            {
                "layer_id": "sfx:cue-001",
                "type": "sfx",
                "asset_candidates": ["assets/litrpg/sfx/explosion.wav"],
                "volume": "-3db",
                "ducking": {"ducks_under_dialogue": False},
                "asset_metadata": {"intensity": 9},
            }
        ],
        "automations": [],
        "issues": [],
    }

    validation = validate_mix_plan(plan)

    assert validation["ready"] is True
    assert validation["warnings"] == ["sfx:cue-001: loud SFX over dialogue risk"]


def test_validate_mix_plan_does_not_warn_for_ducked_quiet_sfx():
    plan = {
        "layers": [
            {
                "layer_id": "sfx:cue-001",
                "type": "sfx",
                "asset_candidates": ["assets/litrpg/sfx/menu_tick.wav"],
                "volume": "-15db",
                "ducking": {"ducks_under_dialogue": True},
                "asset_metadata": {"intensity": 2},
            }
        ],
        "automations": [],
        "issues": [],
    }

    validation = validate_mix_plan(plan)

    assert validation["warnings"] == []


def test_validate_mix_plan_warns_for_missing_ducking_on_beds():
    plan = {
        "layers": [
            {
                "layer_id": "ambience:cue-001",
                "type": "ambience",
                "asset_candidates": ["assets/litrpg/ambience/dungeon_room.wav"],
                "ducking": {"ducks_under_dialogue": False},
            }
        ],
        "automations": [],
        "issues": [],
    }

    validation = validate_mix_plan(plan)

    assert validation["ready"] is True
    assert validation["warnings"] == ["ambience:cue-001: missing ducking on ambience bed"]
