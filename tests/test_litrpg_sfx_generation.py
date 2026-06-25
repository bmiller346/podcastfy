import json
from pathlib import Path

from podcastfy.litrpg.sfx_generation import (
    GenerateSfxRequest,
    build_local_sfx_prompt,
    create_generation_request,
    promote_generated_asset_request,
    sfx_cache_path,
)


def test_prompt_builder_keeps_sfx_non_musical():
    prompt = build_local_sfx_prompt("sword clash", "sfx")

    assert "Short one-shot sound effect" in prompt
    assert "metal blade clash" in prompt
    assert "No music" in prompt
    assert "no vocals" in prompt
    assert "no speech" in prompt


def test_prompt_builder_allows_music_only_for_music_and_ambience_starts():
    bgm_prompt = build_local_sfx_prompt("boss battle", "bgm_start")
    ambience_prompt = build_local_sfx_prompt("dungeon", "ambience_start")

    assert "background music bed" in bgm_prompt
    assert "Instrumental only" in bgm_prompt
    assert "ambient environment" in ambience_prompt
    assert "no melody" in ambience_prompt


def test_cache_path_is_deterministic_and_normalized():
    first = sfx_cache_path(
        "Laser Stapler!!",
        provider="Local AudioGen",
        model="AudioGen Medium",
        duration_seconds=2.5,
        output_dir="cache/root",
    )
    second = sfx_cache_path(
        " laser_stapler ",
        provider="local-audiogen",
        model="audiogen_medium",
        duration_seconds=2.5,
        output_dir=Path("cache") / "root",
    )

    assert first == second
    assert first == "cache/root/local_audiogen__audiogen_medium__2p5s__laser_stapler.wav"


def test_create_generation_request_writes_sidecar(tmp_path):
    request_dir = tmp_path / "requests"
    output_dir = tmp_path / "audio"

    request = create_generation_request(
        "quest popup",
        cue_type="sfx",
        duration_seconds=1,
        output_dir=output_dir,
        request_dir=request_dir,
        write_sidecar=True,
    )

    sidecar_path = Path(request["request_path"])
    written = json.loads(sidecar_path.read_text(encoding="utf-8"))

    assert sidecar_path.parent == request_dir
    assert written == request
    assert request["tag"] == "quest popup"
    assert request["provider"] == "local_audiogen"
    assert request["model"] == "audiogen-medium"
    assert request["trusted"] is False
    assert request["status"] == "requested"
    assert request["cache_path"].endswith("__quest_popup.wav")


def test_generation_scaffold_has_no_paid_provider_references():
    module_text = Path("podcastfy/litrpg/sfx_generation.py").read_text(encoding="utf-8").lower()

    for forbidden in ("eleven", "openai", "gemini", "api_key", "http"):
        assert forbidden not in module_text


def test_promote_generated_asset_request_returns_untrusted_manifest_entry(tmp_path):
    generated_file = tmp_path / "assets" / "litrpg" / "generated" / "audio" / "spell_cast.wav"
    request = GenerateSfxRequest(
        tag="spell cast",
        cue_type="sfx",
        prompt=build_local_sfx_prompt("spell cast"),
        cache_path="assets/litrpg/generated/audio/spell_cast.wav",
    )

    entry = promote_generated_asset_request(
        request,
        generated_file,
        asset_root=tmp_path / "assets" / "litrpg",
    )

    assert entry["stem"] == "generated/audio/spell_cast"
    assert entry["tags"] == ["spell cast"]
    assert entry["cue_types"] == ["sfx"]
    assert entry["source"] == "local_ai_generated"
    assert entry["trusted"] is False
    assert entry["status"] == "generated_unreviewed"
