from pathlib import Path

import pytest

from podcastfy.litrpg.performance import build_line_performance_contracts
from podcastfy.litrpg.performance_qa import build_audio_performance_qa
from podcastfy.litrpg.renderer import RoleScriptRenderer
from podcastfy.litrpg.script_parser import (
    RoleScriptParseError,
    parse_role_script,
    validate_audio_readiness,
)
from podcastfy.tts.script_parser import parse_role_script as parse_generic_role_script
from podcastfy.text_to_speech import TextToSpeech
from podcastfy.tts.base import TTSProvider
from podcastfy.tts.factory import TTSProviderFactory


class FakeProvider(TTSProvider):
    model = "fake"

    def __init__(self, api_key=None, model=None):
        self.calls = []
        self.model = model or "fake"

    def generate_audio(self, text: str, voice: str, model: str, voice2: str = None) -> bytes:
        self.calls.append((text, voice, model))
        return f"{voice}:{text}".encode("utf-8")


class InstructionProvider(FakeProvider):
    def generate_audio(
        self,
        text: str,
        voice: str,
        model: str,
        voice2: str = None,
        instructions: str = None,
        response_format: str = "mp3",
    ) -> bytes:
        self.calls.append((text, voice, model, instructions, response_format))
        return f"{voice}:{text}:{instructions}".encode("utf-8")


def make_tts(monkeypatch):
    monkeypatch.setattr(
        "podcastfy.text_to_speech.TTSProviderFactory.create",
        lambda provider_name, api_key, model: FakeProvider(),
    )
    return TextToSpeech(
        model="fake",
        conversation_config={
            "text_to_speech": {
                "audio_format": "mp3",
                "temp_audio_dir": "data/audio/tmp/",
                "default_model": "fake-model",
                "default_voice_question": "fallback-voice",
                "default_voice_answer": "answer-voice",
                "output_directories": {},
            }
        },
    )


def make_instruction_tts(monkeypatch):
    monkeypatch.setattr(
        "podcastfy.text_to_speech.TTSProviderFactory.create",
        lambda provider_name, api_key, model: InstructionProvider(),
    )
    return TextToSpeech(
        model="fake",
        conversation_config={
            "text_to_speech": {
                "audio_format": "mp3",
                "temp_audio_dir": "data/audio/tmp/",
                "default_model": "fake-model",
                "default_voice_question": "fallback-voice",
                "default_voice_answer": "answer-voice",
                "output_directories": {},
            }
        },
    )


def test_parse_role_script_preserves_order_and_style():
    script = """
        <NARRATOR> The gate opened. </NARRATOR>
        <SYSTEM style="hostile">
            Intruder detected.
        </SYSTEM>
        <HERO>Not today.</HERO>
    """

    lines = parse_role_script(script)

    assert [line.role for line in lines] == ["NARRATOR", "SYSTEM", "HERO"]
    assert [line.text for line in lines] == [
        "The gate opened.",
        "Intruder detected.",
        "Not today.",
    ]
    assert lines[1].style == "hostile"


def test_litrpg_parser_is_compatibility_shim_for_generic_parser():
    script = "<HOST>Welcome</HOST><GUEST>Ready</GUEST>"

    assert parse_role_script(script) == parse_generic_role_script(script)


def test_parse_role_script_filters_role_tags():
    script = "<NARRATOR>Keep</NARRATOR><SIDEKICK>Skip</SIDEKICK>"

    lines = parse_role_script(script, role_tags=["NARRATOR"])

    assert len(lines) == 1
    assert lines[0].role == "NARRATOR"
    assert lines[0].text == "Keep"


def test_parse_role_script_ignores_unsupported_attrs_but_keeps_style():
    script = '<SYSTEM emotion="smug" style="hostile announcer">Level up.</SYSTEM>'

    lines = parse_role_script(script)

    assert lines == [
        parse_generic_role_script('<SYSTEM style="hostile announcer">Level up.</SYSTEM>')[0]
    ]


