from podcastfy.litrpg.production import build_chapter_part_prompt
from podcastfy.litrpg.production import build_chapter_plan, build_chapter_review_prompt
from podcastfy.litrpg.production import build_description_audit_prompt
from podcastfy.litrpg.production import build_director_pass_prompt
from podcastfy.litrpg.production import build_hook_engine_prompt
from podcastfy.litrpg.production import build_mechanics_audit_prompt
from podcastfy.litrpg.production import build_part_review_prompt, default_cast_roles
from podcastfy.litrpg.production import build_part_revision_prompt
from podcastfy.litrpg.production import build_scarcity_audit_prompt
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


def test_non_litrpg_chapter_plan_uses_generic_story_profile():
    plan = build_chapter_plan(
        premise="A village baker solves a murder through pastry gossip.",
        genre="cozy mystery",
    )
    part = plan.parts[2]

    prompt = build_chapter_part_prompt(
        chapter_plan=plan,
        part=part,
        genre="cozy mystery",
    )
    mechanics = build_mechanics_audit_prompt(
        part_script="<HERO>The alibi is in the receipt book.</HERO>",
        chapter_premise=plan.premise,
        genre="cozy mystery",
    )
    tonal = build_tonal_audit_prompt(
        part_script="<HERO>The scones know too much.</HERO>",
        genre="cozy mystery",
    )
    review = build_chapter_review_prompt(
        part_scripts=["<HERO>The clue was buttercream.</HERO>"],
        cast_roles=plan.cast_roles,
        genre="cozy mystery",
    )

    assert "cozy mystery audio chapter" in prompt
    assert "Genre/style: cozy mystery" in prompt
    assert "XP, loot" not in prompt
    assert "clues, promises, secrets" in prompt
    assert "cozy mystery story logic" in mechanics
    assert "XP totals" not in mechanics
    assert "genre_pressure" in tonal
    assert "SYSTEM/announcer" not in review


def test_part_prompt_requires_roles_and_review_before_render():
    plan = build_chapter_plan(premise="A clerk enters a dungeon office.")
    part = plan.parts[1]

    prompt = build_chapter_part_prompt(
        chapter_plan=plan,
        part=part,
        series_package_summary="System announcer: hostile office PA.",
        showrunner_context="Director's Console: PACING: SLOW.",
        story_engine_context="Continuity Ledger: Pedro invoices every insult.",
        scene_brief_context=(
            "Scene rendering contract:\n"
            "- Spatial anchor: Floor 4 Market, ceiling 40ft, three exits\n"
            "- Sensory hooks to re-trigger: copper and spoiled mushroom"
        ),
        series_anchor_block="Series Anchor Block:\n- Forbidden mysteries: Grand Dredger patron",
    )
    review = build_part_review_prompt(
        part_script="<HERO>We move.</HERO>",
        required_roles=part.required_roles,
        series_package_summary="System announcer: hostile office PA.",
        series_anchor_block="Series Anchor Block:\n- Forbidden mysteries: Grand Dredger patron",
    )

    for role in part.required_roles:
        assert role in prompt
        assert role in review
    assert "Every required role must appear" in prompt
    assert "Return actionable fixes first" in review
    assert "System announcer: hostile office PA." in prompt
    assert "PACING: SLOW" in prompt
    assert "Pedro invoices every insult" in prompt
    assert "Grand Dredger patron" in prompt
    assert "Grand Dredger patron" in review
    assert "System announcer: hostile office PA." in review
    assert "TTS-friendly role block constraints" in prompt
    assert "Allowed role tags: " in prompt
    assert "Character voice separation" in review
    assert "diction, sentence rhythm, taboo phrases" in review
    assert "Scarcity lock" in prompt
    assert "Mystery lock discipline" in prompt
    assert "Scene brief / rendering contract:" in prompt
    assert "Floor 4 Market, ceiling 40ft" in prompt
    assert "copper and spoiled mushroom" in prompt
    assert "spatial + sensory + threat orientation" in prompt


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
    hook = build_hook_engine_prompt(
        final_script=script,
        chapter_title="The Stapler Hungers",
        hook_context="Prior chapter ended on the elevator opening by itself.",
        chapter_contract={"phase": "The Apex", "tension": 9},
        series_anchor_block="Series Anchor Block:\n- Reveal locks: Sponsor name: book 3",
        genre="LitRPG",
    )

    assert "emotion" in director
    assert "cue_id" in director
    assert "render_hint" in director
    assert "SFX, ducking, filters" in director
    assert "XP totals" in mechanics
    assert "consumed items, debts, and access as hard constraints" in mechanics
    assert "physical limitation" in description
    assert "Physical continuity / degradation" in description
    assert "stakes_seriousness" in tonal
    assert "Bureaucratic-sadism rules" in tonal
    assert "sponsor_appeal" in showmanship
    assert "Announcer / System tone" in showmanship
    assert "visual_anchors_dynamic" in visual_update
    assert "last_image" in hook
    assert "first two paragraphs" in hook
    assert "elevator opening by itself" in hook
    assert "forbidden payoffs" in hook
    assert "Sponsor name: book 3" in hook
    assert "Allowed role tags: HERO, SYSTEM" in revision
    assert "Description and character audit" in revision
    assert "Do not include markdown" in revision
    assert "Hero voice: dry union pragmatist." in director
    assert "Hero voice: dry union pragmatist." in mechanics
    assert "Hero voice: dry union pragmatist." in revision


def test_scarcity_audit_prompt_returns_story_economy_schema():
    prompt = build_scarcity_audit_prompt(
        final_script="<SYSTEM>QUEST COMPLETE: Sponsor identity revealed.</SYSTEM>",
        series_anchor_block=(
            "Series Anchor Block:\n"
            "- Forbidden now: Sponsor identity\n"
            "- Reveal locks: Sponsor identity: reveal book 3, payoff book 4"
        ),
        scarcity_registry={
            "items": [
                {
                    "name": "Sponsor identity",
                    "reveal_allowed_at_book": 3,
                    "payoff_allowed_at_book": 4,
                }
            ]
        },
        chapter_contract={"book": 1, "chapter": 2},
    )

    assert "Audit story-economy scarcity" in prompt
    assert "not prose QA" in prompt
    assert "Sponsor identity: reveal book 3" in prompt
    assert '"passed": true' in prompt
    assert '"quarantine_required": false' in prompt
    assert "spent_mysteries" in prompt
