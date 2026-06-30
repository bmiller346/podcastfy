import json

import pytest

from podcastfy.litrpg.chapter import generate_litrpg_chapter
from podcastfy.litrpg.task import run_litrpg_task


class FakeChapterLLM:
    def __init__(self):
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        if stage.startswith("part:"):
            role = "SYSTEM" if stage == "part:mechanics-reveal" else "NARRATOR"
            return f"<{role}>{stage} script with cursed stapler.</{role}>"
        if stage.startswith("review:"):
            return f"review for {stage}"
        if stage.startswith("director:"):
            return f'{{"summary":"director tags for {stage}","cues":[]}}'
        if stage.startswith("mechanics:"):
            return f"mechanics audit for {stage}: revise missing XP"
        if stage.startswith("description:"):
            return f"description audit for {stage}: score 8 verdict pass"
        if stage.startswith("tonal:"):
            return f"tonal audit for {stage}: stakes_seriousness 7 absurdity_pressure 8"
        if stage.startswith("showmanship:"):
            return f"showmanship audit for {stage}: sponsor appeal 7"
        if stage.startswith("revise:"):
            roles = []
            for line in prompt.splitlines():
                if line.startswith("Allowed role tags:"):
                    roles = [role.strip() for role in line.removeprefix("Allowed role tags:").split(",")]
                    break
            blocks = "".join(f"<{role}>{role} logs XP and loot.</{role}>" for role in roles)
            return blocks
        if stage == "chapter_review":
            return "chapter review: render ready"
        if stage == "visual_state_update":
            return '{"characters":{"Hero":{"current_injuries":["paper cut"]}}}'
        if stage == "hook":
            return (
                '{"verdict":"pass","hook_type":"action_cliffhanger",'
                '"last_image":"the stapler smiles","open_question":"who fed it?",'
                '"implied_cost":"the clerk has to touch it again",'
                '"next_chapter_obligation":"Open on the stapler grin."}'
            )
        if stage == "scarcity_audit":
            return (
                '{"passed":true,"violations":[],"warnings":[],'
                '"safe_hints":["HR System origin can be hinted"],'
                '"spent_mysteries":[],"quarantine_required":false}'
            )
        if stage == "rhythm":
            return '{"verdict":"pass","scores":{"tempo_match":9}}'
        if stage == "reader_proxy":
            return '{"verdict":"pass","scores":{"binge_worthiness":9}}'
        raise AssertionError(f"unexpected stage {stage}")


class AllRolesChapterLLM:
    def __init__(self):
        self.calls = []
        self.script = "".join(
            f"<{role}>{role} reports XP, loot, quest, skill, and inventory.</{role}>"
            for role in [
                "NARRATOR",
                "HERO",
                "SYSTEM",
                "SIDEKICK",
                "MINION",
                "RIVAL",
                "HEALER",
                "TANK",
                "ROGUE",
                "MAGE",
                "GUIDE",
                "MERCHANT",
                "MENTOR",
                "BOSS",
                "BEAST",
                "VILLAIN",
            ]
        )

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        if stage.startswith("part:") or stage.startswith("revise:"):
            return self.script
        if stage == "scarcity_audit":
            return (
                '{"passed":true,"violations":[],"warnings":[],'
                '"safe_hints":[],"spent_mysteries":[],"quarantine_required":false}'
            )
        return f"{stage} ok"


class FailsOnThirdPartLLM(AllRolesChapterLLM):
    def generate(self, *, prompt, stage):
        if stage == "part:mechanics-reveal":
            raise RuntimeError("simulated part failure")
        return super().generate(prompt=prompt, stage=stage)


class BlockingAuditLLM(AllRolesChapterLLM):
    def generate(self, *, prompt, stage):
        if stage.startswith("tonal:"):
            return (
                "stakes_seriousness: 2\n"
                "absurdity_pressure: 9\n"
                "verdict: block\n"
                "blocking_issues: jokes erase the hostage stakes"
            )
        if stage.startswith("showmanship:"):
            return (
                "crowd_engagement: 8\n"
                "brutality: 7\n"
                "creativity: 6\n"
                "humiliation: 5\n"
                "meme_potential: 4\n"
                "sponsor_appeal: 3\n"
                "verdict: pass"
            )
        return super().generate(prompt=prompt, stage=stage)