@pytest.mark.parametrize(
    "script",
    [
        "<NARRATOR>Missing close",
        "<NARRATOR>Wrong close</SYSTEM>",
        "<NARRATOR>Nested <SYSTEM>Nope</SYSTEM></NARRATOR>",
        "<SYSTEM style=hostile>No quotes</SYSTEM>",
    ],
)
def test_parse_role_script_rejects_malformed_role_blocks(script):
    with pytest.raises(RoleScriptParseError):
        parse_role_script(script)


def test_convert_script_to_speech_routes_voices_in_order(monkeypatch, tmp_path):
    tts = make_tts(monkeypatch)
    merged_inputs = []

    def fake_merge(audio_files, output_file):
        merged_inputs.extend(audio_files)
        with open(output_file, "wb") as output:
            for file_path in audio_files:
                with open(file_path, "rb") as segment:
                    output.write(segment.read())

    monkeypatch.setattr(tts, "_merge_audio_files_sequential", fake_merge)
    output_file = tmp_path / "script.mp3"

    tts.convert_script_to_speech(
        "<NARRATOR>Begin</NARRATOR><SYSTEM>Level up</SYSTEM><HERO>Nice</HERO>",
        str(output_file),
        {"NARRATOR": "voice-n", "SYSTEM": "voice-s", "default": "voice-default"},
    )

    assert tts.provider.calls == [
        ("Begin", "voice-n", "fake-model"),
        ("Level up", "voice-s", "fake-model"),
        ("Nice", "voice-default", "fake-model"),
    ]
    assert [path.split("_")[-1] for path in merged_inputs] == [
        "narrator.mp3",
        "system.mp3",
        "hero.mp3",
    ]
    assert output_file.read_bytes() == b"voice-n:Beginvoice-s:Level upvoice-default:Nice"


def test_convert_script_to_speech_passes_role_and_line_instructions(monkeypatch, tmp_path):
    tts = make_instruction_tts(monkeypatch)
    monkeypatch.setattr(
        tts,
        "_merge_audio_files_sequential",
        lambda audio_files, output_file: open(output_file, "wb").write(b"ok"),
    )
    output_file = tmp_path / "script.mp3"

    tts.convert_script_to_speech(
        '<SYSTEM style="hostile announcer">Level up</SYSTEM>',
        str(output_file),
        {"SYSTEM": "voice-s"},
        role_instructions={"SYSTEM": "Speak with crisp arcade menace."},
    )

    assert tts.provider.calls == [
        (
            "Level up",
            "voice-s",
            "fake-model",
            "Speak with crisp arcade menace. hostile announcer",
            "mp3",
        )
    ]


def test_provider_factory_can_use_registered_fake_without_cloud_dependencies():
    TTSProviderFactory.register_provider("fake-unit", FakeProvider)

    provider = TTSProviderFactory.create("fake-unit", model="fake-model")

    assert isinstance(provider, FakeProvider)
    assert provider.model == "fake-model"


def test_merge_audio_sequential_concatenates_mp3_without_ffmpeg(monkeypatch, tmp_path):
    tts = make_tts(monkeypatch)
    monkeypatch.setattr("podcastfy.text_to_speech.shutil.which", lambda name: None)
    first = tmp_path / "0001_narrator.mp3"
    second = tmp_path / "0002_system.mp3"
    output = tmp_path / "final.mp3"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    tts._merge_audio_files_sequential([str(first), str(second)], str(output))

    assert output.read_bytes() == b"firstsecond"


def test_existing_split_qa_still_pairs_person_tags():
    provider = FakeProvider()

    pairs = provider.split_qa(
        "<Person1>Hello there</Person1><Person2>General Kenobi</Person2>",
        ending_message="Bye",
    )

    assert pairs == [("Hello there", "General Kenobi")]


