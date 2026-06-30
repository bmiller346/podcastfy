import json
import math
import struct
import wave
from pathlib import Path

from podcastfy.litrpg import generate_litrpg_audio_episode
from podcastfy.litrpg.effect_log import effect_log_path, read_effect_log


class FakeLLM:
    def __init__(self):
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append(stage)
        if stage == "outline":
            return "Outline: SYSTEM grants loot; BOSS interrupts."
        return (
            "<NARRATOR>The filing cabinet opened.</NARRATOR>"
            "<SYSTEM>Quest: Survive onboarding. Loot gained: mana flask. +25 XP. "
            "XP total: 25. Skill unlocked: Spark.</SYSTEM>"
            "<HERO>I activate Spark and consume mana flask.</HERO>"
        )


class ExplodingLLM:
    def generate(self, *, prompt, stage):
        raise AssertionError("LLM should not be called during replay")


class FakeTTS:
    def __init__(self):
        self.calls = []

    def convert_script_to_speech(
        self, script, output_file, voice_map, role_tags=None, role_instructions=None
    ):
        self.calls.append((script, output_file, voice_map, role_tags, role_instructions))
        Path(output_file).write_bytes(b"fake-audio")


class SequenceWaveTTS:
    def __init__(self, amplitudes):
        self.amplitudes = list(amplitudes)
        self.calls = []

    def convert_script_to_speech(
        self, script, output_file, voice_map, role_tags=None, role_instructions=None
    ):
        self.calls.append((script, output_file, voice_map, role_tags, role_instructions))
        amplitude = self.amplitudes[min(len(self.calls) - 1, len(self.amplitudes) - 1)]
        _write_tone(Path(output_file), amplitude=amplitude)


def test_pipeline_generates_bundle_audio_and_state(tmp_path):
    llm = FakeLLM()
    tts = FakeTTS()

    result = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=llm,
        tts=tts,
    )

    bundle_path = Path(result["storage_metadata"]["bundle_path"])
    audio_path = Path(result["audio_metadata"]["audio_path"])

    assert llm.calls == ["outline", "script"]
    assert len(tts.calls) == 1
    assert result["series_id"] == "paper-cuts"
    assert result["episode_number"] == 1
    assert (bundle_path / "prompt.txt").exists()
    assert (bundle_path / "script.xml").exists()
    assert audio_path.exists()
    assert audio_path.read_bytes() == b"fake-audio"
    assert (bundle_path / "audio_metadata.json").exists()
    state_path = tmp_path / "series" / "paper-cuts" / "series_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["character"]["stats"]["xp"] == 25
    assert state["character"]["skills"] == ["Spark"]
    assert state["character"]["inventory"] == []
    effect_log = (tmp_path / "series" / "paper-cuts" / "effect_log.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"stage": "audio_render"' in effect_log
    assert '"status": "committed"' in effect_log


def test_pipeline_replays_existing_bundle_without_llm_or_tts(tmp_path):
    first_tts = FakeTTS()
    first = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=first_tts,
    )

    replay = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=ExplodingLLM(),
        tts=FakeTTS(),
    )

    assert replay["replayed"] is True
    assert replay["episode_id"] == first["episode_id"]
    assert replay["episode_number"] == first["episode_number"]
    assert replay["storage_metadata"]["bundle_path"] == first["storage_metadata"]["bundle_path"]
    assert replay["audio_metadata"]["audio_path"] == first["audio_metadata"]["audio_path"]


def test_pipeline_uses_tts_options_for_provider_config(tmp_path, monkeypatch):
    captured = {}

    class CapturingTextToSpeech:
        def __init__(self, model, api_key, conversation_config):
            captured["model"] = model
            captured["api_key"] = api_key
            captured["conversation_config"] = conversation_config

        def convert_script_to_speech(self, script, output_file, voice_map, role_tags=None, role_instructions=None):
            Path(output_file).write_bytes(b"audio")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-openai")
    monkeypatch.setattr("podcastfy.text_to_speech.TextToSpeech", CapturingTextToSpeech)

    generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="provider-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts_options={
            "provider": "openai",
            "model": "gpt-4o-mini-tts",
            "format": "mp3",
        },
    )

    assert captured["model"] == "openai"
    assert captured["api_key"] == "sk-env-openai"
    assert captured["conversation_config"]["text_to_speech"]["openai"]["model"] == "gpt-4o-mini-tts"


def test_pipeline_uses_settings_default_provider(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.local.json"
    settings_path.write_text(
        '{"default_tts_provider":"openai","default_tts_model":"gpt-4o-mini-tts","openai_api_key":"sk-settings-key"}',
        encoding="utf-8",
    )
    captured = {}

    class CapturingTextToSpeech:
        def __init__(self, model, api_key, conversation_config):
            captured["model"] = model
            captured["api_key"] = api_key
            captured["conversation_config"] = conversation_config

        def convert_script_to_speech(self, script, output_file, voice_map, role_tags=None, role_instructions=None):
            Path(output_file).write_bytes(b"audio")

    monkeypatch.setattr("podcastfy.text_to_speech.TextToSpeech", CapturingTextToSpeech)

    generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="settings-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        settings_path=settings_path,
    )

    assert captured["model"] == "openai"
    assert captured["api_key"] == "sk-settings-key"