class BlockingDescriptionAuditLLM(AllRolesChapterLLM):
    def generate(self, *, prompt, stage):
        if stage.startswith("description:"):
            return (
                '{"verdict":"block","score":3,'
                '"blocking_issues":["Hero dodges on ruined left leg without consequence"],'
                '"fixes":["Make the left-calf injury alter the dodge."]}'
            )
        return super().generate(prompt=prompt, stage=stage)


class DirectorCueLLM(AllRolesChapterLLM):
    def generate(self, *, prompt, stage):
        if stage.startswith("director:"):
            return (
                '{"summary":"performance map","cues":['
                '{"role":"SYSTEM","emotion":"smug","delivery":"bark",'
                '"timing":"beat","audio_effect":"announcer slapback"}]}'
            )
        return super().generate(prompt=prompt, stage=stage)


class FailingScarcityAuditLLM(AllRolesChapterLLM):
    def generate(self, *, prompt, stage):
        if stage == "scarcity_audit":
            self.calls.append({"prompt": prompt, "stage": stage})
            return (
                '{"passed":false,"violations":["Sponsor identity revealed early"],'
                '"warnings":["Token count increased without trade"],'
                '"safe_hints":["Sponsor logo may appear"],'
                '"spent_mysteries":["Sponsor identity"],'
                '"quarantine_required":true}'
            )
        return super().generate(prompt=prompt, stage=stage)


class RewriteScarcityAuditLLM(AllRolesChapterLLM):
    def __init__(self):
        super().__init__()
        self.audit_count = 0

    def generate(self, *, prompt, stage):
        if stage == "scarcity_audit":
            self.calls.append({"prompt": prompt, "stage": stage})
            self.audit_count += 1
            if self.audit_count == 1:
                return (
                    '{"passed":false,"violations":["Sponsor identity revealed early"],'
                    '"warnings":[],"safe_hints":[],"spent_mysteries":["Sponsor identity"],'
                    '"quarantine_required":true}'
                )
            return (
                '{"passed":true,"violations":[],"warnings":[],'
                '"safe_hints":["Sponsor logo may appear"],"spent_mysteries":[],'
                '"quarantine_required":false}'
            )
        if stage.startswith("rewrite:scarcity:"):
            self.calls.append({"prompt": prompt, "stage": stage})
            return "<NARRATOR>Rewritten chapter keeps only a sponsor logo hint.</NARRATOR>"
        return super().generate(prompt=prompt, stage=stage)


def _chapter_task(**overrides):
    task = {
        "mode": "chapter",
        "series_id": "paper-cuts",
        "premise": "A clerk discovers the office is a dungeon.",
        "chapter_number": 2,
        "chapter_title": "The Stapler Hungers",
        "target_minutes": 25,
        "injected_beats": ["The cursed stapler must appear.", "The copier demands tribute."],
        "generation": {"provider": "fake", "temperature": 0.2},
        "reviews": {"enabled": True},
    }
    task.update(overrides)
    return task