def test_audio_readiness_gate_blocks_expensive_tts_failures():
    long_line = "x" * 40
    report = validate_audio_readiness(
        f'Loose note.\n<HERO emotion="grim">{long_line}</HERO><NPC>Hi</NPC>',
        allowed_roles=["HERO", "SYSTEM"],
        required_roles=["HERO", "SYSTEM"],
        voice_map={"HERO": "voice-h"},
        max_line_chars=20,
    )

    codes = {issue.code for issue in report.issues}

    assert report.ready is False
    assert {
        "text_outside_role_tags",
        "unsupported_attribute",
        "unsupported_role",
        "missing_required_role",
        "overlong_line",
        "missing_voice",
    }.issubset(codes)


def test_performance_contract_locks_system_line_interpretation():
    contracts = build_line_performance_contracts(
        '<SYSTEM style="hostile crisp">Violation fee applied.</SYSTEM>'
        "<HERO>That is not a fee, that is a mugging.</HERO>",
        director_cues=[
            {
                "role": "SYSTEM",
                "emotion": "dry contempt",
                "delivery": "clipped",
                "timing": "hard stop",
            }
        ],
        reference_clip_ids={"SYSTEM": "system_ref_001"},
    )

    system = contracts[0]

    assert system.role == "SYSTEM"
    assert system.text == "Violation fee applied."
    assert system.pace == "clipped"
    assert system.weight == "heavy"
    assert system.internal_state == "dry_contempt"
    assert system.must_not_soften is True
    assert system.must_not_comedify is True
    assert system.reference_clip_id == "system_ref_001"
    assert "Speak exactly the supplied text" in system.style_instruction()
    assert "do not add, omit, paraphrase, or rewrite" in system.style_instruction()


def test_performance_contract_allows_controlled_announcer_register_shift():
    contracts = build_line_performance_contracts(
        "<SYSTEM>Standard violation notice.</SYSTEM>"
        "<SYSTEM>That should not have been possible.</SYSTEM>",
        director_cues=[
            {"role": "SYSTEM"},
            {
                "role": "SYSTEM",
                "announcer_register": "genuine_awe",
                "register_transition": "collapse",
                "register_earned_by": "Carl breaks a modeled impossible rule.",
            },
        ],
        reference_clip_ids={
            "SYSTEM": "system_ref_bureaucratic",
            "SYSTEM:GENUINE_AWE": "system_ref_awe",
        },
    )

    awe = contracts[1]

    assert contracts[0].performance_register == "bureaucratic_default"
    assert awe.performance_register == "genuine_awe"
    assert awe.prior_register == "bureaucratic_default"
    assert awe.register_transition == "collapse"
    assert awe.register_scarcity_level == 5
    assert awe.register_earned_by == "Carl breaks a modeled impossible rule."
    assert awe.reference_clip_id == "system_ref_awe"
    assert "performance register genuine_awe" in awe.style_instruction()
    assert "register transition collapse" in awe.style_instruction()


def test_audio_performance_qa_quarantines_transcript_and_voice_drift():
    contracts = build_line_performance_contracts(
        '<SYSTEM>Violation fee applied.</SYSTEM>',
        reference_clip_ids={"SYSTEM": "system_ref_001"},
    )

    report = build_audio_performance_qa(
        contracts,
        transcript_lines={"line-0001": "A friendly quest fee was applied."},
        voice_similarity_scores={"SYSTEM": 0.61},
        voice_similarity_threshold=0.82,
    )

    codes = {issue.code for issue in report.issues}

    assert report.ready is False
    assert report.quarantine_required is True
    assert report.transcript_checked is True
    assert report.voice_similarity_checked is True
    assert "transcript_text_mismatch" in codes
    assert "voice_similarity_below_threshold" in codes


