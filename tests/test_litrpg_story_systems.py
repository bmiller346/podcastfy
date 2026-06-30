import json

from podcastfy.litrpg.chapter_contract_integrator import assemble_chapter_contract
from podcastfy.litrpg.chapter_contract_integrator import format_integrated_chapter_context
from podcastfy.litrpg.chapter_contract_integrator import validate_integrated_contract
from podcastfy.litrpg.comedy_pressure import build_comedy_beats
from podcastfy.litrpg.comedy_pressure import validate_comedy_beats
from podcastfy.litrpg.conspiracy_engine import save_conspiracy_engine
from podcastfy.litrpg.continuity import emotional_arc_registry_from_dict
from podcastfy.litrpg.continuity import save_emotional_arcs
from podcastfy.litrpg.faction_ops import plan_faction_move
from podcastfy.litrpg.faction_ops import validate_faction_move
from podcastfy.litrpg.floor_identity import build_floor_identity
from podcastfy.litrpg.floor_identity import validate_floor_identity
from podcastfy.litrpg.foreshadowing import ForeshadowLedger
from podcastfy.litrpg.foreshadowing import ForeshadowEntry
from podcastfy.litrpg.foreshadowing import save_foreshadow_ledger
from podcastfy.litrpg.mechanics_engine import build_encounter_contract
from podcastfy.litrpg.mechanics_engine import validate_encounter_contract
from podcastfy.litrpg.originality_guardrail import audit_originality
from podcastfy.litrpg.promise_ledger import build_promise_report
from podcastfy.litrpg.scene_rendering_audit_gate import apply_scene_rendering_audit_gate
from podcastfy.litrpg.scene_rendering_audit_gate import parse_scene_rendering_audit
from podcastfy.litrpg.setpiece_engine import build_setpiece_contract
from podcastfy.litrpg.setpiece_engine import validate_setpiece_contract
from podcastfy.litrpg.simulation_harness import run_simulation_dry_run
from podcastfy.litrpg.series_architect import SeriesArchitect
from podcastfy.litrpg.series_architect import bootstrap_series
from podcastfy.litrpg.series_architect import format_chapter_contract_context
from podcastfy.litrpg.task import run_litrpg_task_data
from podcastfy.litrpg.threat_forge import forge_threat_contract
from podcastfy.litrpg.threat_forge import validate_threat_contract
from podcastfy.litrpg.world_state import load_world_state
from podcastfy.litrpg.world_state import save_world_state


def test_simulation_harness_reports_fake_three_chapter_state_drift(tmp_path):
    storage = tmp_path / "library"
    series_id = "paper-cuts"
    save_world_state(
        storage,
        series_id,
        {
            "active_mysteries": {"sponsor": {"status": "DO_NOT_SPEND"}},
            "artifacts": {
                "stamp": {
                    "locked_name": "Stamp",
                    "state": {"charges": 1},
                }
            },
        },
    )
    save_conspiracy_engine(
        storage,
        series_id,
        {"reader_position": {"must_not_know_yet": ["sponsor identity"]}},
    )
    save_emotional_arcs(
        storage,
        series_id,
        emotional_arc_registry_from_dict(
            {
                "series_id": series_id,
                "characters": {
                    "Mara": {
                        "character": "Mara",
                        "wound": "trusts systems too much",
                        "current_coping_mode": "quotes policy",
                    }
                },
            }
        ),
    )

    def runner(task):
        state = load_world_state(task["storage_dir"], series_id)
        chapter = int(task["chapter_number"])
        if chapter == 2:
            state["artifacts"]["stamp"]["state"]["charges"] = 3
        if chapter == 3:
            state["active_mysteries"]["sponsor"]["status"] = "REVEALED"
        save_world_state(task["storage_dir"], series_id, state)
        return {"combined_script": "dry run"}

    report = run_simulation_dry_run(
        storage_dir=storage,
        series_id=series_id,
        chapter_tasks=[
            {"chapter_number": 1, "chapter_contract": {"scene_type": "combat"}},
            {"chapter_number": 2, "chapter_contract": {"scene_type": "combat"}},
            {"chapter_number": 3, "chapter_contract": {"scene_type": "combat"}},
        ],
        chapter_runner=runner,
    )

    issue_types = {issue["type"] for issue in report["report"]["issues"]}
    assert report["passed"] is False
    assert "artifact_resource_reset" in issue_types
    assert "mystery_leakage" in issue_types
    assert "repeated_scene_types" in issue_types
    assert load_world_state(storage, series_id)["artifacts"]["stamp"]["state"]["charges"] == 1