def test_pipeline_regenerates_when_audio_required_but_missing(tmp_path):
    first = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        render_audio=False,
    )
    tts = FakeTTS()

    second = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="paper-cuts",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_audio=True,
    )

    assert "replayed" not in second
    assert second["storage_metadata"]["bundle_path"] == first["storage_metadata"]["bundle_path"]
    assert len(tts.calls) == 1


def test_render_retry_disabled_keeps_one_tts_call(tmp_path):
    tts = SequenceWaveTTS([0, 9000])

    result = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="retry-none",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={
            "enabled": True,
            "max_attempts": 3,
            "retry_below_score": 0.72,
            "retry_strategy": "none",
        },
    )

    assert len(tts.calls) == 1
    assert result["render_loop"]["auto_retry_enabled"] is False
    assert len(result["render_feedback"]) == 1


def test_same_directive_retries_low_score_up_to_max_attempts(tmp_path):
    tts = SequenceWaveTTS([0, 0, 0])

    result = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="retry-same",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={
            "enabled": True,
            "max_attempts": 3,
            "retry_below_score": 0.72,
            "retry_strategy": "same_directive",
        },
        performance_directives=[{"intensity": 0.4}],
    )

    assert len(tts.calls) == 3
    assert [item["attempt"] for item in result["render_feedback"]] == [1, 2, 3]
    assert result["render_loop"]["auto_retry_enabled"] is True
    assert sum(1 for item in result["render_feedback"] if item["selected"]) == 1


def test_highest_score_attempt_is_selected_and_copied_to_final_path(tmp_path):
    tts = SequenceWaveTTS([0, 9000, 0])

    result = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="retry-best",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={
            "enabled": True,
            "max_attempts": 3,
            "retry_below_score": 0.99,
            "retry_strategy": "same_directive",
        },
        performance_directives=[{"intensity": 0.4}],
    )

    selected = [item for item in result["render_feedback"] if item["selected"]][0]
    audio_path = Path(result["audio_metadata"]["audio_path"])

    assert len(tts.calls) == 3
    assert selected["attempt"] == 2
    assert audio_path.name == "final.mp3"
    assert audio_path.exists()
    assert Path(result["audio_metadata"]["selected_attempt_audio_path"]).name == "final_attempt_002.mp3"


def test_deterministic_adjustment_retries_with_changed_directive(tmp_path):
    tts = SequenceWaveTTS([0, 9000])

    result = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="retry-adjust",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={
            "enabled": True,
            "max_attempts": 2,
            "retry_below_score": 0.72,
            "retry_strategy": "deterministic_adjustment",
        },
        performance_directives=[
            {"intensity": 0.5, "pause_before_ms": 1000, "pause_after_ms": 500}
        ],
    )

    second_directive = result["render_feedback"][1]["directive"]
    assert len(tts.calls) == 2
    assert second_directive["intensity"] > 0.5
    assert second_directive["pause_before_ms"] == 800
    assert second_directive["pause_after_ms"] == 400


def test_invalid_adjusted_directive_stops_retry(tmp_path, monkeypatch):
    import podcastfy.litrpg.pipeline as pipeline

    def invalid_retry_directive(directive, feedback, attempt):
        return {**dict(directive), "intensity": 1.5}

    monkeypatch.setattr(pipeline, "build_retry_directive", invalid_retry_directive)
    tts = SequenceWaveTTS([0, 9000, 9000])

    result = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="retry-invalid",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={
            "enabled": True,
            "max_attempts": 3,
            "retry_below_score": 0.72,
            "retry_strategy": "deterministic_adjustment",
        },
        performance_directives=[{"intensity": 0.5}],
    )

    assert len(tts.calls) == 1
    assert "retry stopped: adjusted directive invalid" in " ".join(result["render_feedback"][0]["notes"])


def test_render_retry_effect_log_includes_attempt_metadata(tmp_path):
    tts = SequenceWaveTTS([0, 9000])

    result = generate_litrpg_audio_episode(
        premise="A clerk discovers the office is a dungeon.",
        series_id="retry-effects",
        storage_dir=tmp_path,
        llm=FakeLLM(),
        tts=tts,
        render_loop={
            "enabled": True,
            "max_attempts": 2,
            "retry_below_score": 0.72,
            "retry_strategy": "same_directive",
        },
        performance_directives=[{"intensity": 0.4}],
    )

    entries = read_effect_log(effect_log_path(tmp_path, "retry-effects"))
    attempts = [
        entry
        for entry in entries
        if entry.stage == "audio_render" and entry.metadata.get("attempt") in {1, 2}
    ]

    assert len(attempts) >= 2
    assert {entry.metadata["attempt"] for entry in attempts} >= {1, 2}
    assert any(entry.metadata.get("selected_attempt") == 2 for entry in attempts)
    assert result["render_feedback"][1]["selected"] is True


def _write_tone(path: Path, *, amplitude: int, sample_rate: int = 24000) -> None:
    samples = [
        int(amplitude * math.sin(2 * math.pi * 440 * index / sample_rate))
        for index in range(sample_rate)
    ]
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
