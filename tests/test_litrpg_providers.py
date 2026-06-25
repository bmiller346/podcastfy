import base64
import wave
from io import BytesIO

from podcastfy.tts.providers.geminiapi import GeminiApiTTS


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


def json_bytes(payload):
    return __import__("json").dumps(payload).encode("utf-8")
