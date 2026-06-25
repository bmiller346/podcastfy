import json

from podcastfy.litrpg import CharacterState, EpisodeConfig, EpisodeStore
from podcastfy.litrpg import QuestState, ScriptLine, SeriesState
from podcastfy.litrpg import STATE_SCHEMA_VERSION
from podcastfy.litrpg import load_series_state, next_episode_number
from podcastfy.litrpg import save_series_state, stable_cache_key


def test_series_state_round_trip(tmp_path):
    series_dir = tmp_path / "ember-keep"
    state = SeriesState(
        series_id="ember-keep",
        title="Ember Keep",
        episode_number=3,
        character=CharacterState(
            name="Mara",
            level=4,
            character_class="Rune Knight",
            stats={"strength": 12, "wisdom": 8},
            skills=["Shield Bash"],
            inventory=["Iron Key"],
        ),
        quests=[QuestState(title="Find the Gate", status="active", notes="Below town")],
        current_location="Old Well",
        memory=["Mara distrusts the mayor."],
    )

    save_series_state(series_dir, state)
    loaded = load_series_state(series_dir)

    assert loaded == state
    assert next_episode_number(loaded) == 4
    raw = (series_dir / "series_state.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    raw_state = json.loads(raw)
    assert raw_state["series_id"] == "ember-keep"
    assert raw_state["schema_version"] == STATE_SCHEMA_VERSION


def test_load_series_state_returns_default_when_missing(tmp_path):
    state = load_series_state(tmp_path / "new-series")

    assert state.series_id == "new-series"
    assert state.title == "New Series"
    assert state.episode_number == 0
    assert state.character.name == "Hero"
    assert state.schema_version == STATE_SCHEMA_VERSION


def test_stable_cache_key_ignores_dict_order():
    prompt = "Clear the cellar dungeon."
    first = EpisodeConfig(
        prompt=prompt,
        minutes=12,
        tone="tense",
        cast={"narrator": "calm", "hero": "bright"},
        tts_model="local",
        model_version="v1",
    )
    second = EpisodeConfig(
        prompt=prompt,
        minutes=12,
        tone="tense",
        cast={"hero": "bright", "narrator": "calm"},
        tts_model="local",
        model_version="v1",
    )

    assert stable_cache_key(prompt, first) == stable_cache_key(prompt, second)
    assert stable_cache_key(prompt, first) != stable_cache_key("A different prompt", first)


def test_episode_bundle_creation_writes_expected_files(tmp_path):
    store = EpisodeStore(tmp_path)
    config = EpisodeConfig(
        prompt="A secret market opens under the inn.",
        minutes=8,
        tone="wry",
        cast={"narrator": "warm", "Mara": "dry"},
    )

    bundle = store.create_bundle(
        series_id="ember-keep",
        episode_number=1,
        prompt=config.prompt,
        config=config,
        outline={"beats": ["wake", "haggle", "duel"]},
        script=[ScriptLine(role="Narrator", text="The inn floorboards sighed.")],
        metadata={"status": "draft"},
    )

    episode_dir = tmp_path / "episodes" / "ember-keep" / "episode-0001"
    assert bundle.paths["episode_dir"] == str(episode_dir)
    assert (episode_dir / "prompt.txt").read_text(encoding="utf-8") == config.prompt
    assert json.loads((episode_dir / "config.json").read_text(encoding="utf-8"))[
        "minutes"
    ] == 8
    assert json.loads((episode_dir / "outline.json").read_text(encoding="utf-8"))[
        "beats"
    ] == ["wake", "haggle", "duel"]
    assert json.loads((episode_dir / "script.json").read_text(encoding="utf-8"))[0][
        "role"
    ] == "Narrator"
    metadata = json.loads((episode_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["cache_key"] == bundle.cache_key
    assert metadata["status"] == "draft"


def test_existing_cache_lookup(tmp_path):
    store = EpisodeStore(tmp_path)
    config = EpisodeConfig(
        prompt="The tutorial slime returns.",
        minutes=5,
        tone="light",
        cast={"narrator": "warm"},
    )
    created = store.create_bundle(
        series_id="ember-keep",
        episode_number=2,
        prompt=config.prompt,
        config=config,
        script="<script><line role=\"Narrator\">Again?</line></script>",
    )

    found = store.find_by_cache_key("ember-keep", created.cache_key)

    assert found is not None
    assert found.episode_id == "episode-0002"
    assert found.cache_key == created.cache_key
    assert found.config == config
    assert found.paths["script"].endswith("script.xml")
    assert store.find_by_cache_key("ember-keep", "missing") is None


def test_engine_payload_cache_includes_production_config(tmp_path):
    store = EpisodeStore(tmp_path)
    payload = {
        "series_id": "ember-keep",
        "episode_number": 1,
        "premise": "The cellar becomes a dungeon.",
        "config": {
            "minutes": 8,
            "tone": "wry",
            "cast_roles": {"NARRATOR": "warm"},
            "voices": {"NARRATOR": {"voice": "voice-a"}},
            "effects": {"notification": "ping"},
            "episode_structure": ["cold_open", "cliffhanger"],
        },
        "outline": "Outline",
        "script": "<NARRATOR>Begin.</NARRATOR>",
    }

    saved = store.save_bundle(payload)
    found = store.find_existing_bundle(payload)
    changed_voice = {
        **payload,
        "config": {
            **payload["config"],
            "voices": {"NARRATOR": {"voice": "voice-b"}},
        },
    }

    assert found is not None
    assert found["cache_key"] == saved["cache_key"]
    assert store.find_existing_bundle(changed_voice) is None