def test_generate_litrpg_chapter_calls_parts_reviews_and_chapter_review_in_order():
    llm = FakeChapterLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            series_plan={
                "series_title": "Paper Cuts",
                "series_mysteries": ["HR System origin"],
            },
            book_plan={
                "book": 1,
                "role": "Origin and first floor survival",
                "power_ceiling": "level 10",
                "must_preserve": ["HR System origin"],
            },
            chapter_contract={
                "book": 1,
                "chapter": 2,
                "phase": "The Apex",
                "tension": 9,
                "must_not_spend": ["HR System origin"],
            },
        ),
        llm=llm,
    )

    assert [call["stage"] for call in llm.calls] == [
        "part:cold-open",
        "review:cold-open",
        "director:cold-open",
        "mechanics:cold-open",
        "description:cold-open",
        "tonal:cold-open",
        "showmanship:cold-open",
        "revise:cold-open",
        "part:party-pressure",
        "review:party-pressure",
        "director:party-pressure",
        "mechanics:party-pressure",
        "description:party-pressure",
        "tonal:party-pressure",
        "showmanship:party-pressure",
        "revise:party-pressure",
        "part:mechanics-reveal",
        "review:mechanics-reveal",
        "director:mechanics-reveal",
        "mechanics:mechanics-reveal",
        "description:mechanics-reveal",
        "tonal:mechanics-reveal",
        "showmanship:mechanics-reveal",
        "revise:mechanics-reveal",
        "part:boss-setpiece",
        "review:boss-setpiece",
        "director:boss-setpiece",
        "mechanics:boss-setpiece",
        "description:boss-setpiece",
        "tonal:boss-setpiece",
        "showmanship:boss-setpiece",
        "revise:boss-setpiece",
        "part:fallout-cliffhanger",
        "review:fallout-cliffhanger",
        "director:fallout-cliffhanger",
        "mechanics:fallout-cliffhanger",
        "description:fallout-cliffhanger",
        "tonal:fallout-cliffhanger",
        "showmanship:fallout-cliffhanger",
        "revise:fallout-cliffhanger",
        "chapter_review",
        "visual_state_update",
        "hook",
        "scarcity_audit",
        "rhythm",
        "reader_proxy",
    ]
    assert "The cursed stapler must appear." in llm.calls[0]["prompt"]
    assert result["chapter"]["number"] == 2
    assert result["chapter"]["title"] == "The Stapler Hungers"
    assert result["parts"][0]["review"] == "review for review:cold-open"
    assert result["parts"][0]["director_tags"].startswith('{"summary"')
    assert result["parts"][0]["mechanics_audit"].startswith("mechanics audit")
    assert result["parts"][0]["description_audit"].startswith("description audit")
    assert result["parts"][0]["gate"]["draft"]["ready"] is False
    assert result["parts"][0]["gate"]["final"]["ready"] is True
    assert result["qa"]["ready"] is True
    assert result["qa"]["parts"][0]["scores"]["tonal"] == {
        "stakes_seriousness": 7,
        "absurdity_pressure": 8,
    }
    assert result["qa"]["parts"][0]["verdicts"]["description"] == "pass"
    assert result["visual_state_update"].startswith('{"characters"')
    assert result["hook_review"].startswith('{"verdict"')
    assert result["scarcity_audit"]["passed"] is True
    assert result["scarcity_audit"]["safe_hints"] == ["HR System origin can be hinted"]
    assert result["render"]["metadata"]["scarcity_audit"]["passed"] is True
    assert result["render"]["metadata"]["hook_review"].startswith('{"verdict"')
    assert result["rhythm_review"].startswith('{"verdict"')
    assert result["reader_proxy_review"].startswith('{"verdict"')
    assert result["render"]["metadata"]["reader_proxy_review"].startswith('{"verdict"')
    assert result["render"]["metadata"]["chapter_review"] == "chapter review: render ready"
    assert result["render"]["metadata"]["visual_state_update"].startswith('{"characters"')
    assert result["render"]["metadata"]["qa_ready"] is True
    assert result["render"]["metadata"]["qa"]["parts"][0]["audits"]["director"]["raw"].startswith(
        '{"summary"'
    )
    assert result["render"]["metadata"]["qa"]["parts"][0]["audits"]["mechanics"]["raw"].startswith(
        "mechanics audit"
    )
    assert result["render"]["metadata"]["audio_readiness"]["render_ready"] is True
    assert result["render"]["metadata"]["audio_readiness"]["cue_count"] == 0
    assert "SYSTEM" in result["render"]["metadata"]["audio_readiness"]["role_tags"]
    assert "Hook Engine:" in llm.calls[0]["prompt"]
    assert "Series Anchor Block:" in llm.calls[0]["prompt"]
    assert "HR System origin" in result["chapter"]["series_anchor_block"]
    assert result["render"]["metadata"]["series_anchor_block"] == result["chapter"]["series_anchor_block"]
    assert result["chapter"]["scarcity_registry"]["items"]
    assert result["qa"]["parts"][0]["revision_targets"][0]["audit"] == "mechanics"
    assert "NARRATOR logs XP and loot" in result["combined_script"]
    assert result["render"]["ready"] is True
    assert result["render"]["audio_rendered"] is False


def test_generate_litrpg_chapter_applies_part_overrides_and_disables_reviews():
    llm = FakeChapterLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            reviews={"enabled": False},
            part_overrides={
                "cold-open": {
                    "title": "Payroll Ambush",
                    "target_minutes": 7,
                    "extra_injected_beats": ["The boss fight starts at the time clock."],
                }
            },
        ),
        llm=llm,
    )

    assert [call["stage"] for call in llm.calls] == [
        "part:cold-open",
        "part:party-pressure",
        "part:mechanics-reveal",
        "part:boss-setpiece",
        "part:fallout-cliffhanger",
    ]
    assert result["parts"][0]["title"] == "Payroll Ambush"
    assert result["parts"][0]["target_minutes"] == 7
    assert "The boss fight starts at the time clock." in result["parts"][0]["prompt"]
    assert result["parts"][0]["review"] == ""
    assert result["chapter_review"] == ""


