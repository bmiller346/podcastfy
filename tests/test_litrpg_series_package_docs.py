import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "usage"


def test_series_package_docs_reference_existing_seed_files():
    series_doc = USAGE / "litrpg_series_package.md"
    announcer_doc = USAGE / "litrpg_announcer_seed.md"
    example_json = USAGE / "litrpg_catamaran_crawlers_package.example.json"

    assert series_doc.exists()
    assert announcer_doc.exists()
    assert example_json.exists()

    text = series_doc.read_text(encoding="utf-8")
    assert "litrpg_announcer_seed.md" in text
    assert "litrpg_catamaran_crawlers_package.example.json" in text
    assert "Premise -> Series Bible -> Role/Performance Packages" in text


def test_catamaran_series_package_example_loads_as_json():
    package = json.loads(
        (USAGE / "litrpg_catamaran_crawlers_package.example.json").read_text(
            encoding="utf-8"
        )
    )

    assert package["schema_version"] == 1
    assert package["metadata"]["series_id"] == "catamaran-crawlers"
    assert package["metadata"]["status"] == "style_bible_seed"
    assert package["system_announcer"]["role_id"] == "SYSTEM_ANNOUNCER"
    assert package["system_announcer"]["sample_lines"]
    assert package["prompt_summary"]["tone"]


def test_announcer_seed_contains_prompt_ready_baseline_not_final_text():
    text = (USAGE / "litrpg_announcer_seed.md").read_text(encoding="utf-8")

    assert "ROLE: SYSTEM_ANNOUNCER" in text
    assert "The Interface" in text
    assert "not as final chapter text" in text
    assert "Parentheticals" in text
    assert "Do not inject it as normal narrator guidance" in text
