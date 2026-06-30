import json
from pathlib import Path

from podcastfy.litrpg import generate_litrpg_audio_episode


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