def test_run_litrpg_task_routes_chapter_mode_and_writes_result(tmp_path):
    task_path = tmp_path / "chapter_task.json"
    task = _chapter_task(result_path="chapter_result.json")
    task_path.write_text(json.dumps(task), encoding="utf-8")
    llm = FakeChapterLLM()

    result = run_litrpg_task(task_path, llm=llm)

    written = json.loads((tmp_path / "chapter_result.json").read_text(encoding="utf-8"))
    assert result["mode"] == "chapter"
    assert written["mode"] == "chapter"
    assert written["series_id"] == "paper-cuts"


def test_run_litrpg_task_default_mode_still_uses_episode_pipeline(tmp_path, monkeypatch):
    task_path = tmp_path / "task.json"
    task_path.write_text(
        json.dumps(
            {
                "series_id": "paper-cuts",
                "premise": "A clerk discovers the office is a dungeon.",
                "outline": "Outline",
                "script": "<NARRATOR>Begin.</NARRATOR>",
                "render_audio": False,
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"mode": "episode", "series_id": kwargs["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_audio_episode", fake_generate)

    result = run_litrpg_task(task_path)

    assert result == {"mode": "episode", "series_id": "paper-cuts"}
    assert captured["premise"] == "A clerk discovers the office is a dungeon."


def test_generate_litrpg_chapter_writes_part_checkpoints(tmp_path):
    llm = AllRolesChapterLLM()
    checkpoint_dir = tmp_path / "checkpoints"

    result = generate_litrpg_chapter(
        _chapter_task(checkpoint_dir=str(checkpoint_dir), reviews={"enabled": False}),
        llm=llm,
    )

    checkpoint_files = sorted(checkpoint_dir.glob("*.json"))
    script_files = sorted(checkpoint_dir.glob("*_approved.xml"))
    assert len(checkpoint_files) == 5
    assert len(script_files) == 5
    first_checkpoint = json.loads(checkpoint_files[0].read_text(encoding="utf-8"))
    assert first_checkpoint["series_id"] == "paper-cuts"
    assert first_checkpoint["chapter_number"] == 2
    assert first_checkpoint["part"]["part_id"] == "cold-open"
    assert "<NARRATOR>" in script_files[0].read_text(encoding="utf-8")
    assert result["render"]["ready"] is True


def test_generate_litrpg_chapter_reports_reused_regenerated_and_stale_parts(tmp_path):
    prior_path = tmp_path / "prior.json"
    reusable_script = (
        "<NARRATOR>NARRATOR reports XP and loot.</NARRATOR>"
        "<HERO>HERO reports XP and loot.</HERO>"
        "<SYSTEM>SYSTEM reports XP and loot.</SYSTEM>"
        "<SIDEKICK>SIDEKICK reports XP and loot.</SIDEKICK>"
        "<MINION>MINION reports XP and loot.</MINION>"
    )
    prior_path.write_text(
        json.dumps(
            {
                "parts": [
                    {
                        "part_id": "cold-open",
                        "title": "Cold Open",
                        "required_roles": ["NARRATOR", "HERO", "SYSTEM", "SIDEKICK", "MINION"],
                        "revised_script": reusable_script,
                        "gate": {"final": {"ready": True}},
                    },
                    {
                        "part_id": "boss-setpiece",
                        "title": "Old Boss",
                        "required_roles": ["NARRATOR", "HERO", "SYSTEM", "BOSS", "BEAST", "MINION", "SIDEKICK"],
                        "revised_script": "<NARRATOR>Stale XP and loot.</NARRATOR>",
                        "gate": {"final": {"ready": True}},
                    },
                    {
                        "part_id": "party-pressure",
                        "title": "Party Pressure",
                        "required_roles": ["NARRATOR"],
                        "revised_script": "<NARRATOR>Blocked XP.</NARRATOR>",
                        "gate": {"final": {"ready": False}},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    llm = AllRolesChapterLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            reviews={"enabled": False},
            reuse_ready_parts_from=str(prior_path),
        ),
        llm=llm,
    )

    stages = [call["stage"] for call in llm.calls]
    reuse_by_id = {item["part_id"]: item for item in result["chapter"]["part_reuse"]}
    assert "part:cold-open" not in stages
    assert "part:boss-setpiece" in stages
    assert result["parts"][0]["locked"] is True
    assert result["parts"][0]["reuse"]["status"] == "reused"
    assert reuse_by_id["boss-setpiece"]["status"] == "regenerated_after_stale"
    assert reuse_by_id["boss-setpiece"]["stale_fields"] == ["title"]
    assert reuse_by_id["party-pressure"]["status"] == "regenerated_after_blocked"
    assert result["render"]["metadata"]["part_reuse"] == result["chapter"]["part_reuse"]


def test_run_litrpg_task_defaults_checkpoints_and_persists_state(tmp_path):
    task_path = tmp_path / "chapter_task.json"
    task = _chapter_task(
        result_path="chapter_result.json",
        storage_dir="library",
        reviews={"enabled": False},
    )
    task_path.write_text(json.dumps(task), encoding="utf-8")

    result = run_litrpg_task(task_path, llm=AllRolesChapterLLM())

    checkpoint_dir = tmp_path / "chapter_result_checkpoints"
    state_path = tmp_path / "library" / "series" / "paper-cuts" / "series_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["mode"] == "chapter"
    assert checkpoint_dir.exists()
    assert len(list(checkpoint_dir.glob("*_approved.xml"))) == 5
    assert state["episode_number"] == 2
    assert "Chapter 2: The Stapler Hungers" in state["memory"]


def test_generate_litrpg_chapter_preserves_prior_checkpoints_on_failure(tmp_path):
    checkpoint_dir = tmp_path / "checkpoints"

    with pytest.raises(RuntimeError, match="part:mechanics-reveal"):
        generate_litrpg_chapter(
            _chapter_task(
                checkpoint_dir=str(checkpoint_dir),
                reviews={"enabled": False},
                generation={"max_retries": 1},
            ),
            llm=FailsOnThirdPartLLM(),
        )

    assert [path.name for path in sorted(checkpoint_dir.glob("*_approved.xml"))] == [
        "01_cold-open_approved.xml",
        "02_party-pressure_approved.xml",
    ]


def test_generate_litrpg_chapter_block_verdict_makes_qa_and_render_not_ready():
    result = generate_litrpg_chapter(_chapter_task(), llm=BlockingAuditLLM())

    assert result["parts"][0]["gate"]["final"]["ready"] is True
    assert result["qa"]["ready"] is False
    assert result["render"]["ready"] is False
    assert result["qa"]["parts"][0]["verdicts"]["tonal"] == "block"
    assert result["qa"]["parts"][0]["scores"]["showmanship"]["sponsor_appeal"] == 3
    assert any("jokes erase" in issue for issue in result["qa"]["blocking_issues"])


def test_generate_litrpg_chapter_description_block_verdict_makes_render_not_ready():
    result = generate_litrpg_chapter(_chapter_task(), llm=BlockingDescriptionAuditLLM())

    assert result["qa"]["ready"] is False
    assert result["render"]["ready"] is False
    assert result["qa"]["parts"][0]["verdicts"]["description"] == "block"
    assert result["qa"]["parts"][0]["scores"]["description"]["score"] == 3
    assert any("ruined left leg" in issue for issue in result["qa"]["blocking_issues"])


def test_scarcity_failure_quarantines_and_blocks_render_without_rewrite():
    llm = FailingScarcityAuditLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            chapter_contract={
                "book": 1,
                "chapter": 2,
                "phase": "The Apex",
                "must_not_spend": ["Sponsor identity"],
            },
            series_plan={"series_mysteries": ["Sponsor identity"]},
        ),
        llm=llm,
    )

    assert result["scarcity_audit"]["passed"] is False
    assert result["qa"]["ready"] is False
    assert result["render"]["ready"] is False
    assert result["quarantine"]["status"] == "quarantined"
    assert result["quarantine"]["reason"] == "scarcity_audit_failed"
    assert "Sponsor identity revealed early" in result["rewrite_instruction"]
    assert not any(call["stage"].startswith("rewrite:scarcity:") for call in llm.calls)


def test_scarcity_rewrite_flag_reaudits_and_can_clear_quarantine():
    llm = RewriteScarcityAuditLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            rewrite_quarantined=True,
            max_rewrite_attempts=2,
            chapter_contract={
                "book": 1,
                "chapter": 2,
                "phase": "The Apex",
                "must_not_spend": ["Sponsor identity"],
            },
            series_plan={"series_mysteries": ["Sponsor identity"]},
        ),
        llm=llm,
    )

    assert result["scarcity_audit"]["passed"] is True
    assert result["quarantine"]["status"] == "passed"
    assert result["render"]["script"].startswith("<NARRATOR>Rewritten chapter")
    assert [call["stage"] for call in llm.calls if call["stage"].startswith("rewrite:scarcity:")] == [
        "rewrite:scarcity:2:1"
    ]


def test_generate_litrpg_chapter_injects_story_bible_summary_into_prompts():
    llm = FakeChapterLLM()

    generate_litrpg_chapter(
        _chapter_task(story_bible_summary="Hero never jokes about the elevator vow."),
        llm=llm,
    )

    assert "Story bible continuity:" in llm.calls[0]["prompt"]
    assert "Hero never jokes about the elevator vow." in llm.calls[0]["prompt"]
    mechanics_call = next(call for call in llm.calls if call["stage"] == "mechanics:cold-open")
    assert "Hero never jokes about the elevator vow." in mechanics_call["prompt"]


def test_generate_litrpg_chapter_injects_story_engine_context_into_part_prompts():
    llm = FakeChapterLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            story_engine_context=(
                "Voice Cards: Hero uses short denial.\n"
                "Foreshadow: toner clicks before anyone touches it.\n"
                "Emotional arcs: wound=promotion trap.\n"
                "Economy anchors: Toner Scrip buys safe passage."
            )
        ),
        llm=llm,
    )

    first_prompt = next(call["prompt"] for call in llm.calls if call["stage"] == "part:cold-open")
    assert "Story engine continuity context:" in first_prompt
    assert "Voice Cards: Hero uses short denial" in first_prompt
    assert "Foreshadow: toner clicks" in first_prompt
    assert "Economy anchors: Toner Scrip" in first_prompt
    assert result["chapter"]["story_engine_context"].startswith("Voice Cards")


