import json

from podcastfy.litrpg.casting import (
    CastMember,
    CastPlan,
    VoiceProfile,
    build_default_cast_plan,
    cast_plan_from_mapping,
    export_voices_for_litrpg_config,
    generate_audition_script,
    load_cast_plan_json,
    validate_cast_plan,
)
from podcastfy.litrpg.prompts import ROLE_TAGS


def test_default_cast_plan_uses_role_tags_and_config_voices():
    plan = build_default_cast_plan()

    assert len(plan.cast_members) >= 15
    assert [member.role for member in plan.cast_members] == list(ROLE_TAGS)
    assert plan.member_by_role()["SYSTEM"].voice_profile.voice
    assert "announcement" in plan.member_by_role()["SYSTEM"].voice_profile.tags


def test_load_cast_plan_json_merges_override_with_defaults(tmp_path):
    path = tmp_path / "cast.json"
    path.write_text(
        json.dumps(
            {
                "provider_defaults": {
                    "provider": "openai",
                    "model": "gpt-4o-mini-tts",
                },
                "cast_members": [
                    {
                        "role": "hero",
                        "display_name": "Mara",
                        "description": "Office clerk turned dungeon runner.",
                        "archetype": "deadpan novice",
                        "voice_profile": {
                            "provider": "openai",
                            "voice": "cedar",
                            "instructions": "Dry, brave, slightly overwhelmed.",
                            "tags": ["lead", "grounded"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = load_cast_plan_json(path)

    assert len(plan.cast_members) == len(ROLE_TAGS)
    hero = plan.member_by_role()["HERO"]
    assert hero.display_name == "Mara"
    assert hero.voice_profile.voice == "cedar"
    assert hero.voice_profile.instructions == "Dry, brave, slightly overwhelmed."
    assert plan.member_by_role()["NARRATOR"].voice_profile.voice


def test_validate_reports_chapter_errors_and_warnings_without_crashing():
    plan = CastPlan(
        provider_defaults={"provider": "gemini", "model": "gpt-4o-mini-tts"},
        cast_members=[
            CastMember(
                role="NARRATOR",
                display_name="Narrator",
                description="",
                archetype="narrator",
                voice_profile=VoiceProfile(provider="openai", voice="alloy"),
            ),
            CastMember(
                role="NARRATOR",
                display_name="Narrator 2",
                description="",
                archetype="narrator",
                voice_profile=VoiceProfile(provider="openai", voice="echo"),
            ),
        ],
    )

    metadata = validate_cast_plan(plan, required_roles=["NARRATOR", "SYSTEM"])

    assert metadata["valid"] is False
    assert any("at least 15" in error for error in metadata["errors"])
    assert any("Duplicate role IDs" in error for error in metadata["errors"])
    assert any("SYSTEM is missing" in error for error in metadata["errors"])
    assert any("differs from plan provider" in warning for warning in metadata["warnings"])
    assert any("OpenAI model" in warning for warning in metadata["warnings"])


def test_validate_requires_voice_for_required_role():
    plan = build_default_cast_plan()
    plan.member_by_role()["SYSTEM"].voice_profile.voice = ""

    metadata = validate_cast_plan(plan, required_roles=["SYSTEM"])

    assert metadata["valid"] is False
    assert metadata["errors"] == ["Required role SYSTEM must define voice_profile.voice."]


def test_audition_script_generates_litrpg_role_lines():
    plan = build_default_cast_plan()

    scripts = generate_audition_script(plan, roles=["SYSTEM", "HERO"])

    assert scripts["SYSTEM"].startswith("<SYSTEM>SYSTEM ANNOUNCEMENT:")
    assert "New quest unlocked" in scripts["SYSTEM"]
    assert scripts["HERO"].startswith("<HERO>")
    assert "XP" in scripts["HERO"]


def test_export_voices_matches_renderer_config_shape():
    plan = build_default_cast_plan(provider_defaults={"provider": "openai"})
    hero = plan.member_by_role()["HERO"]
    hero.voice_profile.voice = "cedar"
    hero.voice_profile.instructions = "Grounded lead."
    hero.voice_profile.model = "gpt-4o-mini-tts"

    voices = export_voices_for_litrpg_config(plan)

    assert voices["HERO"]["voice"] == "cedar"
    assert voices["HERO"]["instructions"] == "Grounded lead."
    assert voices["HERO"]["model"] == "gpt-4o-mini-tts"
    assert "NARRATOR" in voices


def test_cast_plan_from_mapping_can_skip_default_merge():
    plan = cast_plan_from_mapping(
        {
            "provider_defaults": {"provider": "openai"},
            "cast_members": [
                {
                    "role": "SYSTEM",
                    "voice_profile": {"voice": "coral"},
                }
            ],
        },
        merge_defaults=False,
    )

    assert len(plan.cast_members) == 1
    assert plan.cast_members[0].role == "SYSTEM"
    assert plan.cast_members[0].voice_profile.provider == "openai"
