"""Gemini API text-to-speech provider."""

from __future__ import annotations

import base64
import json
import os
from typing import List
import wave
from io import BytesIO
from urllib import request as urllib_request
from urllib.error import HTTPError

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
            raise ValueError("GEMINI_API_KEY must be provided or set in environment")
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
        self.validate_parameters(text, voice, model or self.model)
        prompt = f"{instructions.strip()}: {text}" if instructions else text
        payload = {
            "model": model or self.model,
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

        audio_data = response_payload.get("output_audio", {}).get("data")
        if not audio_data:
            raise RuntimeError("Gemini API TTS response did not include output_audio.data")
        pcm = base64.b64decode(audio_data)
        return _wav_bytes(pcm)

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