def test_generate_litrpg_chapter_injects_series_package_summary_into_prompts():
    llm = FakeChapterLLM()

    result = generate_litrpg_chapter(
        _chapter_task(
            series_package={
                "premise": "Retirees and a macaw hit the dungeon in a boat.",
                "metadata": {
                    "title": "The Catamaran Crawlers",
                },
                "system_announcer": {
                    "name": "System Announcer",
                    "tone": "smug maritime game-show sadist",
                },
            }
        ),
        llm=llm,
    )

    package_line = "Retirees and a macaw hit the dungeon in a boat."
    assert package_line in result["chapter"]["series_package_summary"]
    assert package_line in llm.calls[0]["prompt"]
    for stage in [
        "review:cold-open",
        "director:cold-open",
        "mechanics:cold-open",
        "revise:cold-open",
        "chapter_review",
    ]:
        call = next(call for call in llm.calls if call["stage"] == stage)
        assert package_line in call["prompt"]


def test_generate_litrpg_chapter_passes_non_litrpg_genre_to_prompts():
    llm = AllRolesChapterLLM()

    result = generate_litrpg_chapter(
        {
            **_chapter_task(),
            "genre": "cozy mystery",
            "premise": "A village baker solves a murder through pastry gossip.",
            "part_overrides": {
                "cold-open": {"required_roles": ["NARRATOR", "HERO"]},
                "social-pressure": {"required_roles": ["NARRATOR"]},
                "rules-reveal": {"required_roles": ["NARRATOR"]},
                "setpiece": {"required_roles": ["NARRATOR"]},
                "fallout-cliffhanger": {"required_roles": ["NARRATOR"]},
            },
        },
        llm=llm,
    )

    first_prompt = next(
        call["prompt"] for call in llm.calls if call["stage"] == "part:cold-open"
    )
    mechanics_prompt = next(
        call["prompt"] for call in llm.calls if call["stage"] == "mechanics:cold-open"
    )

    assert result["chapter"]["genre"] == "cozy mystery"
    assert result["render"]["metadata"]["genre"] == "cozy mystery"
    assert "cozy mystery audio chapter" in first_prompt
    assert "XP, loot" not in first_prompt
    assert "cozy mystery story logic" in mechanics_prompt


