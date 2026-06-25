"""OpenAI TTS provider implementation."""

from openai import OpenAI
from typing import List, Optional
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
            model: Model name to use. Defaults to "tts-1-hd"
        """
        self.client = OpenAI(api_key=api_key) if api_key else OpenAI()
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
        self.validate_parameters(text, voice, model)
        
        try:
            params = {
                "model": model or self.model,
                "voice": voice,
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
