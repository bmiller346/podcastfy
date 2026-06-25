import sys
import shutil
import types
from pathlib import Path
from uuid import uuid4

import pytest

import podcastfy.litrpg.package_generator as generator_module
from podcastfy.litrpg.packages import load_series_package
from podcastfy.litrpg.package_generator import (
    MINIMUM_CHARACTER_PACKAGES,
    PACKAGE_GENERATOR_STAGE,
    build_series_package_prompt,
    coerce_series_package,
    extract_series_package_json,
    format_series_package_summary,
    generate_series_package,
    save_generated_series_package,
    validate_series_package,
)


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        return self.response


def test_build_series_package_prompt_includes_baseline_and_required_shape():
    prompt = build_series_package_prompt(
        premise="Retirees and a macaw get dragged into a dungeon.",
        series_id="catamaran-crawlers",
        baseline_text="System announcer speaks like fine print with a grudge.",
    )

    assert "Series id: catamaran-crawlers" in prompt
    assert "Retirees and a macaw" in prompt
    assert "fine print with a grudge" in prompt
    assert '"system_announcer"' in prompt
    assert '"characters"' in prompt
    assert "at least 15" in prompt
    assert "Return only one JSON object" in prompt


def test_extract_series_package_json_accepts_fenced_or_prefaced_response():
    fenced = """```json
{"series_id": "catamaran-crawlers", "characters": []}
```"""
    prefaced = """Sure, here is the package:
{"series_id": "ember-keep", "characters": []}
extra commentary"""

    assert extract_series_package_json(fenced)["series_id"] == "catamaran-crawlers"
    assert extract_series_package_json(prefaced)["series_id"] == "ember-keep"


def test_extract_series_package_json_rejects_missing_object():
    with pytest.raises(ValueError, match="did not contain"):
        extract_series_package_json("no json here")


def test_coerce_series_package_fills_safe_defaults_and_minimum_cast():
    package = coerce_series_package(
        {
            "series_id": "catamaran-crawlers",
            "system_announcer": {
                "sample_lines": ["NEW QUEST: Stop pretending retirement applies here."]
            },
            "characters": [
                {
                    "role": "hero",
                    "name": "Edward Marsh",
                    "delivery": "low, tired, practical",
                }
            ],
            "faction_map": {"boardwalk-kings": "Control safe-zone trade."},
        },
        premise="Edward wants the System to leave him alone.",
        baseline_text="Baseline system package.",
    )

    assert package["series_id"] == "catamaran-crawlers"
    assert package["metadata"]["baseline_used"] is True
    assert package["system_announcer"]["sample_announcements"] == [
        "NEW QUEST: Stop pretending retirement applies here."
    ]
    assert len(package["characters"]) >= MINIMUM_CHARACTER_PACKAGES
    assert package["characters"][0]["role"] == "HERO"
    assert package["characters"][0]["voice"]["delivery"] == "low, tired, practical"
    assert package["faction_map"][0]["name"] == "boardwalk-kings"
    assert package["validation_metadata"]["valid"] is True


def test_generate_series_package_uses_injected_llm_and_coerces_partial_json():
    llm = FakeLLM(
        """
        {
          "series_id": "catamaran-crawlers",
          "premise": "A boat becomes a dungeon base.",
          "characters": [{"role": "SYSTEM", "name": "Announcer"}],
          "system_announcer": {
            "voice_pillars": ["hostile marina paperwork"],
            "sample_announcements": ["ACHIEVEMENT: Hull-first entry."]
          }
        }
        """
    )

    package = generate_series_package(
        premise="A catamaran is absorbed into the World Dungeon.",
        series_id="catamaran-crawlers",
        baseline_text="Announcer baseline.",
        llm=llm,
    )

    assert llm.calls[0]["stage"] == PACKAGE_GENERATOR_STAGE
    assert "Announcer baseline." in llm.calls[0]["prompt"]
    assert package["series_id"] == "catamaran-crawlers"
    assert package["system_announcer"]["voice_pillars"] == ["hostile marina paperwork"]
    assert len(package["characters"]) >= MINIMUM_CHARACTER_PACKAGES


