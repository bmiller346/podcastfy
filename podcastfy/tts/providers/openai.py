"""OpenAI TTS provider implementation."""

import json
import os
from typing import Any, List, Optional
from ..base import TTSProvider

class OpenAITTS(TTSProvider):
    """OpenAI Text-to-Speech provider."""
    
    # Provider-specific SSML tags
    PROVIDER_SSML_TAGS: List[str] = ['break', 'emphasis']
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini-tts"):
        """
        Initialize OpenAI TTS provider.
        
        Args:
            api_key: OpenAI API key. If None, expects OPENAI_API_KEY env variable
            model: Speech model name to use. Defaults to "gpt-4o-mini-tts"
        """
        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "OpenAI TTS requires an API key. Set OPENAI_API_KEY or provide "
                "openai_api_key in LitRPG settings."
            )
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "OpenAI TTS requires the optional 'openai' package. Install it "
                "with `pip install openai` or choose another TTS provider."
            ) from exc

        self.client = OpenAI(api_key=resolved_api_key)
        self.model = model
            
    def get_supported_tags(self) -> List[str]:
        """Get all supported SSML tags including provider-specific ones."""
        return self.PROVIDER_SSML_TAGS
        
    def generate_audio(
        self,
        text: str,
        voice: str,
        model: str,
        voice2: str = None,
        instructions: str | None = None,
        response_format: str = "mp3",
    ) -> bytes:
        """Generate audio using OpenAI API."""
        voice_id = _resolve_voice_id(voice)
        self.validate_parameters(text, voice_id, model or self.model)
        
        try:
            params = {
                "model": model or self.model,
                "voice": voice_id,
                "input": text,
                "response_format": response_format,
            }
            if instructions:
                params["instructions"] = instructions
            response = self.client.audio.speech.create(
                **params
            )
            return response.content
        except Exception as e:
            raise RuntimeError(f"Failed to generate audio: {str(e)}") from e


def _resolve_voice_id(voice: Any) -> str:
    """Accept built-in voice names plus custom voice objects passed as dict/JSON."""
    voice_data = voice
    if isinstance(voice, str):
        stripped = voice.strip()
        if stripped.startswith("{"):
            try:
                voice_data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError("OpenAI voice JSON string is invalid") from exc
        else:
            return stripped

    if isinstance(voice_data, dict):
        for key in ("id", "voice", "voice_id", "object_id"):
            value = voice_data.get(key)
            if value:
                return str(value)
        raise ValueError(
            "OpenAI custom voice object must include one of: id, voice, voice_id, object_id"
        )

    if voice_data is None:
        return ""
    return str(voice_data)
