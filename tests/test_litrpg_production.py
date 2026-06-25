from podcastfy.litrpg.production import build_chapter_part_prompt
from podcastfy.litrpg.production import build_chapter_plan, build_chapter_review_prompt
from podcastfy.litrpg.production import build_part_review_prompt, default_cast_roles


def test_default_cast_has_large_audio_drama_ensemble():
    cast = default_cast_roles()

    assert len(cast) >= 15
    for role in ["NARRATOR", "HERO", "SYSTEM", "RIVAL", "MENTOR", "VILLAIN"]:
        assert role in cast


def test_chapter_plan_splits_into_parts_with_injected_beats():
    plan = build_chapter_plan(
        premise="A clerk enters a dungeon office.",
        chapter_number=3,
        injected_beats=["The cursed stapler must appear."],
    )

    assert plan.chapter_number == 3
    assert len(plan.parts) >= 5
    assert len(plan.cast_roles) >= 15
    assert "The cursed stapler must appear." in plan.parts[0].injected_beats
    assert any("SYSTEM" in part.required_roles for part in plan.parts)


def test_part_prompt_requires_roles_and_review_before_render():
    plan = build_chapter_plan(premise="A clerk enters a dungeon office.")
    part = plan.parts[1]

    prompt = build_chapter_part_prompt(chapter_plan=plan, part=part)
    review = build_part_review_prompt(
        part_script="<HERO>We move.</HERO>",
        required_roles=part.required_roles,
    )

    for role in part.required_roles:
        assert role in prompt
        assert role in review
    assert "Every required role must appear" in prompt
    assert "Return actionable fixes first" in review


def test_chapter_review_checks_cast_separation_and_injected_scenes():
    cast = default_cast_roles()

    prompt = build_chapter_review_prompt(
        part_scripts=["<NARRATOR>Start.</NARRATOR>", "<SYSTEM>Loot.</SYSTEM>"],
        cast_roles=cast,
    )

    assert "15 distinct roles" in prompt
    assert "SYSTEM/announcer" in prompt
    assert "missing injected scene" in prompt