def test_format_series_package_summary_is_compact_prompt_context():
    package = coerce_series_package(
        {
            "series_id": "catamaran-crawlers",
            "premise": "Retirees survive the dungeon with a boat.",
            "system_announcer": {
                "voice_pillars": ["hostile", "pedantic", "showman"],
                "sample_announcements": ["NEW QUEST: Fix the rigging under fire."],
            },
            "home_base": {
                "name": "The Marsh Catamaran",
                "advantages": ["repairable shelter", "mobile staging ground"],
            },
            "characters": [
                {
                    "role": "HERO",
                    "name": "Edward",
                    "function": "reluctant structural problem solver",
                    "voice": {"delivery": "tired, low, practical"},
                }
            ],
        }
    )

    summary = format_series_package_summary(package, max_characters=3)

    assert summary.startswith("Series Package (catamaran-crawlers)")
    assert "System voice: hostile; pedantic; showman" in summary
    assert "Home base: The Marsh Catamaran" in summary
    assert "HERO | Edward | reluctant structural problem solver" in summary


def test_validate_series_package_reports_too_few_characters():
    metadata = validate_series_package(
        {
            "premise": "",
            "characters": [],
            "system_announcer": {},
            "familiar": {},
            "home_base": {},
            "floor_rules": {},
            "sample_announcements": [],
        }
    )

    assert metadata["valid"] is False
    assert any("at least 15" in error for error in metadata["errors"])
    assert "premise is empty" in metadata["warnings"]


def test_save_generated_series_package_returns_none_when_storage_module_missing(monkeypatch):
    def missing_import(name):
        if name == "podcastfy.litrpg.packages":
            raise ModuleNotFoundError(name)
        return __import__(name)

    monkeypatch.setattr(generator_module.importlib, "import_module", missing_import)

    assert save_generated_series_package({"series_id": "x"}) is None


def test_save_generated_series_package_uses_optional_worker_a_api(monkeypatch):
    calls = []
    module = types.ModuleType("podcastfy.litrpg.packages")

    def save_series_package(storage_dir, package):
        calls.append((storage_dir, package))
        return "saved-path"

    module.save_series_package = save_series_package
    monkeypatch.setitem(sys.modules, "podcastfy.litrpg.packages", module)

    result = save_generated_series_package(
        {"series_id": "catamaran-crawlers"}, storage_dir="data/litrpg"
    )

    assert result == "saved-path"
    assert len(calls) == 1
    storage_dir, payload = calls[0]
    assert storage_dir == "data/litrpg"
    assert payload["series_id"] == "catamaran-crawlers"
    assert payload["schema_version"] == generator_module.SERIES_PACKAGE_SCHEMA_VERSION
    assert payload["system_announcer"]["name"] == "System Announcer"
    assert isinstance(payload["characters"], list)


def test_save_generated_series_package_works_with_landed_storage_api():
    storage_dir = Path.cwd() / ".pytest-local" / f"package-generator-{uuid4().hex}"
    package = coerce_series_package(
        {
            "series_id": "catamaran-crawlers",
            "premise": "Retirees with a boat enter the dungeon.",
            "system_announcer": {
                "voice_pillars": ["weaponized fine print"],
                "sample_announcements": ["NEW QUEST: Dock under fire."],
            },
            "characters": [
                {
                    "role": "HERO",
                    "name": "Edward",
                    "class_or_mechanic": "Structural Assessor",
                    "voice": {
                        "delivery": "low, exhausted, practical",
                        "sample_lines": ["That beam is load-bearing."],
                    },
                }
            ],
        }
    )

    try:
        save_generated_series_package(package, storage_dir=storage_dir)
        saved = load_series_package(storage_dir, "catamaran-crawlers")

        assert saved.series_id == "catamaran-crawlers"
        assert saved.system_announcer.voice == "weaponized fine print"
        assert saved.system_announcer.sample_lines == ["NEW QUEST: Dock under fire."]
        assert saved.characters["Edward"].character_class == "Structural Assessor"
        assert saved.characters["Edward"].voice == "low, exhausted, practical"
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)