def test_mechanics_threat_and_floor_contracts_are_inspectable():
    floor = build_floor_identity(
        floor=1,
        floor_plan={
            "name": "The Filing Reef",
            "visual_grammar": ["wet folders", "reef cubicles"],
            "economy": ["Staple Scrip"],
            "common_threats": ["Ink Eel"],
            "reward_logic": ["access before power"],
            "social_rules": ["forms must be witnessed"],
            "traversal_constraint": "walk only on stamped tiles",
            "faction_pressure": ["clerks auction mistakes"],
            "system_joke_style": "literal filing penalties",
            "exploit_pattern": "misfile the hazard under its own rule",
        },
    )
    threat = forge_threat_contract(floor_identity=floor, threat_seed={"name": "Ink Eel"})
    encounter = build_encounter_contract(
        chapter_contract={"premise": "Cross the reef."},
        character_state={"Mara": {"skills": ["Audit"]}},
        artifact_state={"stamp": {"locked_name": "Stamp", "state": {"charges": 1}}},
        threat_contract=threat,
        floor_identity=floor,
    )

    assert validate_floor_identity(floor)["passed"] is True
    assert validate_threat_contract(threat)["passed"] is True
    assert validate_encounter_contract(encounter)["passed"] is True
    assert encounter["objective"] == "Cross the reef."
    assert encounter["artifact_state_refs"][0].startswith("stamp: name=Stamp")


def test_setpiece_and_comedy_pressure_contracts_validate():
    setpiece = build_setpiece_contract(
        floor_identity={"name": "The Filing Reef", "traversal_constraint": "stamped tiles"},
        encounter_contract={
            "rules": ["unstamped tiles bite"],
            "fail_condition": "lose the only clean form",
            "exploit_surface": ["stamp the eel's shadow"],
        },
    )
    beats = build_comedy_beats(
        chapter_contract={"character_focus": ["Mara"], "comedy_pressure_source": "bureaucratic_cruelty"},
        setpiece_contract=setpiece,
    )

    assert validate_setpiece_contract(setpiece)["passed"] is True
    assert validate_comedy_beats(beats)["passed"] is True
    assert beats[0]["pressure_source"] == "bureaucratic_cruelty"


class RewriteLLM:
    def __init__(self):
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        return "rewritten with spatial anchor"


def test_scene_rendering_audit_gate_rewrites_or_quarantines():
    llm = RewriteLLM()
    revised = apply_scene_rendering_audit_gate(
        audit={"verdict": "revise", "violations": ["missing_spatial_anchor"]},
        script="floating action",
        llm=llm,
        scene_brief={"spatial_anchor": "reef office"},
    )
    blocked = apply_scene_rendering_audit_gate(
        audit={"verdict": "block", "violations": ["truth_document leaked"]},
        script="bad reveal",
    )

    assert revised["status"] == "revised"
    assert revised["script"] == "rewritten with spatial anchor"
    assert llm.calls[0]["stage"] == "scene_rendering_rewrite"
    assert blocked["status"] == "quarantined"
    assert parse_scene_rendering_audit("{bad json")["verdict"] == "block"


