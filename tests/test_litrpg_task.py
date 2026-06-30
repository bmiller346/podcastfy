import json
from pathlib import Path

import pytest

from podcastfy.litrpg.bible import CharacterBibleEntry, StoryBible, save_story_bible
from podcastfy.litrpg.continuity import ContinuityLedger, EconomyAnchor, EmotionalArc
from podcastfy.litrpg.continuity import EmotionalArcRegistry, EntityEcology, LedgerEntry
from podcastfy.litrpg.continuity import LocationDetail, RuleEntry, WorldRegister
from podcastfy.litrpg.continuity import save_continuity_ledger
from podcastfy.litrpg.continuity import save_emotional_arcs, save_world_register
from podcastfy.litrpg.foreshadowing import ForeshadowEntry, ForeshadowLedger
from podcastfy.litrpg.foreshadowing import save_foreshadow_ledger
from podcastfy.litrpg.models import CharacterState, SeriesState
from podcastfy.litrpg.series_architect import ChapterOutlineEntry, SeriesShape
from podcastfy.litrpg.series_architect import bootstrap_series, save_chapter_outline
from podcastfy.litrpg.state_store import save_series_state
from podcastfy.litrpg.task import load_litrpg_task, run_litrpg_task, run_litrpg_task_data
from podcastfy.litrpg.task import _llm_from_task
from podcastfy.litrpg.voice_cards import VoiceCard, VoiceCardDeck, save_voice_cards


REPO_ROOT = Path(__file__).resolve().parents[1]
EPISODE_EXAMPLE = REPO_ROOT / "usage" / "litrpg_task.example.json"
CHAPTER_EXAMPLE = REPO_ROOT / "usage" / "litrpg_chapter_task.example.json"


class FakeTTS:
    def __init__(self):
        self.calls = []

    def convert_script_to_speech(
        self, script, output_file, voice_map, role_tags=None, role_instructions=None
    ):
        self.calls.append((script, output_file, voice_map, role_tags, role_instructions))
        Path(output_file).write_bytes(b"task-audio")


class SmokeChapterLLM:
    def __init__(self):
        self.calls = []
        self.script = "".join(
            f"<{role}>{role} reports XP, loot, quest, skill, and inventory.</{role}>"
            for role in [
                "NARRATOR",
                "HERO",
                "SYSTEM",
                "SIDEKICK",
                "MINION",
                "RIVAL",
                "HEALER",
                "TANK",
                "ROGUE",
                "MAGE",
                "GUIDE",
                "MERCHANT",
                "MENTOR",
                "BOSS",
                "BEAST",
                "VILLAIN",
            ]
        )

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        if stage.startswith("part:") or stage.startswith("revise:"):
            return self.script
        return f"{stage} ok"


def _write_task(tmp_path, **overrides):
    task = {
        "series_id": "paper-cuts",
        "premise": "A clerk discovers the office is a dungeon.",
        "storage_dir": "library",
        "result_path": "last_result.json",
        "render_audio": True,
        "outline": "Outline: SYSTEM grants a quest.",
        "script": "<NARRATOR>Begin.</NARRATOR><SYSTEM>Quest accepted.</SYSTEM>",
        "litrpg_config": {"minutes": 4, "tone": "wry"},
    }
    task.update(overrides)
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    return task_path


def test_load_litrpg_task_requires_json_object(tmp_path):
    task_path = tmp_path / "task.json"
    task_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        load_litrpg_task(task_path)


def test_run_litrpg_task_uses_inline_script_and_writes_result(tmp_path):
    task_path = _write_task(tmp_path)
    tts = FakeTTS()

    result = run_litrpg_task(task_path, tts=tts)

    result_path = tmp_path / "last_result.json"
    audio_path = Path(result["audio_metadata"]["audio_path"])

    assert len(tts.calls) == 1
    assert result["series_id"] == "paper-cuts"
    assert result["episode_number"] == 1
    assert audio_path.exists()
    assert audio_path.read_bytes() == b"task-audio"
    assert json.loads(result_path.read_text(encoding="utf-8"))["series_id"] == "paper-cuts"