def test_audio_performance_qa_quarantines_unearned_scarce_register():
    contracts = build_line_performance_contracts(
        '<SYSTEM style="genuine awe">Impossible.</SYSTEM>',
        reference_clip_ids={"SYSTEM:GENUINE_AWE": "system_ref_awe"},
    )

    report = build_audio_performance_qa(
        contracts,
        transcript_lines={"line-0001": "Impossible."},
        voice_similarity_scores={"SYSTEM:GENUINE_AWE": 0.93},
        performance_context={"chapter_number": 4, "phase": "Setup"},
    )

    codes = {issue.code for issue in report.issues}

    assert report.quarantine_required is True
    assert "register_transition_unearned" in codes
    assert "register_used_before_unlock" in codes
    assert "register_requires_apex_beat" in codes


def test_audio_performance_qa_passes_exact_transcript_and_reference_match():
    contracts = build_line_performance_contracts(
        '<SYSTEM>Violation fee applied.</SYSTEM>',
        reference_clip_ids={"SYSTEM": "system_ref_001"},
    )

    report = build_audio_performance_qa(
        contracts,
        transcript_lines={"line-0001": "Violation fee applied."},
        voice_similarity_scores={"SYSTEM": 0.91},
    )

    assert report.ready is True
    assert report.quarantine_required is False
    assert report.issues == []


def test_audio_performance_qa_allows_earned_unlocked_scarce_register():
    contracts = build_line_performance_contracts(
        '<SYSTEM style="genuine awe">Impossible.</SYSTEM>',
        director_cues=[
            {
                "role": "SYSTEM",
                "announcer_register": "genuine_awe",
                "register_earned_by": "Unprecedented apex exploit.",
            }
        ],
        reference_clip_ids={"SYSTEM:GENUINE_AWE": "system_ref_awe"},
    )

    report = build_audio_performance_qa(
        contracts,
        transcript_lines={"line-0001": "Impossible."},
        voice_similarity_scores={"SYSTEM:GENUINE_AWE": 0.93},
        performance_context={"chapter_number": 60, "phase": "Apex"},
    )

    assert report.ready is True
    assert report.quarantine_required is False
    assert report.issues == []


