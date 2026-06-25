import json

from podcastfy.litrpg.packages import CharacterPackage, FactionPackage
from podcastfy.litrpg.packages import FamiliarPackage, FloorRulesPackage
from podcastfy.litrpg.packages import HomeBasePackage, SeriesPackage
from podcastfy.litrpg.packages import SystemAnnouncerPackage
from podcastfy.litrpg.packages import WorldEntityPackage, EncounterPackage
from podcastfy.litrpg.packages import SERIES_PACKAGE_FILENAME
from podcastfy.litrpg.packages import SERIES_PACKAGE_SCHEMA_VERSION
from podcastfy.litrpg.packages import default_series_package
from podcastfy.litrpg.packages import format_series_package_summary
from podcastfy.litrpg.packages import load_series_package
from podcastfy.litrpg.packages import merge_series_package_updates
from podcastfy.litrpg.packages import save_series_package
from podcastfy.litrpg.packages import series_package_from_dict
from podcastfy.litrpg.packages import series_package_path
from podcastfy.litrpg.packages import series_package_to_dict
from podcastfy.litrpg.packages import update_series_package


def test_load_series_package_returns_safe_default_when_missing(tmp_path):
    package = load_series_package(tmp_path, "catamaran-crawlers")

    assert package == default_series_package("catamaran-crawlers")
    assert package.schema_version == SERIES_PACKAGE_SCHEMA_VERSION
    assert package.system_announcer.name == "System Announcer"
    assert package.characters == {}
    assert series_package_path(tmp_path, "catamaran-crawlers") == (
        tmp_path / "series" / "catamaran-crawlers" / SERIES_PACKAGE_FILENAME
    )


def test_series_package_round_trip_persistence(tmp_path):
    package = SeriesPackage(
        series_id="catamaran-crawlers",
        premise="Retired sailors get dragged into a nautical dungeon.",
        metadata={"source": "premise-generator"},
        system_announcer=SystemAnnouncerPackage(
            voice="game-show menace",
            tone="cheerfully hostile",
            rules=["Treat legal disclaimers like insults."],
            sample_lines=["New achievement: Unsafe At Any Speed!"],
        ),
        characters={
            "Edward": CharacterPackage(
                name="Edward",
                role="reluctant protagonist",
                character_class="Structural Assessor",
                voice="dry, low, exhausted",
                rules=["Never sounds impressed by the System."],
            )
        },
        familiar=FamiliarPackage(
            name="Pedro",
            species="macaw",
            system_role="Familiar",
            vocabulary=["THAT'S NOT CODE"],
        ),
        home_base=HomeBasePackage(
            name="The Marsh catamaran",
            description="A damaged home base absorbed hull-first.",
            advantages=["Floating workshop"],
        ),
        floor_rules=FloorRulesPackage(
            floor="Floor 1",
            rules=["Structural damage can bypass some boss armor."],
        ),
        faction_map={
            "Docklords": FactionPackage(
                name="Docklords",
                agenda="Control safe moorings.",
                relationship="wary rivals",
            )
        },
        bestiary={
            "Saltwater Code-Worm": WorldEntityPackage(
                name="Saltwater Code-Worm",
                entity_type="mob",
                recurrence="common floor-one parasite",
                weaknesses=["copper grounding wire"],
                behavior_rules=["attacks damaged rigging first"],
            )
        },
        encounters={
            "Deputy Architect Branz": EncounterPackage(
                name="Deputy Architect Branz",
                encounter_type="floor boss",
                status="planned",
                location="marina inspection chamber",
                weaknesses=["northeast load-bearing pillar"],
            )
        },
    )

    save_series_package(tmp_path, package)
    loaded = load_series_package(tmp_path, "catamaran-crawlers")

    assert loaded == package
    raw_path = tmp_path / "series" / "catamaran-crawlers" / "series_package.json"
    raw = raw_path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    raw_package = json.loads(raw)
    assert raw_package["schema_version"] == SERIES_PACKAGE_SCHEMA_VERSION
    assert raw_package["characters"]["Edward"]["character_class"] == (
        "Structural Assessor"
    )
    assert raw_package["familiar"]["vocabulary"] == ["THAT'S NOT CODE"]
    assert raw_package["bestiary"]["Saltwater Code-Worm"]["weaknesses"] == [
        "copper grounding wire"
    ]
    assert raw_package["encounters"]["Deputy Architect Branz"]["status"] == "planned"


