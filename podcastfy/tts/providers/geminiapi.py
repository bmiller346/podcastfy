"""Gemini API text-to-speech provider."""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any, List
import wave
from io import BytesIO
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from ..base import TTSProvider


class GeminiApiTTS(TTSProvider):
    """Gemini API TTS provider using the Interactions endpoint."""

    def __init__(
        self,
        api_key: str = None,
        model: str = "gemini-3.1-flash-tts-preview",
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API TTS requires an API key. Set GEMINI_API_KEY or provide "
                "gemini_api_key in LitRPG settings."
            )
        if not model:
            raise ValueError("Gemini API TTS requires a model name.")
        self.model = model

    def generate_audio(
        self,
        text: str,
        voice: str,
        model: str,
        voice2: str = None,
        instructions: str | None = None,
        response_format: str = "wav",
    ) -> bytes:
        """Generate a WAV audio segment using Gemini TTS."""
        effective_model = model or self.model
        self.validate_parameters(text, voice, effective_model)
        if response_format and response_format.lower() != "wav":
            raise ValueError("Gemini API TTS currently supports response_format='wav' only.")

        prompt = f"{instructions.strip()}: {text}" if instructions else text
        payload = {
            "model": effective_model,
            "input": prompt,
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [
                    {"voice": voice},
                ]
            },
        }
        request = urllib_request.Request(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=120) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API TTS request failed: {error_body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Gemini API TTS request failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini API TTS response was not valid JSON") from exc

        audio_data = _extract_audio_data(response_payload)
        audio_bytes = _decode_audio_data(audio_data)
        if _is_wav(audio_bytes):
            return audio_bytes
        return _wav_bytes(audio_bytes)

    def get_supported_tags(self) -> List[str]:
        return self.COMMON_SSML_TAGS


def _wav_bytes(pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def _extract_audio_data(payload: Any) -> str:
    candidates = [
        ("output_audio.data", lambda p: p.get("output_audio", {}).get("data")),
        ("audio.data", lambda p: p.get("audio", {}).get("data")),
        ("output.0.content.0.audio.data", lambda p: p.get("output", [{}])[0].get("content", [{}])[0].get("audio", {}).get("data")),
        ("candidates.0.content.parts.0.inline_data.data", lambda p: p.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("inline_data", {}).get("data")),
        ("candidates.0.content.parts.0.inlineData.data", lambda p: p.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("inlineData", {}).get("data")),
    ]
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini API TTS response was not a JSON object")

    for label, getter in candidates:
        try:
            value = getter(payload)
        except (AttributeError, IndexError, KeyError, TypeError):
            value = None
        if value:
            if not isinstance(value, str):
                raise RuntimeError(f"Gemini API TTS response field {label} was not a string")
            return value

    raise RuntimeError(
        "Gemini API TTS response did not include base64 audio data in a recognized field"
    )


def _decode_audio_data(audio_data: str) -> bytes:
    try:
        return base64.b64decode(audio_data, validate=True)
    except binascii.Error as exc:
        raise RuntimeError("Gemini API TTS response audio data was not valid base64") from exc


def _is_wav(audio: bytes) -> bool:
    return len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"
