import json

import pytest

from podcastfy.litrpg.foreshadowing import foreshadow_entry_from_dict
from podcastfy.litrpg.models import SchemaValidationError
from podcastfy.litrpg.models import character_state_from_mapping
from podcastfy.litrpg.models import chapter_contract_from_mapping
from podcastfy.litrpg.models import hook_contract_from_mapping
from podcastfy.litrpg.models import mystery_lock_from_mapping
from podcastfy.litrpg.models import series_arc_beat_from_mapping
from podcastfy.litrpg.models import voice_constraint_from_mapping
from podcastfy.litrpg.models import world_register_entry_from_mapping
from podcastfy.litrpg.series_architect import load_tempo_map
from podcastfy.litrpg.state_store import load_series_state


def test_character_state_contract_defaults_optional_fields():
    state = character_state_from_mapping(
        {"name": "Edward Marsh", "level": "2", "character_class": "Dock Knight"}
    )

    assert state.name == "Edward Marsh"
    assert state.level == 2
    assert state.stats == {}
    assert state.skills == []
    assert state.inventory == []


def test_character_state_contract_rejects_missing_required_fields():
    with pytest.raises(SchemaValidationError, match="character.character_class is required"):
        character_state_from_mapping({"name": "Kelli Marsh", "level": 1})


def test_chapter_contract_rejects_bad_numeric_targets():
    with pytest.raises(SchemaValidationError, match="tension must be an integer"):
        chapter_contract_from_mapping(
            {
                "book": 1,
                "chapter": 4,
                "phase": "The Apex",
                "tension": "eleven",
                "creativity": 5,
                "absurdity": 6,
            }
        )


def test_chapter_contract_coerces_backward_compatible_defaults():
    contract = chapter_contract_from_mapping(
        {
            "book": "1",
            "chapter": "2",
            "phase": "The Bivouac",
            "tension": 3,
            "creativity": 4,
            "absurdity": 5,
        }
    )

    assert contract.book == 1
    assert contract.series_title == "Untitled Series"
    assert contract.must_not_spend == []
    assert contract.chapter_count == 1


def test_series_arc_beat_rejects_out_of_range_tension():
    with pytest.raises(SchemaValidationError, match="series_arc_beat.tension"):
        series_arc_beat_from_mapping(
            {
                "chapter": 1,
                "phase": "The Drop",
                "tension": 99,
                "creativity": 5,
                "absurdity": 5,
            }
        )


def test_mystery_lock_rejects_inverted_payoff_range():
    with pytest.raises(SchemaValidationError, match="intended_payoff_end"):
        mystery_lock_from_mapping(
            {
                "mystery": "Who owns the buoy?",
                "detail": "A brass plaque has been filed off.",
                "planted_chapter": 2,
                "intended_payoff_start": 8,
                "intended_payoff_end": 6,
            }
        )


def test_hook_voice_and_world_contracts_validate_required_identity():
    hook = hook_contract_from_mapping(
        {
            "category": "quiet_dread",
            "open_question": "Why did the dock bell ring underwater?",
            "mystery_lock": {
                "mystery": "Who rings the drowned bell?",
                "detail": "A bell rings below the dock at low tide.",
                "planted_chapter": 3,
                "intended_payoff_range": [10, 12],
            },
        }
    )
    voice = voice_constraint_from_mapping(
        {"role": "SYSTEM_ANNOUNCER", "must_avoid": ["warm reassurance"]}
    )
    entry = world_register_entry_from_mapping(
        {"kind": "location", "name": "The Knotty Buoy", "detail": "Damaged home base."}
    )

    assert hook.mystery_lock is not None
    assert hook.mystery_lock.intended_payoff_end == 12
    assert voice.tts_constraints == []
    assert entry.floor is None


def test_series_state_load_fails_clearly_for_invalid_character_payload(tmp_path):
    series_dir = tmp_path / "bad-series"
    series_dir.mkdir()
    (series_dir / "series_state.json").write_text(
        json.dumps(
            {
                "series_id": "bad-series",
                "title": "Bad Series",
                "episode_number": 1,
                "character": {"name": "Edward", "level": "not-a-number"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SchemaValidationError, match="character.level must be an integer"):
        load_series_state(series_dir)


def test_tempo_map_load_rejects_bad_contract_types(tmp_path):
    book_dir = tmp_path / "series" / "bad-series" / "book_1"
    book_dir.mkdir(parents=True)
    (book_dir / "tempo_map.json").write_text(
        json.dumps(
            [
                {
                    "chapter": 1,
                    "phase": "The Drop",
                    "tension": "high",
                    "creativity": 5,
                    "absurdity": 5,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SchemaValidationError, match="series_arc_beat.tension"):
        load_tempo_map(tmp_path, "bad-series", 1)


def test_foreshadow_entry_uses_mystery_lock_contract():
    with pytest.raises(SchemaValidationError, match="mystery_lock.mystery is required"):
        foreshadow_entry_from_dict(
            {
                "detail": "A receipt prints tomorrow's date.",
                "planted_chapter": 1,
                "intended_payoff_range": [4, 6],
            }
        )
