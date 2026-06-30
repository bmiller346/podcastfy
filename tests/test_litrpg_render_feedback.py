import json
import math
import struct
import wave
from pathlib import Path

from podcastfy.litrpg.pipeline import generate_litrpg_audio_episode
from podcastfy.litrpg.render_feedback import RenderFeedback
from podcastfy.litrpg.render_feedback import build_retry_directive
from podcastfy.litrpg.render_feedback import build_directive_revision_prompt
from podcastfy.litrpg.render_feedback import directive_validation_to_dict
from podcastfy.litrpg.render_feedback import parse_directive_revision
from podcastfy.litrpg.render_feedback import render_feedback_to_dict
from podcastfy.litrpg.render_feedback import score_rendered_audio
from podcastfy.litrpg.render_feedback import validate_directive


class FakeLLM:
    def generate(self, *, prompt, stage):
        if stage == "outline":
            return "Outline: SYSTEM announces a safe test."
        return "<NARRATOR>Begin.</NARRATOR><SYSTEM>Quest accepted.</SYSTEM>"


class FakeTTS:
    def __init__(self):
        self.calls = []

    def convert_script_to_speech(
        self, script, output_file, voice_map, role_tags=None, role_instructions=None
    ):
        self.calls.append((script, output_file, voice_map, role_tags, role_instructions))
        Path(output_file).write_bytes(b"fake-audio")


def test_valid_directive_passes():
    validation = validate_directive(
        {
            "intensity": 0.65,
            "pause_before_ms": 250,
            "pause_after_ms": 500,
            "pace": "measured",
            "register": "bureaucratic_default",
        }
    )

    assert validation.valid is True
    assert validation.reason == ""


def test_invalid_intensity_fails():
    validation = validate_directive({"intensity": 1.2})

    assert validation.valid is False
    assert "intensity" in validation.reason


def test_inner_monologue_over_point_85_fails():
    validation = validate_directive({"register": "inner_monologue", "intensity": 0.9})

    assert validation.valid is False
    assert "inner monologue" in validation.reason


def test_urgent_void_or_memory_scene_fails():
    validation = validate_directive({"scene_type": "void", "pace": "urgent"})

    assert validation.valid is False
    assert "void/memory" in validation.reason


def test_pause_over_2000ms_fails():
    validation = validate_directive({"pause_after_ms": 2001})

    assert validation.valid is False
    assert "pause_after_ms" in validation.reason


def test_provider_specific_distortion_risk_and_unknown_options():
    distortion = validate_directive(
        {"exaggeration": 0.99},
        provider="chatterbox",
    )
    openai_warning = validate_directive(
        {"voice": "mystery-voice", "model": "unknown-model"},
        provider="openai",
    )

    assert distortion.valid is False
    assert "Chatterbox" in distortion.reason
    assert openai_warning.valid is True
    assert "unknown OpenAI voice" in openai_warning.warnings[0]
    assert "unknown OpenAI model" in openai_warning.warnings[1]


def test_scoring_silent_audio_produces_low_score_and_human_review(tmp_path):
    audio_path = tmp_path / "silent.wav"
    _write_wav(audio_path, [0] * 24000)

    feedback = score_rendered_audio(
        audio_path,
        segment_id="chapter_001_part_001",
        segment_text="This should have audible speech.",
    )

    assert feedback.score < 0.72
    assert feedback.verdict == "needs_review"
    assert feedback.human_review_required is True
    assert feedback.rms_db is not None
    assert feedback.silence_ratio == 1.0


def test_scoring_normal_synthetic_audio_is_accepted(tmp_path):
    audio_path = tmp_path / "tone.wav"
    samples = [
        int(9000 * math.sin(2 * math.pi * 440 * index / 24000))
        for index in range(24000)
    ]
    _write_wav(audio_path, samples)

    feedback = score_rendered_audio(
        audio_path,
        segment_id="chapter_001_part_001",
        expected_duration_seconds=1.0,
        segment_text="A normal audible line plays here.",
    )

    assert feedback.score >= 0.72
    assert feedback.verdict == "accepted"
    assert feedback.human_review_required is False
    assert feedback.duration_seconds == 1.0