def test_generate_litrpg_chapter_uses_mechanics_context_in_final_gate():
    script = (
        "<NARRATOR>XP total: 5.</NARRATOR>"
        "<HERO>I activate Meteor Punch.</HERO>"
        "<SYSTEM>Status: denied.</SYSTEM>"
        "<SIDEKICK>Quest updated.</SIDEKICK>"
        "<MINION>Loot envy rises.</MINION>"
    )

    result = generate_litrpg_chapter(
        _chapter_task(
            reviews={"enabled": False},
            part_overrides={
                "cold-open": {
                    "required_roles": ["NARRATOR", "HERO", "SYSTEM", "SIDEKICK", "MINION"]
                },
                "party-pressure": {"required_roles": ["NARRATOR"]},
                "mechanics-reveal": {"required_roles": ["NARRATOR"]},
                "boss-setpiece": {"required_roles": ["NARRATOR"]},
                "fallout-cliffhanger": {"required_roles": ["NARRATOR"]},
            },
            locked_part_scripts={
                "cold-open": script,
                "party-pressure": "<NARRATOR>+1 XP. Loot gained: memo.</NARRATOR>",
                "mechanics-reveal": "<NARRATOR>+1 XP. Quest updated: memo.</NARRATOR>",
                "boss-setpiece": "<NARRATOR>+1 XP. Status: cornered.</NARRATOR>",
                "fallout-cliffhanger": "<NARRATOR>+1 XP. Inventory: memo.</NARRATOR>",
            },
            mechanics_context={"skills": ["Paper Cut"], "class": "Intern"},
        ),
        llm=AllRolesChapterLLM(),
    )

    assert result["parts"][0]["gate"]["final"]["ready"] is False
    assert any("Meteor Punch" in issue for issue in result["parts"][0]["gate"]["final"]["issues"])
    assert result["qa"]["ready"] is False
    assert result["render"]["ready"] is False


