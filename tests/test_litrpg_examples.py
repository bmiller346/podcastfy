import importlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_EXAMPLE = REPO_ROOT / "usage" / "litrpg_catamaran_crawlers_package.example.json"
TASK_EXAMPLE = REPO_ROOT / "usage" / "litrpg_task.example.json"


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
