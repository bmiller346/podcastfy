import importlib
import json
from pathlib import Path

from podcastfy.litrpg.render_feedback import validate_directive


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_EXAMPLE = REPO_ROOT / "usage" / "litrpg_catamaran_crawlers_package.example.json"
TASK_EXAMPLE = REPO_ROOT / "usage" / "litrpg_task.example.json"
KNOTTY_SEED = REPO_ROOT / "usage" / "knotty_buoy_seed" / "knotty_buoy_canonical_seed.json"
KNOTTY_SEED_README = REPO_ROOT / "usage" / "knotty_buoy_seed" / "README.md"
KNOTTY_INTAKE_TASK = REPO_ROOT / "usage" / "knotty_buoy_premise_intake.example.json"
RENDER_LOOP_EXAMPLE = REPO_ROOT / "usage" / "litrpg_render_loop.example.json"
RENDER_LOOP_DOCS = REPO_ROOT / "usage" / "litrpg_render_loop.md"


def _load_package():
    return json.loads(PACKAGE_EXAMPLE.read_text(encoding="utf-8"))


def test_catamaran_series_package_has_required_sections():
    package = _load_package()

    assert package["schema_version"] == 1
    assert package["metadata"]["series_id"] == "catamaran-crawlers"
    assert package["metadata"]["status"] == "style_bible_seed"
    for key in [
        "premise",
        "system_announcer",
        "characters",
        "familiar",
        "home_base",
        "floor_rules",
        "faction_map",
        "prompt_summary",
    ]:
        assert key in package


def test_catamaran_announcer_fixture_preserves_performance_baseline():
    package = _load_package()
    announcer = package["system_announcer"]
    sample_text = "\n".join(line["text"] for line in announcer["sample_lines"])

    assert announcer["role_id"] == "SYSTEM_ANNOUNCER"
    assert "Bureaucratically enthusiastic" in announcer["voice_pillars"]
    assert "fine print" in " ".join(announcer["performance"]["emphasis_rules"])
    assert "STRUCTURAL ANOMALY" in sample_text
    assert "THAT'S NOT CODE" in sample_text


def test_catamaran_package_includes_character_and_portrayal_guardrails():
    package = _load_package()
    characters = {entry["role_id"]: entry for entry in package["characters"]}

    assert characters["EDWARD"]["class_candidate"] == "Structural Assessor"
    assert "Load Bearing Intuition" == characters["EDWARD"]["mechanics"]["passive"]
    assert characters["KELLI"]["class_candidate"] == "All-In"
    assert "not the joke" in characters["KELLI"]["portrayal_guardrail"]
    assert any("mental health" in item for item in characters["KELLI"]["avoid"])
    assert "sensitive_portrayal_notes" in package["metadata"]


def test_catamaran_package_covers_familiar_home_base_rules_and_factions():
    package = _load_package()

    assert package["familiar"]["name"] == "Pedro"
    assert "THAT'S NOT CODE" in package["familiar"]["signature_phrases"]
    assert package["home_base"]["system_status"] == "STRUCTURAL ANOMALY / MOBILE ASSET"
    assert package["floor_rules"]["floor"] == 1
    assert "northeast load-bearing pillar" in package["floor_rules"]["first_boss_vulnerability"]
    assert len(package["faction_map"]) >= 3


def test_catamaran_package_can_be_summarized_by_packages_api_when_available():
    package = _load_package()

    try:
        packages = importlib.import_module("podcastfy.litrpg.packages")
    except ModuleNotFoundError:
        packages = None

    if packages and hasattr(packages, "format_package_prompt_summary"):
        summary = packages.format_package_prompt_summary(package)
    else:
        summary = " ".join(package["prompt_summary"].values())

    assert "Edward" in summary
    assert "Kelli" in summary
    assert "Pedro" in summary
    assert "catamaran" in summary.lower()
    assert "System" in summary or "Interface" in summary


def test_checked_in_task_example_points_to_series_package_fixture():
    task = json.loads(TASK_EXAMPLE.read_text(encoding="utf-8"))

    assert task["series_package_path"] == "litrpg_catamaran_crawlers_package.example.json"
    assert PACKAGE_EXAMPLE.exists()


def test_knotty_buoy_canonical_seed_exists_and_preserves_core_names():
    seed = json.loads(KNOTTY_SEED.read_text(encoding="utf-8"))

    assert seed["schema_version"] == 1
    assert seed["metadata"]["series_id"] == "knotty-buoy"
    assert seed["metadata"]["status"] == "source_fixture"
    assert seed["series_core"]["registration_identity"] == "The Knotty Buoy"
    assert seed["series_core"]["canonical_vessel_name"] == "Sophie II"

    characters = {entry["id"]: entry for entry in seed["characters"]}
    assert characters["edward"]["name"] == "Edward Marsh"
    assert characters["kelli"]["name"] == "Kelli Marsh"
    assert characters["pedro"]["name"] == "Pedro"
    assert "Gallowgate" in seed["world_register"]["gallowgate"]["name"]
    assert seed["world_register"]["grand_dredger"]["name"] == "Grand Dredger"


