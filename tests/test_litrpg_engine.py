from podcastfy.litrpg.config import LitRPGConfig, load_litrpg_config
from podcastfy.litrpg.engine import LitRPGEngine
from podcastfy.litrpg.prompts import (
    ROLE_TAGS,
    build_audio_script_prompt,
    build_episode_outline_prompt,
)


def test_prompt_templates_include_roles_and_litrpg_mechanics():
    outline_prompt = build_episode_outline_prompt(
        premise="A chef wakes as a dungeon tank.",
        episode_number=2,
        minutes=15,
        tone="tense and funny",
        prior_state={"hero_level": 3},
        callbacks=["the cursed soup ladle"],
    )
    script_prompt = build_audio_script_prompt(
        outline="Scene 1: SYSTEM grants a quest. Scene 2: BOSS interrupts.",
        episode_number=2,
        minutes=15,
        tone="tense and funny",
        prior_state={"hero_level": 3},
    )

    combined = f"{outline_prompt}\n{script_prompt}"
    assert len(ROLE_TAGS) >= 15
    for role in ROLE_TAGS:
        assert role in combined
    for mechanic in ["XP", "loot", "class", "skill", "quest", "cliffhanger"]:
        assert mechanic in combined
    assert "short exchanges" in combined
    assert "spoken cadence" in outline_prompt
    assert "audio first" in script_prompt


def test_load_litrpg_config_reads_package_defaults():
    config = load_litrpg_config()

    assert config.minutes > 0
    assert "cliffhanger" in config.episode_structure
    assert set(ROLE_TAGS).issubset(config.cast_roles)
    assert set(ROLE_TAGS).issubset(config.voices)
    assert config.voices["SYSTEM"]["voice"] == "onyx"
    assert config.voices["SYSTEM"]["model"] == "gpt-4o-mini-tts"
    assert config.voice_processing["SYSTEM"]["chain"] == "announcer_broadcast"
    assert (
        config.voice_effects_metadata()["voice_processing"]["SYSTEM"]["chain"]
        == "announcer_broadcast"
    )
    assert "notification" in config.effects


def test_engine_orchestrates_state_generation_storage_and_tts():
    calls = []

    class FakeStateStore:
        def load_state(self, *, episode_number):
            calls.append(("load_state", episode_number))
            return {"hero_level": 4, "last_loot": "Moonlit Pan"}

    class FakeLLM:
        def generate(self, *, prompt, stage):
            calls.append(("generate", stage))
            assert "NARRATOR" in prompt
            assert "SYSTEM" in prompt
            if stage == "outline":
                assert "loot" in prompt
                return "Outline: SYSTEM grants a quest; BOSS arrives."
            assert "Outline: SYSTEM grants a quest" in prompt
            return "<NARRATOR>The gate hums.</NARRATOR><SYSTEM>Quest updated.</SYSTEM><HERO>I step in.</HERO>"

    class FakeEpisodeStore:
        def save_bundle(self, bundle):
            calls.append(("save_bundle", bundle["episode_id"]))
            assert bundle["script"].startswith("<NARRATOR>")
            return {"bundle_path": "memory://episode-0007"}

    class FakeTTSRenderer:
        def render_episode(self, bundle):
            calls.append(("render_episode", bundle["episode_id"]))
            assert "<SYSTEM>" in bundle["script"]
            return {"audio_path": "memory://episode-0007.mp3"}

    engine = LitRPGEngine(
        llm=FakeLLM(),
        state_store=FakeStateStore(),
        episode_store=FakeEpisodeStore(),
        tts_renderer=FakeTTSRenderer(),
        config=LitRPGConfig(minutes=12, tone="bright peril"),
    )

    result = engine.generate_episode(
        premise="A baker becomes a shield mage.",
        episode_number=7,
    )

    assert calls == [
        ("load_state", 7),
        ("generate", "outline"),
        ("generate", "script"),
        ("save_bundle", "episode-0007"),
        ("render_episode", "episode-0007"),
    ]
    assert result["episode_id"] == "episode-0007"
    assert result["episode_number"] == 7
    assert result["storage_metadata"] == {"bundle_path": "memory://episode-0007"}
    assert result["audio_metadata"] == {"audio_path": "memory://episode-0007.mp3"}
    assert result["state"]["last_loot"] == "Moonlit Pan"


def test_engine_replays_existing_bundle_without_llm_or_tts():
    calls = []

    class ExplodingLLM:
        def generate(self, *, prompt, stage):
            raise AssertionError("LLM should not be called for replay")

    class FakeEpisodeStore:
        def find_existing_bundle(self, payload):
            calls.append(("find_existing_bundle", payload["series_id"]))
            return {"bundle_path": "memory://episode-003", "replayed": True}

    class ExplodingTTS:
        def render_episode(self, bundle):
            raise AssertionError("TTS should not be called for replay")

    engine = LitRPGEngine(
        llm=ExplodingLLM(),
        episode_store=FakeEpisodeStore(),
        tts_renderer=ExplodingTTS(),
        config=LitRPGConfig(minutes=10, tone="wry"),
    )

    result = engine.generate_episode(
        premise="A clerk enters a dungeon.",
        series_id="paper-cuts",
        episode_number=3,
    )

    assert calls == [("find_existing_bundle", "paper-cuts")]
    assert result["replayed"] is True
    assert result["storage_metadata"]["bundle_path"] == "memory://episode-003"