def test_faction_ops_uses_safe_conspiracy_context_only():
    move = plan_faction_move(
        conspiracy_context={
            "faction_constraints": {
                "sponsor": {
                    "name": "Sponsor Desk",
                    "apparent_goal": "increase broadcast fines",
                    "operational_rules": ["cannot touch contestants directly"],
                }
            },
            "truth_document": {"secret": "must not appear"},
        },
        chapter_contract={"faction": "sponsor", "hidden_goal_reference": "secret"},
        allowed_hidden_refs=[],
    )

    assert validate_faction_move(move)["passed"] is True
    assert move["move_type"] == "sponsor"
    assert move["hidden_goal_reference"] == ""
    assert "truth_document" not in json.dumps(move)


def test_promise_ledger_wraps_foreshadow_without_new_source():
    ledger = ForeshadowLedger(
        series_id="paper-cuts",
        planted=[
            ForeshadowEntry(
                detail="The copier remembers blood.",
                planted_chapter=1,
                intended_payoff_start=2,
                intended_payoff_end=3,
                mystery="copier memory",
            )
        ],
    )

    ready = build_promise_report(ledger, book=1, chapter=2)
    overdue = build_promise_report(ledger, book=1, chapter=4)

    assert ready["source"] == "foreshadow_ledger_wrapper"
    assert ready["ready_to_pay"][0]["reader_facing_wording"] == "The copier remembers blood."
    assert overdue["overdue"][0]["current_status"] == "overdue"


def test_originality_guardrail_distinguishes_structure_from_imitation():
    allowed = audit_originality("lethal absurd systems with bureaucratic satire")
    flagged = audit_originality("The announcer says New Achievement in a Dungeon Crawler Carl cadence.")

    assert allowed["passed"] is True
    assert flagged["passed"] is False
    assert flagged["warnings"][0]["action"]


def test_chapter_contract_integrator_is_bounded_and_truth_isolated():
    integrated = assemble_chapter_contract(
        chapter_contract={
            "book": 1,
            "chapter": 2,
            "title": "Stamped",
            "phase": "combat",
            "premise": "Cross the reef.",
            "character_focus": ["Mara"],
            "must_not_use": ["sponsor identity"],
        },
        world_state={
            "artifacts": {"stamp": {"locked_name": "Stamp", "state": {"charges": 1}}},
            "characters": {"Mara": {"skills": ["Audit"]}},
        },
        arc_context={
            "arc_pressure": [
                {
                    "character": "Mara",
                    "current_coping_mode": "quotes policy",
                    "allowed_shift": "micro-beat only",
                }
            ]
        },
        conspiracy_context={
            "forbidden_revelations": ["truth stays hidden"],
            "truth_document": {"secret": "do not leak"},
        },
        floor_plan={
            "name": "The Filing Reef",
            "visual_grammar": ["wet folders"],
            "economy": ["Staple Scrip"],
            "common_threats": ["Ink Eel"],
            "reward_logic": ["access before power"],
            "social_rules": ["forms must be witnessed"],
            "traversal_constraint": "stamped tiles",
            "faction_pressure": ["clerks auction mistakes"],
            "system_joke_style": "literal filing penalties",
            "exploit_pattern": "misfile the hazard",
        },
    )
    context = format_integrated_chapter_context(integrated)
    validation = validate_integrated_contract(integrated)

    assert validation["passed"] is True
    assert integrated["hidden_truth_isolated"] is True
    assert "truth_document" not in json.dumps(integrated)
    assert "[mechanics_engine]" in context
    assert "[forbidden_moves]" in context


def test_reader_contract_changes_by_book_position(tmp_path):
    bootstrap_series(
        storage_dir=tmp_path,
        series_id="paper-cuts",
        shape={
            "series_title": "Paper Cuts",
            "series_promise": "Clerks survive a lethal archive.",
            "target_books": 5,
            "chapters_per_book": 4,
            "series_mysteries": ["who owns the archive"],
        },
    )
    architect = SeriesArchitect(tmp_path, "paper-cuts")

    book_1 = architect.get_chapter_contract(book_number=1, chapter_number=1)
    mid = architect.get_chapter_contract(book_number=3, chapter_number=2)
    late = architect.get_chapter_contract(book_number=5, chapter_number=4)
    context = format_chapter_contract_context(book_1)

    assert book_1["reader_contract"]["book_position"] == "book_1"
    assert "why keep reading" in book_1["reader_contract"]["optimization_target"]
    assert mid["reader_contract"]["book_position"] == "mid_series"
    assert late["reader_contract"]["book_position"] == "late_series"
    assert "you were right to keep reading" in late["reader_contract"]["optimization_target"]
    assert "Reader contract" in context


