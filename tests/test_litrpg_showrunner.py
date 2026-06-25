import random

from podcastfy.litrpg.showrunner import build_showrunner_payload
from podcastfy.litrpg.showrunner import format_showrunner_context
from podcastfy.litrpg.showrunner import roll_wandering_event
from podcastfy.litrpg.showrunner import arc_entry_for_chapter


def test_showrunner_payload_maps_chapter_to_directives():
    payload = build_showrunner_payload(chapter_number=14)

    assert payload["phase"] == "Mid-Boss"
    assert payload["tension"] == 9
    assert payload["creativity"] == 2
    assert payload["absurdity"] == 4
    assert any("FRANTIC" in directive for directive in payload["directives"])
    assert any("STRICT INVENTORY LOCK" in directive for directive in payload["directives"])
    assert any("GROUNDED" in directive for directive in payload["directives"])


def test_showrunner_context_formats_director_console_for_prompt():
    payload = build_showrunner_payload(
        chapter_number=4,
        wandering_event={
            "name": "Test Trap",
            "tension_override": 8,
            "directive": "WANDERING EVENT: The room bites back.",
        },
    )

    context = format_showrunner_context(payload)

    assert "Director's Console" in context
    assert "The Bivouac" in context
    assert "tension 8" in context
    assert "The room bites back" in context
    assert "Test Trap" in context


def test_wandering_event_only_rolls_on_plateau_chapters():
    high = arc_entry_for_chapter(1)
    low = arc_entry_for_chapter(4)

    assert roll_wandering_event(high, rng=random.Random(1)) is None
    assert roll_wandering_event(low, rng=random.Random(5), trigger_roll=20) is not None