def test_role_renderer_runs_readiness_before_tts_money(tmp_path):
    class RecordingTTS:
        def __init__(self):
            self.calls = []

        def convert_script_to_speech(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    tts = RecordingTTS()
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir()
    renderer = RoleScriptRenderer(tts=tts)

    with pytest.raises(ValueError, match="audio readiness failed"):
        renderer.render_episode(
            {
                "script": '<HERO emotion="grim">Nope.</HERO>',
                "storage_metadata": {"bundle_path": str(bundle_path)},
                "config": {"voices": {"HERO": {"voice": "voice-h"}}},
                "role_tags": ["HERO"],
            }
        )

    assert tts.calls == []


def test_role_renderer_passes_contracted_script_and_metadata(tmp_path, monkeypatch):
    class RecordingTTS:
        def __init__(self):
            self.calls = []

        def convert_script_to_speech(self, script, output_file, voice_map, role_tags=None, role_instructions=None):
            self.calls.append(
                {
                    "script": script,
                    "output_file": output_file,
                    "voice_map": voice_map,
                    "role_tags": role_tags,
                    "role_instructions": role_instructions,
                }
            )
            Path(output_file).write_bytes(b"audio")

    monkeypatch.setattr(
        "podcastfy.litrpg.renderer.mix_audio_locally",
        lambda **kwargs: {"mixed": False, "reason": "unit test"},
    )
    tts = RecordingTTS()
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir()
    renderer = RoleScriptRenderer(tts=tts)

    metadata = renderer.render_episode(
        {
            "script": '<SYSTEM>Quest updated: pay the violation fee.</SYSTEM>',
            "storage_metadata": {"bundle_path": str(bundle_path)},
            "config": {
                "voices": {
                    "SYSTEM": {
                        "voice": "voice-s",
                        "instructions": "Crisp bureaucratic hostility.",
                        "reference_clip_id": "system_ref_001",
                    }
                }
            },
            "role_tags": ["SYSTEM"],
            "director_cues": [
                {
                    "role": "SYSTEM",
                    "emotion": "dry contempt",
                    "delivery": "clipped",
                    "timing": "hard stop",
                }
            ],
        }
    )

    call = tts.calls[0]
    instruction = call["role_instructions"]["SYSTEM"]

    assert 'style="' in call["script"]
    assert "Speak exactly the supplied text" in call["script"]
    assert "do not add, omit, paraphrase, or rewrite" in call["script"]
    assert "Quest updated: pay the violation fee." in call["script"]
    assert "Performance contract discipline" in instruction
    assert "do not soften" in instruction
    assert metadata["performance_contracts"][0]["reference_clip_id"] == "system_ref_001"
    assert metadata["performance_contracts"][0]["must_not_comedify"] is True


def test_role_renderer_quarantines_audio_when_post_generation_qa_fails(tmp_path, monkeypatch):
    class RecordingTTS:
        def convert_script_to_speech(self, script, output_file, voice_map, role_tags=None, role_instructions=None):
            Path(output_file).write_bytes(b"audio")

    monkeypatch.setattr(
        "podcastfy.litrpg.renderer.mix_audio_locally",
        lambda **kwargs: {"mixed": False, "reason": "unit test"},
    )
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir()
    renderer = RoleScriptRenderer(tts=RecordingTTS())

    metadata = renderer.render_episode(
        {
            "script": '<SYSTEM>Quest updated: pay the violation fee.</SYSTEM>',
            "storage_metadata": {"bundle_path": str(bundle_path)},
            "config": {
                "voices": {
                    "SYSTEM": {
                        "voice": "voice-s",
                        "reference_clip_id": "system_ref_001",
                    }
                }
            },
            "role_tags": ["SYSTEM"],
            "post_generation_transcript_lines": {
                "line-0001": "Quest updated. Ignore the violation fee."
            },
            "voice_similarity_scores": {"SYSTEM": 0.42},
        }
    )

    qa = metadata["audio_performance_qa"]

    assert metadata["status"] == "quarantined"
    assert qa["quarantine_required"] is True
    assert {issue["code"] for issue in qa["issues"]} == {
        "transcript_text_mismatch",
        "voice_similarity_below_threshold",
    }
    assert Path(metadata["audio_quarantine_path"]).exists()


def test_role_renderer_quarantines_unauthorized_announcer_register(tmp_path, monkeypatch):
    class RecordingTTS:
        def convert_script_to_speech(self, script, output_file, voice_map, role_tags=None, role_instructions=None):
            Path(output_file).write_bytes(b"audio")

    monkeypatch.setattr(
        "podcastfy.litrpg.renderer.mix_audio_locally",
        lambda **kwargs: {"mixed": False, "reason": "unit test"},
    )
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir()
    renderer = RoleScriptRenderer(tts=RecordingTTS())

    metadata = renderer.render_episode(
        {
            "script": "<SYSTEM>Impossible.</SYSTEM>",
            "storage_metadata": {"bundle_path": str(bundle_path)},
            "config": {
                "voices": {
                    "SYSTEM": {
                        "voice": "voice-s",
                        "reference_clip_id": "system_ref_bureaucratic",
                    }
                }
            },
            "role_tags": ["SYSTEM"],
            "chapter_contract": {"chapter": 4, "phase": "Setup"},
            "director_cues": [
                {
                    "role": "SYSTEM",
                    "announcer_register": "genuine_awe",
                    "register_transition": "collapse",
                }
            ],
            "post_generation_transcript_lines": {"line-0001": "Impossible."},
            "voice_similarity_scores": {"SYSTEM": 0.94},
        }
    )

    codes = {issue["code"] for issue in metadata["audio_performance_qa"]["issues"]}

    assert metadata["status"] == "quarantined"
    assert "register_transition_unearned" in codes
    assert "register_used_before_unlock" in codes
    assert "register_requires_apex_beat" in codes