def test_task_story_context_includes_integrated_systems_and_excludes_truth_document(tmp_path):
    bootstrap_series(
        storage_dir=tmp_path / "library",
        series_id="paper-cuts",
        shape={
            "series_title": "Paper Cuts",
            "series_promise": "Clerks survive a lethal archive.",
            "target_books": 2,
            "chapters_per_book": 3,
            "series_mysteries": ["sponsor identity"],
        },
    )
    save_world_state(
        tmp_path / "library",
        "paper-cuts",
        {
            "artifacts": {"stamp": {"locked_name": "Stamp", "state": {"charges": 1}}},
            "characters": {"Mara": {"skills": ["Audit"]}},
            "active_mysteries": {"sponsor": {"status": "DO_NOT_SPEND"}},
        },
    )
    save_conspiracy_engine(
        tmp_path / "library",
        "paper-cuts",
        {
            "truth_document": {"actual_reality": {"owner": "hidden"}},
            "reader_position": {"must_not_know_yet": ["sponsor identity"]},
            "factions": {
                "sponsor": {
                    "name": "Sponsor Desk",
                    "apparent_goal": "increase filing fees",
                    "operational_rules": ["cannot act without a posted fee schedule"],
                }
            },
        },
    )

    class CaptureLLM:
        def generate(self, *, prompt, stage):
            if stage == "scarcity_audit":
                return '{"passed":true,"violations":[],"warnings":[],"safe_hints":[],"spent_mysteries":[],"quarantine_required":false}'
            if stage == "scene_rendering_audit":
                return '{"verdict":"pass","violations":[],"warnings":[]}'
            return "<NARRATOR>Stamp charged once. Quest updated: survive.</NARRATOR>"

    result = run_litrpg_task_data(
        {
            "mode": "chapter",
            "series_id": "paper-cuts",
            "storage_dir": "library",
            "book_number": 1,
            "chapter_number": 1,
            "reviews_enabled": True,
            "revision_enabled": False,
            "approved_stages": ["chapter_generation"],
        },
        base_dir=tmp_path,
        llm=CaptureLLM(),
    )

    context = result["chapter"]["story_engine_context"]
    assert "[mechanics_engine]" in context
    assert "[faction_ops]" in context
    assert "[promise_ledger]" in context
    assert "[originality_guardrail]" in context
    assert "Reader contract" in result["chapter"]["showrunner_context"]
    assert "truth_document" not in context
    assert "actual_reality" not in context
    assert result["chapter"]["scene_rendering_gate_mode"] == "report"


def test_simulation_harness_reports_overdue_promise(tmp_path):
    storage = tmp_path / "library"
    series_id = "paper-cuts"
    save_world_state(storage, series_id, {})
    save_foreshadow_ledger(
        storage,
        ForeshadowLedger(
            series_id=series_id,
            planted=[
                ForeshadowEntry(
                    detail="The copier remembers blood.",
                    planted_chapter=1,
                    intended_payoff_start=2,
                    intended_payoff_end=3,
                    mystery="copier memory",
                )
            ],
        ),
    )

    report = run_simulation_dry_run(
        storage_dir=storage,
        series_id=series_id,
        chapter_tasks=[
            {"chapter_number": 1, "chapter_contract": {"scene_type": "setup"}},
            {"chapter_number": 2, "chapter_contract": {"scene_type": "pressure"}},
            {"chapter_number": 4, "chapter_contract": {"scene_type": "payoff"}},
        ],
        chapter_runner=lambda task: {"world_state_update": "{}"},
    )

    assert any(issue["type"] == "overdue_promise" for issue in report["report"]["issues"])
