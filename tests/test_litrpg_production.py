from podcastfy.litrpg.production import build_chapter_part_prompt
from podcastfy.litrpg.production import build_chapter_plan, build_chapter_review_prompt
from podcastfy.litrpg.production import build_description_audit_prompt
from podcastfy.litrpg.production import build_director_pass_prompt
from podcastfy.litrpg.production import build_mechanics_audit_prompt
from podcastfy.litrpg.production import build_part_review_prompt, default_cast_roles
from podcastfy.litrpg.production import build_part_revision_prompt
from podcastfy.litrpg.production import build_showmanship_audit_prompt
from podcastfy.litrpg.production import build_tonal_audit_prompt
from podcastfy.litrpg.production import build_visual_state_extraction_prompt


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

    prompt = build_chapter_part_prompt(
        chapter_plan=plan,
        part=part,
        series_package_summary="System announcer: hostile office PA.",
        showrunner_context="Director's Console: PACING: SLOW.",
    )
    review = build_part_review_prompt(
        part_script="<HERO>We move.</HERO>",
        required_roles=part.required_roles,
        series_package_summary="System announcer: hostile office PA.",
    )

    for role in part.required_roles:
        assert role in prompt
        assert role in review
    assert "Every required role must appear" in prompt
    assert "Return actionable fixes first" in review
    assert "System announcer: hostile office PA." in prompt
    assert "PACING: SLOW" in prompt
    assert "System announcer: hostile office PA." in review


def test_chapter_review_checks_cast_separation_and_injected_scenes():
    cast = default_cast_roles()

    prompt = build_chapter_review_prompt(
        part_scripts=["<NARRATOR>Start.</NARRATOR>", "<SYSTEM>Loot.</SYSTEM>"],
        cast_roles=cast,
    )

    assert "15 distinct roles" in prompt
    assert "SYSTEM/announcer" in prompt
    assert "missing injected scene" in prompt


def test_review_loop_prompts_cover_director_audits_and_revision():
    script = "<HERO>I use the stapler skill.</HERO><SYSTEM>+5 XP.</SYSTEM>"

    director = build_director_pass_prompt(
        part_script=script,
        required_roles=["HERO", "SYSTEM"],
        series_package_summary="Hero voice: dry union pragmatist.",
    )
    mechanics = build_mechanics_audit_prompt(
        part_script=script,
        chapter_premise="A clerk enters a dungeon office.",
        series_package_summary="Hero voice: dry union pragmatist.",
    )
    description = build_description_audit_prompt(
        part_script=script,
        story_bible_summary="Hero: body: limping from copier mimic bite.",
    )
    tonal = build_tonal_audit_prompt(part_script=script)
    showmanship = build_showmanship_audit_prompt(part_script=script)
    revision = build_part_revision_prompt(
        draft_script=script,
        director_tags=director,
        mechanics_audit=mechanics,
        tonal_audit=tonal,
        showmanship_audit=showmanship,
        description_audit=description,
        required_roles=["HERO", "SYSTEM"],
        series_package_summary="Hero voice: dry union pragmatist.",
    )
    visual_update = build_visual_state_extraction_prompt(
        final_script=script,
        story_bible_summary="Hero: gear: stapler shield (jammed).",
    )

    assert "emotion" in director
    assert "XP totals" in mechanics
    assert "physical limitation" in description
    assert "stakes_seriousness" in tonal
    assert "sponsor_appeal" in showmanship
    assert "visual_anchors_dynamic" in visual_update
    assert "Allowed role tags: HERO, SYSTEM" in revision
    assert "Description and character audit" in revision
    assert "Do not include markdown" in revision
    assert "Hero voice: dry union pragmatist." in director
    assert "Hero voice: dry union pragmatist." in mechanics
    assert "Hero voice: dry union pragmatist." in revision