def test_run_litrpg_task_passes_tts_provider_options(tmp_path, monkeypatch):
    task_path = _write_task(
        tmp_path,
        tts={"provider": "openai", "model": "gpt-4o-mini-tts", "format": "mp3"},
    )
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"series_id": kwargs["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_audio_episode", fake_generate)

    result = run_litrpg_task(task_path, tts=FakeTTS())

    assert result == {"series_id": "paper-cuts"}
    assert captured["tts_options"]["provider"] == "openai"


def test_run_litrpg_task_replays_inline_script_without_rendering_again(tmp_path):
    task_path = _write_task(tmp_path)
    first_tts = FakeTTS()
    first = run_litrpg_task(task_path, tts=first_tts)
    second_tts = FakeTTS()

    replay = run_litrpg_task(task_path, tts=second_tts)

    assert replay["replayed"] is True
    assert replay["episode_id"] == first["episode_id"]
    assert replay["audio_metadata"]["audio_path"] == first["audio_metadata"]["audio_path"]
    assert second_tts.calls == []


def test_run_litrpg_task_rejects_unknown_generation_provider(tmp_path):
    task_path = _write_task(
        tmp_path,
        outline="",
        script="",
        generation={"provider": "unknown"},
    )

    with pytest.raises(ValueError, match="generation.provider=openai, generation.provider=gemini"):
        run_litrpg_task(task_path, tts=FakeTTS())


def test_llm_from_task_builds_ollama_generator_from_generation_config():
    llm = _llm_from_task(
        {
            "generation": {
                "provider": "ollama",
                "ollama_model": "dcc-writer",
                "ollama_host": "http://127.0.0.1:11434",
                "ollama_options": {"temperature": 0.8},
                "ollama_timeout_seconds": 99,
            }
        },
        settings={},
    )

    assert llm.model == "dcc-writer"
    assert llm.host == "http://127.0.0.1:11434"
    assert llm.options == {"temperature": 0.8}
    assert llm.timeout_seconds == 99


def test_llm_from_task_uses_ollama_base_url_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11435")

    llm = _llm_from_task({"generation": {"provider": "ollama"}}, settings={})

    assert llm.host == "http://localhost:11435"


def test_llm_from_task_builds_hybrid_router_with_custom_stage_rules(monkeypatch):
    class FakeOpenAIResponsesGenerator:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(
        "podcastfy.litrpg.task.OpenAIResponsesGenerator",
        FakeOpenAIResponsesGenerator,
    )

    llm = _llm_from_task(
        {
            "generation": {
                "provider": "hybrid",
                "local_model": "dolphin3",
                "commercial_model": "gpt-5.4",
                "local_exact_stages": ["script", "announcer_lines"],
                "local_stage_prefixes": ["part:", "revise:", "voice:"],
                "allow_local_fallback": True,
            }
        },
        settings={"openai_api_key": "sk-test"},
    )

    assert llm.local.model == "dolphin3"
    assert llm.default.model == "gpt-5.4"
    assert llm.routing.local_exact == ("script", "announcer_lines")
    assert llm.routing.local_prefixes == ("part:", "revise:", "voice:")
    assert llm.allow_local_fallback is True


def test_llm_from_task_builds_hybrid_router_with_openai_intent_routing(monkeypatch):
    class FakeOpenAIResponsesGenerator:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(
        "podcastfy.litrpg.llm.OpenAIResponsesGenerator",
        FakeOpenAIResponsesGenerator,
    )

    llm = _llm_from_task(
        {
            "generation": {
                "provider": "hybrid",
                "local_model": "litrpg-writer",
                "commercial_model": "gpt-5.4",
                "auto_model_routing": True,
                "cheap_model": "gpt-5.4-mini",
                "nano_model": "gpt-5.4-nano",
            }
        },
        settings={"openai_api_key": "sk-test"},
    )

    assert llm.local.model == "litrpg-writer"
    assert llm.default.strong_model == "gpt-5.4"
    assert llm.default.cheap_model == "gpt-5.4-mini"
    assert llm.default.nano_model == "gpt-5.4-nano"


