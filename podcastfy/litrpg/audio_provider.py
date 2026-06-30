"""Provider adapters for contract-driven LitRPG audio performance."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from podcastfy.litrpg.performance import LinePerformanceContract


@dataclass(frozen=True, slots=True)
class AudioPerformanceRequest:
    """Provider-neutral render request derived from a line contract."""

    provider: str
    text: str
    voice: str
    model: str
    instructions: str = ""
    contract: dict[str, Any] = field(default_factory=dict)
    reference_clip_ids: list[str] = field(default_factory=list)
    generation_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AudioPerformanceProvider(Protocol):
    """Render a single contracted line with provider-specific translation."""

    provider_name: str

    def render_line(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> bytes:
        ...


class GeminiAudioProvider:
    """Gemini-style adapter: preserve structured contract as generation config."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        provider: Any | None = None,
        voice: str,
        model: str,
        response_format: str = "wav",
    ) -> None:
        self.provider = provider
        self.voice = voice
        self.model = model
        self.response_format = response_format

    def build_request(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> AudioPerformanceRequest:
        reference_ids = _matching_reference_ids(contract, reference_clips)
        return AudioPerformanceRequest(
            provider=self.provider_name,
            text=contract.text,
            voice=self.voice,
            model=self.model,
            instructions=contract.style_instruction(),
            contract=contract.to_dict(),
            reference_clip_ids=reference_ids,
            generation_config={
                "performance_contract": contract.to_dict(),
                "reference_clip_ids": reference_ids,
                "speech_config": {"voice": self.voice},
            },
        )

    def render_line(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> bytes:
        request = self.build_request(contract, reference_clips)
        if self.provider is None:
            return _encoded_placeholder(request)
        if hasattr(self.provider, "render_line"):
            return self.provider.render_line(contract, reference_clips)
        return self.provider.generate_audio(
            contract.text,
            self.voice,
            self.model,
            instructions=json.dumps(request.contract, sort_keys=True),
            response_format=self.response_format,
        )


class ElevenLabsPerformanceProvider:
    """ElevenLabs-style adapter: style text plus reference audio conditioning."""

    provider_name = "elevenlabs"

    def __init__(
        self,
        *,
        provider: Any | None = None,
        voice: str,
        model: str,
    ) -> None:
        self.provider = provider
        self.voice = voice
        self.model = model

    def build_request(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> AudioPerformanceRequest:
        reference_ids = _matching_reference_ids(contract, reference_clips)
        return AudioPerformanceRequest(
            provider=self.provider_name,
            text=contract.text,
            voice=self.voice,
            model=self.model,
            instructions=contract.style_instruction(),
            contract=contract.to_dict(),
            reference_clip_ids=reference_ids,
            generation_config={
                "reference_audio_count": len(reference_ids),
                "style_instruction": contract.style_instruction(),
            },
        )

    def render_line(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> bytes:
        request = self.build_request(contract, reference_clips)
        if self.provider is None:
            return _encoded_placeholder(request)
        if hasattr(self.provider, "render_line"):
            return self.provider.render_line(contract, reference_clips)
        try:
            return self.provider.generate_audio(
                contract.text,
                self.voice,
                self.model,
                instructions=request.instructions,
            )
        except TypeError:
            return self.provider.generate_audio(contract.text, self.voice, self.model)


class OpenAIAudioProvider:
    """OpenAI-style adapter: map contract fields to supported instructions."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        provider: Any | None = None,
        voice: str,
        model: str,
        response_format: str = "mp3",
    ) -> None:
        self.provider = provider
        self.voice = voice
        self.model = model
        self.response_format = response_format

    def build_request(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> AudioPerformanceRequest:
        parameters = {
            "pace": _pace_parameter(contract.pace),
            "emotional_weight": contract.weight,
            "internal_state": contract.internal_state,
            "register": contract.performance_register,
            "transition": contract.register_transition,
        }
        return AudioPerformanceRequest(
            provider=self.provider_name,
            text=contract.text,
            voice=self.voice,
            model=self.model,
            instructions=contract.style_instruction(),
            contract=contract.to_dict(),
            reference_clip_ids=_matching_reference_ids(contract, reference_clips),
            generation_config={"voice_parameters": parameters},
        )

    def render_line(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> bytes:
        request = self.build_request(contract, reference_clips)
        if self.provider is None:
            return _encoded_placeholder(request)
        if hasattr(self.provider, "render_line"):
            return self.provider.render_line(contract, reference_clips)
        return self.provider.generate_audio(
            contract.text,
            self.voice,
            self.model,
            instructions=request.instructions,
            response_format=self.response_format,
        )


class FallbackTTSPerformanceProvider:
    """Classical TTS adapter: exact text only, no register conditioning."""

    provider_name = "fallback"

    def __init__(
        self,
        *,
        provider: Any | None = None,
        voice: str,
        model: str,
    ) -> None:
        self.provider = provider
        self.voice = voice
        self.model = model

    def build_request(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> AudioPerformanceRequest:
        return AudioPerformanceRequest(
            provider=self.provider_name,
            text=contract.text,
            voice=self.voice,
            model=self.model,
            instructions="Speak exactly the supplied text.",
            contract={"line_id": contract.line_id, "role": contract.role},
            reference_clip_ids=[],
            generation_config={"exact_text_only": True},
        )

    def render_line(
        self,
        contract: LinePerformanceContract,
        reference_clips: Mapping[str, bytes],
    ) -> bytes:
        request = self.build_request(contract, reference_clips)
        if self.provider is None:
            return _encoded_placeholder(request)
        if hasattr(self.provider, "render_line"):
            return self.provider.render_line(contract, reference_clips)
        return self.provider.generate_audio(contract.text, self.voice, self.model)


def provider_name_for_contract(
    contract: LinePerformanceContract,
    config: Mapping[str, Any] | None = None,
) -> str:
    """Choose provider by role/register override, falling back to default."""

    values = dict(config or {})
    register_overrides = _mapping(values.get("register_provider_overrides"))
    role_overrides = _mapping(values.get("role_provider_overrides"))
    register = str(contract.performance_register or "").lower()
    role = contract.role.upper()
    if register and register in register_overrides:
        return str(register_overrides[register])
    if role in role_overrides:
        return str(role_overrides[role])
    return str(values.get("default_provider") or values.get("provider") or "fallback")


def load_reference_clips(
    references: Mapping[str, Any] | None,
    *,
    base_dir: str | Path | None = None,
) -> dict[str, bytes]:
    """Load reference clips from bytes, strings, or paths for provider adapters."""

    clips: dict[str, bytes] = {}
    root = Path(base_dir) if base_dir else None
    for key, value in dict(references or {}).items():
        clip_id = str(key)
        if isinstance(value, bytes):
            clips[clip_id] = value
            continue
        if isinstance(value, bytearray):
            clips[clip_id] = bytes(value)
            continue
        path = Path(str(value))
        if not path.is_absolute() and root is not None:
            path = root / path
        if path.exists() and path.is_file():
            clips[clip_id] = path.read_bytes()
    return clips


def _matching_reference_ids(
    contract: LinePerformanceContract,
    reference_clips: Mapping[str, bytes],
) -> list[str]:
    candidates = []
    if contract.reference_clip_id:
        candidates.append(contract.reference_clip_id)
    role = contract.role.upper()
    register = str(contract.performance_register or "").upper()
    if register:
        candidates.extend([f"{role}:{register}", f"{role}/{register}", f"{role}.{register}"])
    candidates.append(role)
    return [candidate for candidate in candidates if candidate in reference_clips]


def _pace_parameter(pace: str) -> float:
    return {
        "flat": 0.85,
        "measured": 1.0,
        "clipped": 1.08,
        "urgent": 1.18,
    }.get(str(pace), 1.0)


def _encoded_placeholder(request: AudioPerformanceRequest) -> bytes:
    return json.dumps(request.to_dict(), sort_keys=True).encode("utf-8")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
