from podcastfy.litrpg.effect_log import append_effect_log_entry
from podcastfy.litrpg.effect_log import build_effect_log_entry
from podcastfy.litrpg.effect_log import effect_log_path
from podcastfy.litrpg.effect_log import find_committed_effect
from podcastfy.litrpg.effect_log import make_idempotency_key
from podcastfy.litrpg.effect_log import read_effect_log
from podcastfy.litrpg.effect_log import should_skip_effect
from podcastfy.litrpg.effect_log import stable_hash


def test_idempotency_key_is_stable_and_changes_with_stage_or_input():
    input_hash = stable_hash({"prompt": "draft"})
    key = make_idempotency_key(
        series_id="paper-cuts",
        book_number=1,
        chapter_number=2,
        stage="chapter_generation",
        input_hash=input_hash,
        provider="fake",
        model="unit",
    )

    assert key == make_idempotency_key(
        series_id="paper-cuts",
        book_number=1,
        chapter_number=2,
        stage="chapter_generation",
        input_hash=input_hash,
        provider="fake",
        model="unit",
    )
    assert key != make_idempotency_key(
        series_id="paper-cuts",
        book_number=1,
        chapter_number=2,
        stage="audio_render",
        input_hash=input_hash,
        provider="fake",
        model="unit",
    )
    assert key != make_idempotency_key(
        series_id="paper-cuts",
        book_number=1,
        chapter_number=2,
        stage="chapter_generation",
        input_hash=stable_hash({"prompt": "different"}),
        provider="fake",
        model="unit",
    )


def test_effect_log_append_read_and_skip_policy(tmp_path):
    path = effect_log_path(tmp_path, "paper-cuts")
    entry = build_effect_log_entry(
        series_id="paper-cuts",
        book_number=1,
        chapter_number=2,
        stage="chapter_generation",
        input_payload={"prompt": "draft"},
        output_payload={"result": "ok"},
        provider="fake",
        model="unit",
    )
    failed = build_effect_log_entry(
        series_id="paper-cuts",
        book_number=1,
        chapter_number=2,
        stage="chapter_generation",
        input_payload={"prompt": "failed"},
        output_payload={"error": "boom"},
        status="failed",
    )

    append_effect_log_entry(path, entry)
    append_effect_log_entry(path, failed)

    entries = read_effect_log(path)
    assert len(entries) == 2
    assert entries[0].idempotency_key == entry.idempotency_key
    assert find_committed_effect(path, entry.idempotency_key) == entry
    assert should_skip_effect(path, idempotency_key=entry.idempotency_key, policy="") is False
    assert should_skip_effect(path, idempotency_key=entry.idempotency_key, policy="skip_committed") is True
    assert should_skip_effect(path, idempotency_key=failed.idempotency_key, policy="skip_committed") is False


def test_effect_log_stores_render_feedback_metadata(tmp_path):
    path = effect_log_path(tmp_path, "paper-cuts")
    entry = build_effect_log_entry(
        series_id="paper-cuts",
        book_number=1,
        chapter_number=3,
        stage="audio_render",
        input_payload={"chapter": 3},
        output_payload={"audio_path": "final.mp3"},
        provider="edge",
        model="edge",
        metadata={
            "render_feedback_score": 0.41,
            "human_review_required": True,
            "directive_valid": False,
            "segment_id": "chapter_003_part_001",
            "attempt": 1,
        },
    )

    append_effect_log_entry(path, entry)
    stored = read_effect_log(path)[0]

    assert stored.metadata["render_feedback_score"] == 0.41
    assert stored.metadata["human_review_required"] is True
    assert stored.metadata["directive_valid"] is False
    assert stored.metadata["segment_id"] == "chapter_003_part_001"
    assert stored.to_dict()["metadata"]["attempt"] == 1