def test_generate_litrpg_chapter_builds_render_role_instructions_from_casting_and_director():
    result = generate_litrpg_chapter(
        _chapter_task(
            casting_manifest={
                "SYSTEM": {
                    "instructions": "Hostile game interface.",
                    "baseline": {"pace": 1.05, "pitch": -1, "delivery": "crisp"},
                    "arc_modifiers": {"trauma": 0.2, "confidence": 0.8, "rage": 0.1},
                }
            }
        ),
        llm=DirectorCueLLM(),
    )

    system_instruction = result["render"]["role_instructions"]["SYSTEM"]
    assert "Baseline identity: Hostile game interface." in system_instruction
    assert "pace 1.05" in system_instruction
    assert "delivery bark" in system_instruction
    assert "audio effect announcer slapback" in system_instruction


def test_generate_litrpg_chapter_extracts_sfx_cues_for_render_mix_plan():
    result = generate_litrpg_chapter(
        _chapter_task(
            reviews={"enabled": False},
            part_overrides={
                "cold-open": {"required_roles": ["NARRATOR"]},
                "party-pressure": {"required_roles": ["NARRATOR"]},
                "mechanics-reveal": {"required_roles": ["NARRATOR"]},
                "boss-setpiece": {"required_roles": ["NARRATOR"]},
                "fallout-cliffhanger": {"required_roles": ["NARRATOR"]},
            },
            locked_part_scripts={
                "cold-open": (
                    "[BGM_START: battle volume=-9db]"
                    "<NARRATOR>+1 XP. Loot gained: badge.</NARRATOR>"
                    "[SFX: sword clash pan=left]"
                ),
                "party-pressure": "<NARRATOR>+1 XP. Quest updated: badge.</NARRATOR>",
                "mechanics-reveal": "<NARRATOR>+1 XP. Status: briefed.</NARRATOR>",
                "boss-setpiece": "<NARRATOR>+1 XP. Skill unlocked: Staple Guard.</NARRATOR>",
                "fallout-cliffhanger": "<NARRATOR>+1 XP. Inventory: badge.</NARRATOR>",
            },
        ),
        llm=AllRolesChapterLLM(),
    )

    assert "[BGM_START" in result["combined_script"]
    assert "[BGM_START" not in result["render"]["script"]
    assert result["render"]["cue_sheet"]["metadata"]["cue_count"] == 2
    assert result["render"]["mix_plan"]["metadata"]["cue_count"] == 2
    assert any(layer["type"] == "music" for layer in result["render"]["mix_plan"]["layers"])
    assert any(layer["type"] == "sfx" for layer in result["render"]["mix_plan"]["layers"])