def test_llm_from_task_builds_direct_gemini_generator():
    llm = _llm_from_task(
        {
            "generation": {
                "provider": "gemini",
                "model": "gemini-2.5-flash-lite",
                "temperature": 0.1,
            }
        },
        settings={"gemini_api_key": "gemini-key"},
    )

    assert llm.model == "gemini-2.5-flash-lite"
    assert llm.api_key == "gemini-key"
    assert llm.temperature == 0.1


def test_llm_from_task_builds_hybrid_router_with_gemini_commercial():
    llm = _llm_from_task(
        {
            "generation": {
                "provider": "hybrid",
                "local_model": "litrpg-writer",
                "commercial_provider": "gemini",
                "commercial_model": "gemini-2.5-flash",
                "auto_model_routing": True,
                "cheap_model": "gemini-2.5-flash-lite",
            }
        },
        settings={"gemini_api_key": "gemini-key"},
    )

    assert llm.local.model == "litrpg-writer"
    assert llm.default.strong_model == "gemini-2.5-flash"
    assert llm.default.cheap_model == "gemini-2.5-flash-lite"


def test_llm_from_task_hybrid_default_routing_keeps_planning_commercial():
    llm = _llm_from_task(
        {
            "generation": {
                "provider": "hybrid",
                "local_model": "litrpg-writer",
                "commercial_provider": "gemini",
                "commercial_model": "gemini-2.5-flash",
            }
        },
        settings={"gemini_api_key": "gemini-key"},
    )

    assert llm.routing.local_exact == ("script",)
    assert llm.routing.local_prefixes == ("part:", "revise:")
    assert llm.routing.backend_for("part:cold-open") == "local"
    assert llm.routing.backend_for("revise:cold-open") == "local"
    assert llm.routing.backend_for("premise_intake") == "default"
    assert llm.routing.backend_for("series_package") == "default"
    assert llm.routing.backend_for("chapter_review") == "default"
    assert llm.routing.backend_for("story_seed_revision") == "default"


def test_llm_from_task_rejects_unsupported_hybrid_local_provider():
    with pytest.raises(ValueError, match="local_provider=ollama"):
        _llm_from_task(
            {
                "generation": {
                    "provider": "hybrid",
                    "local_provider": "openai",
                    "commercial_provider": "gemini",
                    "commercial_model": "gemini-2.5-flash",
                }
            },
            settings={"gemini_api_key": "gemini-key"},
        )


def test_llm_from_task_rejects_unsupported_hybrid_commercial_provider():
    with pytest.raises(ValueError, match="commercial_provider currently supports openai or gemini"):
        _llm_from_task(
            {
                "generation": {
                    "provider": "hybrid",
                    "local_provider": "ollama",
                    "commercial_provider": "ollama",
                    "local_model": "litrpg-writer",
                }
            },
            settings={},
        )


def test_llm_from_task_requires_valid_gemini_key_for_gemini():
    with pytest.raises(ValueError, match="Gemini generation requires a valid API key"):
        _llm_from_task(
            {"generation": {"provider": "gemini", "model": "gemini-2.5-flash"}},
            settings={},
        )


def test_llm_from_task_requires_valid_openai_key_for_hybrid():
    with pytest.raises(ValueError, match="OpenAI generation requires a valid API key"):
        _llm_from_task(
            {
                "generation": {
                    "provider": "hybrid",
                    "local_model": "litrpg-writer",
                    "commercial_model": "gpt-5.4",
                }
            },
            settings={"openai_api_key": "not a real key"},
        )


def test_run_litrpg_task_data_uses_base_dir_for_relative_outputs(tmp_path):
    task = {
        "series_id": "paper-cuts",
        "premise": "A clerk discovers the office is a dungeon.",
        "storage_dir": "library",
        "result_path": "results/inline_result.json",
        "render_audio": True,
        "outline": "Outline: SYSTEM grants a quest.",
        "script": "<NARRATOR>Begin.</NARRATOR><SYSTEM>Quest accepted.</SYSTEM>",
    }
    tts = FakeTTS()

    result = run_litrpg_task_data(task, base_dir=tmp_path, tts=tts)

    result_path = tmp_path / "results" / "inline_result.json"
    assert result["series_id"] == "paper-cuts"
    assert len(tts.calls) == 1
    assert result_path.exists()
    assert json.loads(result_path.read_text(encoding="utf-8"))["series_id"] == "paper-cuts"


