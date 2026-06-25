import json

from podcastfy.litrpg.series_architect import BookPlan
from podcastfy.litrpg.series_architect import ChapterOutlineEntry
from podcastfy.litrpg.series_architect import SeriesArchitect
from podcastfy.litrpg.series_architect import SeriesShape
from podcastfy.litrpg.series_architect import bootstrap_series
from podcastfy.litrpg.series_architect import generate_tempo_map
from podcastfy.litrpg.series_architect import length_mode_for_chapters
from podcastfy.litrpg.series_architect import save_chapter_outline


def test_bootstrap_series_writes_contract_hierarchy_and_tempo_map(tmp_path):
    shape = SeriesShape(
        target_books=2,
        chapters_per_book=12,
        arc_style="escalating_floor_survival",
        series_title="No Fixed Address",
        series_promise="Underdogs survive impossible floors.",
        endgame_direction="The System is dismantled from inside.",
        power_curve="logarithmic",
        series_mysteries=["true purpose of the System"],
    )

    architect = bootstrap_series(storage_dir=tmp_path, series_id="no-fixed-address", shape=shape)

    root = tmp_path / "series" / "no-fixed-address"
    assert architect.available() is True
    assert (root / "series_plan.json").exists()
    assert (root / "series_arc.json").exists()
    assert (root / "book_1" / "book_plan.json").exists()
    tempo = json.loads((root / "book_1" / "tempo_map.json").read_text(encoding="utf-8"))
    assert len(tempo) == 12
    assert tempo[0]["must_not_spend"] == ["true purpose of the System"]


def test_tempo_map_changes_compression_by_length():
    tight = generate_tempo_map(
        BookPlan(
            book=1,
            role="Novella",
            major_change="Survive the first room.",
            power_ceiling="level 5",
            chapter_count=20,
            arc_style="escalating_floor_survival",
        )
    )
    epic = generate_tempo_map(
        BookPlan(
            book=1,
            role="Epic descent",
            major_change="Understand the floor ecology.",
            power_ceiling="level 25",
            chapter_count=80,
            arc_style="escalating_floor_survival",
        )
    )

    assert length_mode_for_chapters(20) == "tight"
    assert length_mode_for_chapters(80) == "epic"
    assert len(tight) == 20
    assert len(epic) == 80
    assert sum(1 for beat in epic if beat.phase == "Exploration") > sum(
        1 for beat in tight if beat.phase == "Exploration"
    )


def test_tempo_map_supports_tiny_smoke_books():
    tiny = generate_tempo_map(
        BookPlan(
            book=1,
            role="Smoke outline",
            major_change="Prove intake can bootstrap.",
            power_ceiling="level 3",
            chapter_count=3,
            arc_style="escalating_floor_survival",
        )
    )

    assert len(tiny) == 3
    assert [beat.chapter for beat in tiny] == [1, 2, 3]


def test_chapter_contract_merges_tempo_book_and_outline(tmp_path):
    shape = SeriesShape(
        target_books=1,
        chapters_per_book=10,
        series_title="No Fixed Address",
        series_promise="Loyal underdogs cheat impossible floors.",
        endgame_direction="Expose the System.",
        series_mysteries=["sponsor true identity"],
    )
    bootstrap_series(
        storage_dir=tmp_path,
        series_id="no-fixed-address",
        shape=shape,
        series_arc=[
            {
                "book": 1,
                "role": "Origin and first floor survival",
                "major_change": "They accept the dungeon is real.",
                "power_ceiling": "level 10",
                "chapter_count": 10,
                "arc_style": "escalating_floor_survival",
                "must_resolve": ["first floor boss"],
                "must_preserve": ["sponsor true identity"],
                "character_targets": {"protagonist": "stops denying the dungeon"},
                "faction_targets": ["merchant guild rumor"],
                "floor_range": [1, 3],
            }
        ],
    )
    save_chapter_outline(
        tmp_path,
        "no-fixed-address",
        1,
        [
            ChapterOutlineEntry(
                chapter=2,
                phase="The Drop",
                title="Notification: You Are Already Dead",
                premise="The tutorial door closes with no handle on this side.",
                ends_on="The handle appears on the wrong wall.",
                character_focus=["protagonist", "pedro"],
                introduces=["Welcoming Committee"],
                resolves=[],
                must_not_use=["sponsor true identity"],
            )
        ],
    )

    contract = SeriesArchitect(tmp_path, "no-fixed-address").get_chapter_contract(
        book_number=1,
        chapter_number=2,
    )

    assert contract["book"] == 1
    assert contract["chapter"] == 2
    assert contract["series_title"] == "No Fixed Address"
    assert contract["book_role"] == "Origin and first floor survival"
    assert contract["power_ceiling"] == "level 10"
    assert contract["title"] == "Notification: You Are Already Dead"
    assert "sponsor true identity" in contract["must_not_spend"]
    assert "sponsor true identity" in contract["must_not_use"]
    assert contract["character_targets"]["protagonist"] == "stops denying the dungeon"
