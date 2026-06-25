from podcastfy.litrpg.script_parser import parse_role_script
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