def test_knotty_buoy_seed_includes_pedro_phrase_vocabulary():
    seed = json.loads(KNOTTY_SEED.read_text(encoding="utf-8"))
    vocabulary = seed["pedro_phrase_vocabulary"]
    phrases = {entry["text"]: entry for entry in vocabulary["available_phrases"]}

    assert vocabulary["declared_total_phrases"] == 47
    for phrase in [
        "THAT'S NOT CODE.",
        "WHERE'S THE PERMIT?",
        "DOUBLE DOWN.",
        "I'M NOT PAYING FOR THAT.",
        "THE HOUSE TAKES ALL.",
        "THE ARCHITECT IS ROTTING.",
    ]:
        assert phrase in phrases
    assert phrases["THE ARCHITECT IS ROTTING."]["category"] == "flagged"
    assert "Grand Dredger" in phrases["THE ARCHITECT IS ROTTING."]["broadcast_lock"]


def test_knotty_buoy_seed_covers_home_base_floor_rules_and_outline():
    seed = json.loads(KNOTTY_SEED.read_text(encoding="utf-8"))

    home_base = seed["home_base"]
    assert home_base["name"] == "Sophie II"
    assert home_base["system_registration"] == "The Knotty Buoy"
    assert home_base["stats"]["engines"] == "twin 45hp diesel engines"
    assert "dungeon-epoxy repairs" in home_base["upgrade_hooks"]

    floor = seed["floor_1"]
    assert floor["designation"] == "The Drowned Scaffolding"
    assert "Barnacle Scrip" in floor["economy"]
    assert {entry["name"] for entry in floor["entities"]} >= {
        "Barnacle Mimics",
        "Rebar Gargoyles",
        "OSHA Wraiths",
        "Dockmaster Brine",
    }

    outline = seed["book_1_outline"]
    assert len(outline) == 30
    assert outline[0]["title"] == "Out of the Atlantic"
    assert outline[-1]["title"] == "The Knot Holds"
    assert all("source_beat" in entry and "ending_hook" in entry for entry in outline)


def test_knotty_buoy_docs_show_intake_bootstrap_without_final_prose():
    readme = KNOTTY_SEED_README.read_text(encoding="utf-8")
    intake = json.loads(KNOTTY_INTAKE_TASK.read_text(encoding="utf-8"))
    seed = json.loads(KNOTTY_SEED.read_text(encoding="utf-8"))

    assert "python -m podcastfy.litrpg.task usage/knotty_buoy_premise_intake.example.json" in readme
    assert "not generated chapter prose" in readme
    assert intake["mode"] == "premise_intake"
    assert intake["series_id"] == seed["metadata"]["series_id"]
    assert intake["chapters_per_book"] == seed["metadata"]["chapter_count"]
    assert seed["metadata"]["artifact_type"] == "canonical_seed_data"


def test_render_loop_example_is_bounded_and_parseable():
    task = json.loads(RENDER_LOOP_EXAMPLE.read_text(encoding="utf-8"))
    render_loop = task["render_loop"]
    directives = task["performance_directives"]
    valid_strategies = {"none", "same_directive", "deterministic_adjustment", "llm_revision"}

    assert task["mode"] == "episode"
    assert task["render_audio"] is True
    assert render_loop["enabled"] is True
    assert render_loop["retry_strategy"] in valid_strategies
    assert 1 <= render_loop["max_attempts"] <= 3
    assert 0.0 < render_loop["retry_below_score"] <= 1.0
    assert "default" in directives
    assert 0.0 <= directives["default"]["intensity"] <= 1.0
    assert directives["default"]["pace"] == "steady"
    assert validate_directive(directives["default"]).valid is True
    assert "script" in task and "No story rewrite requested" in task["script"]


def test_render_loop_llm_revision_example_is_explicitly_opt_in():
    task = json.loads(RENDER_LOOP_EXAMPLE.read_text(encoding="utf-8"))
    example = task["llm_revision_example"]["render_loop"]
    docs = RENDER_LOOP_DOCS.read_text(encoding="utf-8")

    assert task["render_loop"]["retry_strategy"] == "deterministic_adjustment"
    assert example["retry_strategy"] == "llm_revision"
    assert example["llm_revision_enabled"] is True
    assert "No autonomous story rewrite happens." in docs
    assert "get_render_feedback" in docs
    assert "audio_metadata.json" in docs