def test_serialization_shape_is_stable(tmp_path):
    validation = validate_directive({"intensity": 0.5})
    audio_path = tmp_path / "tone.wav"
    _write_wav(audio_path, [1000] * 24000)
    feedback = score_rendered_audio(audio_path, segment_id="segment-1")

    assert directive_validation_to_dict(validation) == {
        "valid": True,
        "reason": "",
        "warnings": [],
    }
    payload = render_feedback_to_dict(feedback)
    assert set(payload) == {
        "segment_id",
        "attempt",
        "provider",
        "model",
        "peak_db",
        "rms_db",
        "silence_ratio",
        "duration_seconds",
        "clipping_detected",
        "tts_valley_risk",
        "score",
        "verdict",
        "human_review_required",
        "notes",
    }


def test_pipeline_with_render_loop_disabled_behaves_as_before(tmp_path):
    tts = FakeTTS()

    result = generate_litrpg_audio_episode(
        premise="A clerk tests audio.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={"enabled": False},
    )

    assert len(tts.calls) == 1
    assert "render_feedback" not in result
    assert "render_loop" not in result


def test_pipeline_with_render_loop_enabled_includes_feedback(tmp_path):
    tts = FakeTTS()

    result = generate_litrpg_audio_episode(
        premise="A clerk tests audio.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={"enabled": True, "max_attempts": 3, "retry_below_score": 0.72},
    )

    assert len(tts.calls) == 1
    assert result["render_loop"] == {
        "enabled": True,
        "max_attempts": 3,
        "retry_below_score": 0.72,
        "retry_strategy": "none",
        "llm_revision_enabled": False,
        "auto_retry_enabled": False,
    }
    assert result["render_feedback"][0]["segment_id"] == "paper-cuts_episode_001"
    assert result["render_feedback"][0]["human_review_required"] is True
    assert result["render_feedback"][0]["verdict"] == "needs_review"
    metadata = json.loads(
        Path(result["audio_metadata"]["audio_metadata_path"]).read_text(encoding="utf-8")
    )
    assert metadata["render_feedback"] == result["render_feedback"]
    assert metadata["render_loop"] == result["render_loop"]


def test_invalid_directive_does_not_call_fake_tts(tmp_path):
    tts = FakeTTS()

    result = generate_litrpg_audio_episode(
        premise="A clerk tests audio.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={"enabled": True},
        performance_directives=[{"intensity": 1.1}],
    )

    assert tts.calls == []
    assert result["audio_metadata"]["status"] == "directive_invalid"
    assert result["render_feedback"][0]["verdict"] == "directive_invalid"
    assert result["render_feedback"][0]["human_review_required"] is True
    assert Path(result["audio_metadata"]["audio_metadata_path"]).exists()


def test_task_config_passes_render_loop_and_writes_result(tmp_path):
    task_path = tmp_path / "task.json"
    task_path.write_text(
        json.dumps(
            {
                "series_id": "paper-cuts",
                "premise": "A clerk tests audio.",
                "storage_dir": "library",
                "result_path": "result.json",
                "render_audio": True,
                "outline": "Outline",
                "script": "<NARRATOR>Begin.</NARRATOR>",
                "render_loop": {"enabled": True, "max_attempts": 2},
                "directives": [{"intensity": 1.1}],
            }
        ),
        encoding="utf-8",
    )

    from podcastfy.litrpg.task import run_litrpg_task

    tts = FakeTTS()
    result = run_litrpg_task(task_path, tts=tts)
    written = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))

    assert tts.calls == []
    assert result["render_loop"]["auto_retry_enabled"] is False
    assert written["render_feedback"][0]["verdict"] == "directive_invalid"


