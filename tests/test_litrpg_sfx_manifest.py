import pytest

from podcastfy.litrpg.sfx import load_asset_manifest
from podcastfy.litrpg.sfx_manifest import (
    AssetManifest,
    AssetManifestEntry,
    add_or_promote_asset,
    load_asset_manifest_file,
    save_asset_manifest_file,
    scan_asset_directory,
    validate_asset_manifest,
)


def test_load_save_manifest_round_trips_entries(tmp_path):
    manifest_path = tmp_path / "asset_manifest.json"
    manifest = AssetManifest(
        assets=[
            AssetManifestEntry(
                stem="sfx/coin_drop",
                tags=["coin drop", "loot"],
                cue_types=["sfx"],
                loopable=False,
                default_lufs=-17,
                intensity=4,
                pan_safe=True,
                transient=True,
                source="freesound_review",
                trusted=True,
                license="CC0",
                attribution="",
            )
        ]
    )

    save_asset_manifest_file(manifest, manifest_path)
    loaded = load_asset_manifest_file(manifest_path)

    assert loaded.version == 1
    assert loaded.assets[0].stem == "sfx/coin_drop"
    assert loaded.assets[0].tags == ["coin drop", "loot"]
    assert loaded.assets[0].trusted is True
    assert loaded.assets[0].license == "CC0"


def test_validate_manifest_reports_errors():
    manifest = AssetManifest(
        assets=[
            AssetManifestEntry(
                stem="sfx/bad",
                tags=["bad"],
                cue_types=["unsupported"],
                intensity=11,
            )
        ]
    )

    with pytest.raises(ValueError, match="unsupported"):
        validate_asset_manifest(manifest)

    duplicate = AssetManifest(
        assets=[
            AssetManifestEntry(stem="sfx/hit", tags=["hit"], license="CC0"),
            AssetManifestEntry(stem="sfx/hit.wav", tags=["hit alt"], license="CC0"),
        ]
    )

    with pytest.raises(ValueError, match="Duplicate asset stem"):
        validate_asset_manifest(duplicate)


def test_validation_preserves_bad_json_types(tmp_path):
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(
        """
{
  "version": 1,
  "assets": [
    {
      "stem": "sfx/bad_bool",
      "tags": ["bad"],
      "cue_types": ["sfx"],
      "loopable": "false",
      "default_lufs": -18,
      "intensity": 3,
      "pan_safe": true,
      "transient": true,
      "source": "test",
      "trusted": false,
      "license": "CC0",
      "attribution": ""
    }
  ]
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="loopable must be a boolean"):
        load_asset_manifest_file(manifest_path)


def test_add_or_promote_asset_merges_tags_and_trust_without_duplicates():
    manifest = AssetManifest(
        assets=[
            AssetManifestEntry(
                stem="sfx/sword_clash",
                tags=["sword", "metal"],
                cue_types=["sfx"],
                trusted=False,
                license="pending",
            )
        ]
    )

    result = add_or_promote_asset(
        manifest,
        {
            "path": "sfx/sword_clash.wav",
            "tags": ["metal", "clash"],
            "cue_types": ["sfx"],
            "source": "curated_local",
            "trusted": False,
            "license": "CC0",
            "attribution": "Reviewed library",
        },
        promote=True,
    )

    asset = result.assets[0]
    assert len(result.assets) == 1
    assert asset.stem == "sfx/sword_clash"
    assert asset.tags == ["sword", "metal", "clash"]
    assert asset.trusted is True
    assert asset.source == "curated_local"
    assert asset.license == "CC0"
    assert asset.attribution == "Reviewed library"


def test_scan_asset_directory_returns_untrusted_candidates_with_filename_tags(tmp_path):
    (tmp_path / "sfx").mkdir()
    (tmp_path / "music").mkdir()
    (tmp_path / "ambience").mkdir()
    (tmp_path / "sfx" / "Sword_Clash-01.wav").write_bytes(b"")
    (tmp_path / "music" / "Battle Loop.mp3").write_bytes(b"")
    (tmp_path / "ambience" / "dungeon_room.ogg").write_bytes(b"")
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")

    candidates = scan_asset_directory(tmp_path)
    by_stem = {candidate.stem: candidate for candidate in candidates}

    assert sorted(by_stem) == [
        "ambience/dungeon_room",
        "music/Battle Loop",
        "sfx/Sword_Clash-01",
    ]
    assert by_stem["sfx/Sword_Clash-01"].trusted is False
    assert by_stem["sfx/Sword_Clash-01"].tags == ["sword clash", "sword", "clash"]
    assert by_stem["sfx/Sword_Clash-01"].cue_types == ["sfx"]
    assert by_stem["music/Battle Loop"].cue_types == ["bgm_start"]
    assert by_stem["music/Battle Loop"].loopable is True
    assert by_stem["ambience/dungeon_room"].cue_types == ["ambience_start"]


def test_saved_manifest_is_compatible_with_sfx_loader(tmp_path):
    manifest_path = tmp_path / "asset_manifest.json"
    save_asset_manifest_file(
        AssetManifest(
            assets=[
                AssetManifestEntry(
                    stem="sfx/quest_popup",
                    tags=["quest"],
                    cue_types=["sfx"],
                    source="curated_local",
                    trusted=True,
                    license="CC0",
                    attribution="",
                )
            ]
        ),
        manifest_path,
    )

    library = load_asset_manifest(manifest_path)

    assert library["quest"][0]["stem"] == "sfx/quest_popup"
    assert library["quest"][0]["metadata"]["trusted"] is True
    assert library["quest"][0]["metadata"]["license"] == "CC0"
