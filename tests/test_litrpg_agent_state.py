import json

from podcastfy.litrpg.agent_state import QueueItem
from podcastfy.litrpg.agent_state import add_queue_item
from podcastfy.litrpg.agent_state import complete_queue_item
from podcastfy.litrpg.agent_state import load_agent_state
from podcastfy.litrpg.agent_state import record_next_chapter_action
from podcastfy.litrpg.agent_state import record_quarantine_blocker
from podcastfy.litrpg.agent_state import save_agent_state


def test_queue_item_add_dedupe_and_complete(tmp_path):
    state = load_agent_state(tmp_path, "paper-cuts")
    state = add_queue_item(
        state,
        "next",
        QueueItem(
            id="next:chapter:2",
            kind="next_chapter",
            summary="Prepare Chapter 2.",
            source="test",
            priority=3,
        ),
    )
    state = add_queue_item(
        state,
        "next",
        QueueItem(
            id="next:chapter:2",
            kind="next_chapter",
            summary="Prepare Chapter 2 with urgency.",
            source="test",
            priority=1,
        ),
    )

    assert len(state["next"]) == 1
    assert state["next"][0]["priority"] == 1
    state = complete_queue_item(state, "next:chapter:2")
    assert state["next"] == []

    path = save_agent_state(tmp_path, state)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["series_id"] == "paper-cuts"


def test_record_quarantine_blocker_and_next_chapter_action(tmp_path):
    state = load_agent_state(tmp_path, "paper-cuts")
    state = record_quarantine_blocker(
        state,
        series_id="paper-cuts",
        chapter_number=12,
        quarantine_path="q.json",
        reason="max_rewrite_attempts_exceeded",
    )
    state = record_next_chapter_action(
        state,
        series_id="paper-cuts",
        book_number=1,
        chapter_number=2,
        opener="Open on the stapler grin.",
    )

    assert state["blocked"][0]["kind"] == "quarantine_blocker"
    assert state["blocked"][0]["metadata"]["quarantine_path"] == "q.json"
    assert state["next"][0]["id"] == "next:chapter:3"
    assert state["next"][0]["metadata"]["opener"] == "Open on the stapler grin."
