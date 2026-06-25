import base64
import json
import sys
import types
import wave
from io import BytesIO

import pytest

from podcastfy.tts.factory import TTSProviderFactory
from podcastfy.tts.providers.geminiapi import GeminiApiTTS
from podcastfy.tts.providers.openai import OpenAITTS


class FakeOpenAISpeech:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(content=b"openai-audio")


class FakeOpenAIClient:
    speech = FakeOpenAISpeech()

    def __init__(self, api_key):
        self.api_key = api_key
        self.audio = types.SimpleNamespace(speech=self.speech)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json_bytes(self.payload)


def test_geminiapi_tts_posts_interactions_request(monkeypatch):
    calls = []
    pcm = b"\x00\x00" * 24

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse({"output_audio": {"data": base64.b64encode(pcm).decode("ascii")}})

    monkeypatch.setattr("podcastfy.tts.providers.geminiapi.urllib_request.urlopen", fake_urlopen)

    provider = GeminiApiTTS(api_key="gemini-key", model="gemini-3.1-flash-tts-preview")
    audio = provider.generate_audio(
        "Quest accepted.",
        voice="Kore",
        model="gemini-3.1-flash-tts-preview",
        instructions="Say with crisp arcade menace",
        response_format="wav",
    )

    request = calls[0][0]
    payload = __import__("json").loads(request.data.decode("utf-8"))
    assert request.full_url == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert request.headers["X-goog-api-key"] == "gemini-key"
    assert payload["model"] == "gemini-3.1-flash-tts-preview"
    assert payload["generation_config"]["speech_config"] == [{"voice": "Kore"}]
    assert "Say with crisp arcade menace" in payload["input"]

    with wave.open(BytesIO(audio), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1


def test_geminiapi_tts_parses_inline_data_response(monkeypatch):
    wav = make_wav_bytes(b"\x00\x00" * 12)

    def fake_urlopen(request, timeout):
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inline_data": {
                                        "data": base64.b64encode(wav).decode("ascii")
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("podcastfy.tts.providers.geminiapi.urllib_request.urlopen", fake_urlopen)

    provider = GeminiApiTTS(api_key="gemini-key")

    assert provider.generate_audio("Quest accepted.", voice="Kore", model=None) == wav


def test_geminiapi_tts_reports_unrecognized_response(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse({"candidates": []})

    monkeypatch.setattr("podcastfy.tts.providers.geminiapi.urllib_request.urlopen", fake_urlopen)
    provider = GeminiApiTTS(api_key="gemini-key")

    with pytest.raises(RuntimeError, match="recognized field"):
        provider.generate_audio("Quest accepted.", voice="Kore", model=None)


def test_geminiapi_tts_validates_voice_model_and_format():
    with pytest.raises(ValueError, match="model"):
        GeminiApiTTS(api_key="gemini-key", model="")

    provider = GeminiApiTTS(api_key="gemini-key")
    with pytest.raises(ValueError, match="Voice"):
        provider.generate_audio("Quest accepted.", voice="", model=None)

    with pytest.raises(ValueError, match="response_format='wav'"):
        provider.generate_audio("Quest accepted.", voice="Kore", model=None, response_format="mp3")


def test_openai_tts_uses_custom_voice_json_and_optional_instructions(monkeypatch):
    fake_module = types.SimpleNamespace(OpenAI=FakeOpenAIClient)
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    FakeOpenAIClient.speech.calls.clear()

    provider = OpenAITTS(api_key="openai-key")
    audio = provider.generate_audio(
        "Quest accepted.",
        voice=json.dumps({"id": "voice_custom_123"}),
        model=None,
        response_format="mp3",
    )

    assert audio == b"openai-audio"
    assert FakeOpenAIClient.speech.calls == [
        {
            "model": "gpt-4o-mini-tts",
            "voice": "voice_custom_123",
            "input": "Quest accepted.",
            "response_format": "mp3",
        }
    ]


def test_openai_tts_passes_instructions_only_when_provided(monkeypatch):
    fake_module = types.SimpleNamespace(OpenAI=FakeOpenAIClient)
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    FakeOpenAIClient.speech.calls.clear()

    provider = OpenAITTS(api_key="openai-key")
    provider.generate_audio(
        "Quest accepted.",
        voice={"voice_id": "voice_custom_456"},
        model="gpt-4o-mini-tts",
        instructions="Crisp arcade menace.",
    )

    assert FakeOpenAIClient.speech.calls[0]["voice"] == "voice_custom_456"
    assert FakeOpenAIClient.speech.calls[0]["instructions"] == "Crisp arcade menace."


def test_openai_tts_reports_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAITTS()


def test_provider_factory_lists_supported_providers():
    providers = TTSProviderFactory.supported_providers()

    assert "openai" in providers
    assert "geminiapi" in providers


def test_provider_factory_does_not_override_provider_default_model(monkeypatch):
    fake_module = types.SimpleNamespace(OpenAI=FakeOpenAIClient)
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    provider = TTSProviderFactory._create_provider_instance(OpenAITTS, "openai-key", None)

    assert provider.model == "gpt-4o-mini-tts"


def json_bytes(payload):
    return __import__("json").dumps(payload).encode("utf-8")


def make_wav_bytes(pcm):
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(pcm)
    return output.getvalue()