def test_task_config_accepts_named_performance_directive_map(tmp_path):
    task_path = tmp_path / "task.json"
    task_path.write_text(
        json.dumps(
            {
                "series_id": "paper-cuts",
                "premise": "A clerk tests audio.",
                "storage_dir": "library",
                "render_audio": True,
                "outline": "Outline",
                "script": "<NARRATOR>Begin.</NARRATOR>",
                "render_loop": {"enabled": True},
                "performance_directives": {
                    "default": {"intensity": 0.55, "pace": "steady"}
                },
            }
        ),
        encoding="utf-8",
    )

    from podcastfy.litrpg.task import run_litrpg_task

    tts = FakeTTS()
    result = run_litrpg_task(task_path, tts=tts)

    assert len(tts.calls) == 1
    assert result["render_feedback"][0]["directive"] == {
        "id": "default",
        "intensity": 0.55,
        "pace": "steady",
    }


def test_build_retry_directive_increases_intensity_for_valley_risk():
    feedback = _feedback(tts_valley_risk=True, score=0.2)

    directive = build_retry_directive({"intensity": 0.5, "custom": "keep"}, feedback, 2)

    assert directive["intensity"] == 0.6
    assert directive["custom"] == "keep"
    assert directive["retry_attempt"] == 2
    assert directive["retry_source"] == "deterministic_adjustment"


def test_build_retry_directive_reduces_long_pauses_for_silence_risk():
    feedback = _feedback(silence_ratio=0.9, score=0.2)

    directive = build_retry_directive(
        {"pause_before_ms": 1000, "pause_after_ms": 500},
        feedback,
        3,
    )

    assert directive["pause_before_ms"] == 800
    assert directive["pause_after_ms"] == 400


def test_directive_revision_prompt_contains_feedback_constraints_and_history():
    feedback = _feedback(score=0.31, verdict="needs_review")

    prompt = build_directive_revision_prompt(
        "Do not change this line.",
        {"intensity": 0.4, "custom": "keep"},
        feedback,
        history=[{"attempt": 1, "score": 0.2}, {"attempt": 2, "score": 0.31}],
        constraints={"provider": "edge"},
    )

    assert "Return valid JSON only" in prompt
    assert "Do not change this line." in prompt
    assert '"score": 0.31' in prompt
    assert "do_not_change_segment_text" in prompt
    assert "preserve_unknown_directive_keys_unless_unsafe" in prompt
    assert '"attempt": 2' in prompt
    assert '"provider": "edge"' in prompt


def test_parse_directive_revision_accepts_plain_and_fenced_json():
    plain = parse_directive_revision('{"directive":{"intensity":0.6},"reason":"quieter","risk_notes":["none"]}')
    fenced = parse_directive_revision(
        '```json\n{"directive":{"pause_after_ms":100},"reason":"trim pause"}\n```'
    )

    assert plain["directive"]["intensity"] == 0.6
    assert plain["reason"] == "quieter"
    assert fenced["directive"]["pause_after_ms"] == 100


def test_parse_directive_revision_rejects_missing_or_non_dict_directive():
    try:
        parse_directive_revision('{"reason":"missing"}')
    except ValueError as exc:
        assert "requires a directive" in str(exc)
    else:
        raise AssertionError("missing directive should fail")

    try:
        parse_directive_revision('{"directive":["bad"]}')
    except ValueError as exc:
        assert "directive must be a JSON object" in str(exc)
    else:
        raise AssertionError("non-dict directive should fail")


def _feedback(**overrides):
    values = {
        "segment_id": "segment-1",
        "attempt": 1,
        "provider": "edge",
        "model": "edge",
        "peak_db": -3.0,
        "rms_db": -20.0,
        "silence_ratio": 0.0,
        "duration_seconds": 1.0,
        "clipping_detected": False,
        "tts_valley_risk": False,
        "score": 0.5,
        "verdict": "needs_review",
        "human_review_required": True,
        "notes": [],
    }
    values.update(overrides)
    return RenderFeedback(**values)


def _write_wav(path: Path, samples: list[int], *, sample_rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