def test_series_package_from_dict_accepts_loose_shapes_and_aliases():
    package = series_package_from_dict(
        {
            "series_id": "catamaran-crawlers",
            "character_packages": [
                {
                    "name": "Edward",
                    "rules": "Treat absurdity with exhausted pragmatism.",
                }
            ],
            "familiar_package": {
                "name": "Pedro",
                "vocabulary": "THAT'S NOT CODE",
            },
            "faction_map": {
                "safe-zone-council": {
                    "agenda": "Tax every boat.",
                    "resources": ("guards", "permits"),
                }
            },
            "monsters": {
                "Dock Barnacle": {
                    "type": "mob",
                    "weaknesses": "scraper",
                }
            },
            "bosses": [
                {
                    "name": "Harbor Auditor",
                    "type": "social encounter",
                    "return_conditions": "appears after unpaid docking fees",
                }
            ],
        }
    )

    as_dict = series_package_to_dict(package)

    assert package.characters["Edward"].rules == [
        "Treat absurdity with exhausted pragmatism."
    ]
    assert package.familiar.vocabulary == ["THAT'S NOT CODE"]
    assert package.faction_map["safe-zone-council"].name == "safe-zone-council"
    assert package.faction_map["safe-zone-council"].resources == ["guards", "permits"]
    assert package.bestiary["Dock Barnacle"].entity_type == "mob"
    assert package.bestiary["Dock Barnacle"].weaknesses == ["scraper"]
    assert package.encounters["Harbor Auditor"].encounter_type == "social encounter"
    assert as_dict["series_id"] == "catamaran-crawlers"
    assert as_dict["characters"]["Edward"]["name"] == "Edward"


def test_merge_series_package_updates_keeps_existing_and_deduplicates():
    package = SeriesPackage(
        series_id="catamaran-crawlers",
        premise="Original premise.",
        metadata={"created_by": "test"},
        system_announcer=SystemAnnouncerPackage(
            tone="hostile sparkle",
            rules=["Never comfort the crawlers."],
        ),
        characters={
            "Edward": CharacterPackage(
                name="Edward",
                voice="low and tired",
                rules=["Never comfort the System."],
            )
        },
        faction_map={
            "Docklords": FactionPackage(
                name="Docklords",
                resources=["boats"],
            )
        },
    )

    updated = merge_series_package_updates(
        package,
        {
            "series_id": "catamaran-crawlers",
            "premise": "",
            "metadata": {"updated_by": "agent"},
            "system_announcer": {
                "tone": "hostile sparkle",
                "rules": [
                    "never comfort the crawlers.",
                    "Reads fine print like a personal attack.",
                ],
            },
            "characters": {
                "Edward": {
                    "name": "Edward",
                    "character_class": "Structural Assessor",
                    "rules": [
                        "Never comfort the System.",
                        "Solves problems with job-site logic.",
                    ],
                },
                "Kelli": {
                    "name": "Kelli",
                    "role": "chaos engine",
                    "rules": ["Risk math should feel emotionally real."],
                },
            },
            "faction_map": {
                "docklords": {
                    "name": "Docklords",
                    "resources": ["boats", "safe-zone permits"],
                    "relationship": "predatory landlords",
                }
            },
            "bestiary": {
                "code-worm": {
                    "name": "Code Worm",
                    "entity_type": "hazard",
                    "weaknesses": ["grounding wire"],
                }
            },
            "encounters": {
                "branz": {
                    "name": "Deputy Branz",
                    "encounter_type": "boss",
                    "status": "escaped",
                }
            },
        },
    )

    assert updated is package
    assert package.premise == "Original premise."
    assert package.metadata == {"created_by": "test", "updated_by": "agent"}
    assert package.system_announcer.rules == [
        "Never comfort the crawlers.",
        "Reads fine print like a personal attack.",
    ]
    assert package.characters["Edward"].voice == "low and tired"
    assert package.characters["Edward"].character_class == "Structural Assessor"
    assert package.characters["Edward"].rules == [
        "Never comfort the System.",
        "Solves problems with job-site logic.",
    ]
    assert package.characters["Kelli"].role == "chaos engine"
    assert package.faction_map["Docklords"].resources == [
        "boats",
        "safe-zone permits",
    ]
    assert package.faction_map["Docklords"].relationship == "predatory landlords"
    assert package.bestiary["code-worm"].weaknesses == ["grounding wire"]
    assert package.encounters["branz"].status == "escaped"