def test_run_litrpg_task_injects_story_bible_and_mechanics_context_for_chapters(tmp_path, monkeypatch):
    storage_dir = tmp_path / "library"
    series_dir = storage_dir / "series" / "paper-cuts"
    save_story_bible(
        storage_dir,
        StoryBible(
            series_id="paper-cuts",
            characters={
                "Hero": CharacterBibleEntry(
                    name="Hero",
                    never_contradict_facts=["Hero promised never to trust elevators."],
                    voice_rules=["Dry under pressure."],
                )
            },
        ),
    )
    save_series_state(
        series_dir,
        SeriesState(
            series_id="paper-cuts",
            title="Paper Cuts",
            episode_number=2,
            character=CharacterState(
                name="Hero",
                level=3,
                character_class="Intern",
                skills=["Paper Cut"],
                inventory=["mana flask"],
            ),
        ),
    )
    series_dir.mkdir(parents=True, exist_ok=True)
    (series_dir / "series_package.json").write_text(
        json.dumps(
            {
                "premise": "Office workers survive dungeon performance reviews.",
                "metadata": {
                    "title": "Paper Cuts",
                },
                "system_announcer": {
                    "name": "System Announcer",
                    "tone": "hostile corporate game-show host",
                },
            }
        ),
        encoding="utf-8",
    )
    task_path = tmp_path / "chapter_task.json"
    task_path.write_text(
        json.dumps(
            {
                "mode": "chapter",
                "series_id": "paper-cuts",
                "premise": "A clerk discovers the office is a dungeon.",
                "storage_dir": "library",
                "reviews": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_generate(task, *, llm):
        captured.update(task)
        return {"mode": "chapter", "series_id": task["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_chapter", fake_generate)

    result = run_litrpg_task(task_path, llm=object())

    assert result == {"mode": "chapter", "series_id": "paper-cuts"}
    assert "Hero promised never to trust elevators." in captured["story_bible_summary"]
    assert "Office workers survive dungeon performance reviews." in captured["series_package_summary"]
    assert "hostile corporate game-show host" in captured["series_package_summary"]
    assert captured["showrunner"]["phase"] == "The Drop"
    assert captured["showrunner"]["tension"] == 8
    assert "FRANTIC" in captured["showrunner_context"]
    assert captured["mechanics_context"]["inventory"] == ["mana flask"]
    assert captured["mechanics_context"]["skills"] == ["Paper Cut"]
    assert captured["mechanics_context"]["class"] == "Intern"


def test_run_litrpg_task_persists_validated_mechanics_deltas_for_chapters(tmp_path, monkeypatch):
    storage_dir = tmp_path / "library"
    series_dir = storage_dir / "series" / "paper-cuts"
    save_series_state(
        series_dir,
        SeriesState(
            series_id="paper-cuts",
            title="Paper Cuts",
            episode_number=2,
            character=CharacterState(
                name="Hero",
                level=3,
                character_class="Intern",
                stats={"xp": 100},
                skills=["Paper Cut"],
                inventory=["mana flask"],
            ),
        ),
    )
    task_path = tmp_path / "chapter_task.json"
    task_path.write_text(
        json.dumps(
            {
                "mode": "chapter",
                "series_id": "paper-cuts",
                "chapter_number": 3,
                "chapter_title": "The Break Room Bites Back",
                "premise": "A clerk discovers the office is a dungeon.",
                "storage_dir": "library",
            }
        ),
        encoding="utf-8",
    )

    def fake_generate(task, *, llm):
        return {
            "mode": "chapter",
            "series_id": task["series_id"],
            "chapter": {"number": 3, "title": "The Break Room Bites Back"},
            "parts": [
                {
                    "gate": {
                        "final": {
                            "mechanics": {
                                "events": [
                                    {"kind": "xp_gain", "display": "+25 XP", "amount": 25},
                                    {"kind": "loot_gain", "display": "brass key", "term": "brass key"},
                                    {"kind": "item_consumed", "display": "mana flask", "term": "mana flask"},
                                    {"kind": "skill_learned", "display": "Staple Guard", "term": "staple guard"},
                                ]
                            }
                        }
                    }
                }
            ],
        }

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_chapter", fake_generate)

    run_litrpg_task(task_path, llm=object())

    state = json.loads((series_dir / "series_state.json").read_text(encoding="utf-8"))
    assert state["episode_number"] == 3
    assert state["character"]["stats"]["xp"] == 125
    assert state["character"]["inventory"] == ["brass key"]
    assert "Staple Guard" in state["character"]["skills"]
    assert "Chapter 3: The Break Room Bites Back" in state["memory"]


def test_run_litrpg_task_injects_series_architect_chapter_contract(tmp_path, monkeypatch):
    storage_dir = tmp_path / "library"
    bootstrap_series(
        storage_dir=storage_dir,
        series_id="paper-cuts",
        shape=SeriesShape(
            target_books=1,
            chapters_per_book=8,
            series_title="Paper Cuts",
            series_promise="Office workers survive dungeon bureaucracy.",
            endgame_direction="Expose the HR System.",
            series_mysteries=["HR System origin"],
        ),
        series_arc=[
            {
                "book": 1,
                "role": "Origin and first floor survival",
                "major_change": "The clerk admits the office is a dungeon.",
                "power_ceiling": "level 10",
                "chapter_count": 8,
                "arc_style": "escalating_floor_survival",
                "must_resolve": ["first boss"],
                "must_preserve": ["HR System origin"],
            }
        ],
    )
    save_chapter_outline(
        storage_dir,
        "paper-cuts",
        1,
        [
            ChapterOutlineEntry(
                chapter=2,
                title="The Copier Has Teeth",
                premise="The copier room becomes a tutorial arena.",
                ends_on="The toner hatch opens from the inside.",
                must_not_use=["HR System origin"],
            )
        ],
    )
    task_path = tmp_path / "chapter_task.json"
    task_path.write_text(
        json.dumps(
            {
                "mode": "chapter",
                "series_id": "paper-cuts",
                "book_number": 1,
                "chapter_number": 2,
                "storage_dir": "library",
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_generate(task, *, llm):
        captured.update(task)
        return {"mode": "chapter", "series_id": task["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_chapter", fake_generate)

    run_litrpg_task(task_path, llm=object())

    assert captured["chapter_title"] == "The Copier Has Teeth"
    assert captured["premise"] == "The copier room becomes a tutorial arena."
    assert captured["chapter_contract"]["book_role"] == "Origin and first floor survival"
    assert "HR System origin" in captured["chapter_contract"]["must_not_spend"]
    assert "Chapter Contract:" in captured["showrunner_context"]
    assert captured["showrunner"]["contract_source"] == "series_architect"


def test_run_litrpg_task_injects_story_engine_storage_context(tmp_path, monkeypatch):
    storage_dir = tmp_path / "library"
    save_continuity_ledger(
        storage_dir,
        "paper-cuts",
        ContinuityLedger(
            series_id="paper-cuts",
            running_gags=[LedgerEntry(text="The copier demands tribute.", chapter=1)],
        ),
    )
    save_voice_cards(
        storage_dir,
        VoiceCardDeck(
            series_id="paper-cuts",
            cards={
                "Hero": VoiceCard(
                    name="Hero",
                    roles=["HERO"],
                    sentence_pattern_rules=["Short denial, then procedural panic."],
                )
            },
        ),
    )
    save_emotional_arcs(
        storage_dir,
        "paper-cuts",
        EmotionalArcRegistry(
            series_id="paper-cuts",
            characters={
                "Hero": EmotionalArc(
                    character="Hero",
                    wound="Hero still thinks every promotion is a trap.",
                    current_coping_mode="alphabetizes terror",
                    relationships={"System": "mutual contempt"},
                )
            },
        ),
    )
    save_world_register(
        storage_dir,
        "paper-cuts",
        WorldRegister(
            series_id="paper-cuts",
            locations=[
                LocationDetail(
                    name="Copy Room",
                    detail="toner-scented arena with jammed doors",
                    floor=1,
                )
            ],
            entity_ecology=[
                EntityEcology(
                    entity="Staple Wraith",
                    detail="feeds on unsigned forms",
                    floor=1,
                    location="Copy Room",
                )
            ],
            rules=[
                RuleEntry(
                    rule="All forms bite back",
                    detail="paperwork becomes hostile when ignored",
                    floor=1,
                )
            ],
            economy_anchors=[
                EconomyAnchor(
                    name="Toner Scrip",
                    detail="accepted by vending machines and minor office spirits",
                    floor=1,
                )
            ],
        ),
    )
    save_foreshadow_ledger(
        storage_dir,
        ForeshadowLedger(
            series_id="paper-cuts",
            planted=[
                ForeshadowEntry(
                    detail="The toner cartridge clicks before anyone touches it.",
                    planted_chapter=1,
                    intended_payoff_start=2,
                    intended_payoff_end=3,
                    mystery="What lives inside office supplies.",
                )
            ],
        ),
    )
    task_path = tmp_path / "chapter_task.json"
    task_path.write_text(
        json.dumps(
                {
                    "mode": "chapter",
                    "series_id": "paper-cuts",
                    "chapter_number": 2,
                    "premise": "The office bites back.",
                    "floor": 1,
                    "storage_dir": "library",
                    "chapter_contract": False,
                }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_generate(task, *, llm):
        captured.update(task)
        return {"mode": "chapter", "series_id": task["series_id"]}

    monkeypatch.setattr("podcastfy.litrpg.task.generate_litrpg_chapter", fake_generate)

    run_litrpg_task(task_path, llm=object())

    context = captured["story_engine_context"]
    assert "The copier demands tribute" in context
    assert "Short denial, then procedural panic" in context
    assert "Hero still thinks every promotion is a trap" in context
    assert "alphabetizes terror" in context
    assert "Copy Room: toner-scented arena" in context
    assert "Staple Wraith: feeds on unsigned forms" in context
    assert "All forms bite back: paperwork becomes hostile" in context
    assert "Toner Scrip: accepted by vending machines" in context
    assert "The toner cartridge clicks" in context
    assert "ready_to_pay" in context


def test_checked_in_episode_example_replays_with_fake_tts(tmp_path):
    task = load_litrpg_task(EPISODE_EXAMPLE)
    task["storage_dir"] = "library"
    task["result_path"] = "library/paper-cuts-replay/episode-001.json"
    task["settings_path"] = "settings.local.json"
    task_path = tmp_path / "episode.task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    (tmp_path / "settings.local.json").write_text("{}", encoding="utf-8")

    first_tts = FakeTTS()
    first = run_litrpg_task(task_path, tts=first_tts)
    second_tts = FakeTTS()
    second = run_litrpg_task(task_path, tts=second_tts)

    assert task["render_audio"] is True
    assert task["replay_existing"] is True
    assert len(first_tts.calls) == 1
    assert Path(first["audio_metadata"]["audio_path"]).exists()
    assert second["replayed"] is True
    assert second["audio_metadata"]["audio_path"] == first["audio_metadata"]["audio_path"]
    assert second_tts.calls == []


def test_checked_in_chapter_example_runs_with_fake_llm_and_writes_smoke_bundle(tmp_path):
    task = load_litrpg_task(CHAPTER_EXAMPLE)
    task["storage_dir"] = "library"
    task["result_path"] = "library/paper-cuts/chapter-002.json"
    task["checkpoint_dir"] = "library/paper-cuts/chapter-002_checkpoints"
    task["settings_path"] = "settings.local.json"
    task_path = tmp_path / "chapter.task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    (tmp_path / "settings.local.json").write_text("{}", encoding="utf-8")

    result = run_litrpg_task(task_path, llm=SmokeChapterLLM())

    checkpoint_dir = tmp_path / "library" / "paper-cuts" / "chapter-002_checkpoints"
    state_path = tmp_path / "library" / "series" / "paper-cuts" / "series_state.json"
    result_path = tmp_path / "library" / "paper-cuts" / "chapter-002.json"

    assert task["render_audio"] is False
    assert result["mode"] == "chapter"
    assert result["render"]["audio_rendered"] is False
    assert result_path.exists()
    assert checkpoint_dir.exists()
    assert len(list(checkpoint_dir.glob("*_approved.xml"))) == 5
    assert state_path.exists()
