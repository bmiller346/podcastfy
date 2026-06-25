"""Factory for creating TTS providers."""

from importlib import import_module
from typing import Dict, Type, Optional

from .base import TTSProvider


class TTSProviderFactory:
    """Factory class for creating TTS providers."""

    _provider_paths: Dict[str, str] = {
        "elevenlabs": "podcastfy.tts.providers.elevenlabs:ElevenLabsTTS",
        "openai": "podcastfy.tts.providers.openai:OpenAITTS",
        "edge": "podcastfy.tts.providers.edge:EdgeTTS",
        "gemini": "podcastfy.tts.providers.gemini:GeminiTTS",
        "geminiapi": "podcastfy.tts.providers.geminiapi:GeminiApiTTS",
        "geminimulti": "podcastfy.tts.providers.geminimulti:GeminiMultiTTS",
    }
    _providers: Dict[str, Type[TTSProvider]] = {}

    @classmethod
    def create(cls, provider_name: str, api_key: Optional[str] = None, model: Optional[str] = None) -> TTSProvider:
        """
        Create a TTS provider instance.
        
        Args:
            provider_name: Name of the provider to create
            api_key: Optional API key for the provider
            model: Optional model name for the provider
            
        Returns:
            TTSProvider instance
            
        Raises:
            ValueError: If provider_name is not supported
        """
        provider_key = provider_name.lower()
        provider_class = cls._providers.get(provider_key) or cls._load_provider(provider_key)
        if not provider_class:
            raise ValueError(f"Unsupported provider: {provider_name}. "
                           f"Choose from: {', '.join(cls._provider_paths.keys())}")

        return provider_class(api_key, model) if api_key else provider_class(model=model)

    @classmethod
    def _load_provider(cls, provider_name: str) -> Optional[Type[TTSProvider]]:
        provider_path = cls._provider_paths.get(provider_name)
        if not provider_path:
            return None

        module_name, class_name = provider_path.split(":", 1)
        try:
            module = import_module(module_name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"Provider '{provider_name}' requires optional dependency: {exc.name}"
            ) from exc

        provider_class = getattr(module, class_name)
        cls._providers[provider_name] = provider_class
        return provider_class

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[TTSProvider]) -> None:
        """Register a new provider class."""
        cls._providers[name.lower()] = provider_class