def test_update_series_package_loads_merges_and_saves(tmp_path):
    save_series_package(
        tmp_path,
        SeriesPackage(
            series_id="catamaran-crawlers",
            system_announcer=SystemAnnouncerPackage(name="Dungeon Host"),
            characters={"Edward": CharacterPackage(name="Edward", voice="dry")},
        ),
    )

    updated = update_series_package(
        tmp_path,
        "catamaran-crawlers",
        {
            "series_id": "catamaran-crawlers",
            "characters": {
                "Edward": {"name": "Edward", "rules": ["Use carpentry logic."]}
            },
        },
    )
    reloaded = load_series_package(tmp_path, "catamaran-crawlers")

    assert updated.characters["Edward"].voice == "dry"
    assert updated.system_announcer.name == "Dungeon Host"
    assert reloaded.characters["Edward"].rules == ["Use carpentry logic."]
    assert reloaded.system_announcer.name == "Dungeon Host"


def test_format_series_package_summary_is_compact_prompt_context():
    package = SeriesPackage(
        series_id="catamaran-crawlers",
        premise="A retired couple and their macaw enter a televised dungeon.",
        system_announcer=SystemAnnouncerPackage(
            voice="bright legal malice",
            tone="gleeful compliance failure",
            rules=["Mock mundane safety habits."],
            delivery_notes=["Punch achievements hard, disclaimers faster."],
        ),
        characters={
            "Edward": CharacterPackage(
                name="Edward",
                role="straight man",
                character_class="Rigger",
                voice="dry union foreman",
                rules=["Treat quests like unwanted paperwork."],
            )
        },
        familiar=FamiliarPackage(
            name="Pedro",
            species="macaw",
            system_role="Familiar",
            vocabulary=["THAT'S NOT CODE"],
        ),
        home_base=HomeBasePackage(
            name="catamaran",
            description="Absorbed boat-home with structural advantages.",
            advantages=["Mobile workshop"],
        ),
        floor_rules=FloorRulesPackage(
            floor="Floor 1",
            premise="Boardwalk dungeon politics.",
            hazards=["Load-bearing boss lairs"],
        ),
        faction_map={
            "Docklords": FactionPackage(
                name="Docklords",
                agenda="Control dock space.",
                relationship="hostile",
            )
        },
        bestiary={
            "Code Worm": WorldEntityPackage(
                name="Code Worm",
                entity_type="mob",
                recurrence="common floor-one nuisance",
                weaknesses=["freshwater shock"],
            )
        },
        encounters={
            "Branz": EncounterPackage(
                name="Branz",
                encounter_type="floor boss",
                status="escaped",
                location="inspection chamber",
            )
        },
    )

    summary = format_series_package_summary(package)

    assert summary.startswith("Series Package (catamaran-crawlers)")
    assert "Premise: A retired couple and their macaw" in summary
    assert "System Announcer: voice: bright legal malice" in summary
    assert "Edward: role: straight man" in summary
    assert "character class: Rigger" in summary
    assert "Familiar Pedro: species: macaw" in summary
    assert "Home Base catamaran:" in summary
    assert "Floor Rules: floor: Floor 1" in summary
    assert "Faction Docklords: agenda: Control dock space." in summary
    assert "Bestiary Code Worm: entity type: mob" in summary
    assert "weaknesses: freshwater shock" in summary
    assert "Encounter Branz: encounter type: floor boss" in summary
