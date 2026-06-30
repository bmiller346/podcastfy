"""Configurable post-generation voice processing for LitRPG audio."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


DEFAULT_VOICE_PROCESSING_CHAINS: dict[str, dict[str, Any]] = {
    "none": {"effects": []},
    "announcer_broadcast": {
        "effects": [
            {"type": "highpass", "cutoff_frequency_hz": 120},
            {"type": "lowpass", "cutoff_frequency_hz": 9000},
            {"type": "compressor", "threshold_db": -18, "ratio": 4.0},
            {"type": "gain", "gain_db": 1.5},
        ]
    },
    "warm_narration": {
        "effects": [
            {"type": "highpass", "cutoff_frequency_hz": 70},
            {"type": "compressor", "threshold_db": -24, "ratio": 2.0},
            {"type": "reverb", "room_size": 0.06, "wet_level": 0.025},
        ]
    },
    "monster_distortion": {
        "effects": [
            {"type": "highpass", "cutoff_frequency_hz": 90},
            {"type": "pitch_shift", "semitones": -4.0},
            {"type": "distortion", "drive_db": 8.0},
            {"type": "compressor", "threshold_db": -20, "ratio": 5.0},
        ]
    },
}


@dataclass(frozen=True, slots=True)
class VoiceProcessingChain:
    """One role/register post-processing chain."""

    role: str
    chain: str = "none"
    pitch_shift_semitones: float = 0.0
    chain_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def voice_processing_chain_for_role(
    role: str,
    config: Mapping[str, Any] | None = None,
    *,
    performance_register: str | None = None,
) -> VoiceProcessingChain:
    """Return deterministic post-processing settings for role/register."""

    role_key = str(role).upper()
    values = _voice_processing_values(config)
    selected = _mapping(values.get(role_key))
    register_key = str(performance_register or "").lower()
    register_overrides = _mapping(selected.get("register_overrides"))
    if register_key and register_key in register_overrides:
        merged = dict(selected)
        merged.update(_mapping(register_overrides[register_key]))
        selected = merged
    return VoiceProcessingChain(
        role=role_key,
        chain=str(selected.get("chain") or "none"),
        pitch_shift_semitones=_float(selected.get("pitch_shift_semitones"), 0.0),
        chain_params=dict(selected.get("chain_params") or {}),
    )


def apply_voice_processing_to_file(
    input_path: str | Path,
    output_path: str | Path,
    chain: VoiceProcessingChain,
) -> dict[str, Any]:
    """Apply a configured chain when pedalboard is available.

    If ``pedalboard`` is unavailable, this returns a metadata result and leaves
    audio untouched instead of failing render tests or local development.
    """

    source = Path(input_path)
    output = Path(output_path)
    if chain.chain == "none" and chain.pitch_shift_semitones == 0:
        return {
            "processed": False,
            "reason": "chain_none",
            "input_path": str(source),
            "output_path": str(output),
            "chain": chain.to_dict(),
        }
    if not source.exists():
        return {
            "processed": False,
            "reason": "input_missing",
            "input_path": str(source),
            "output_path": str(output),
            "chain": chain.to_dict(),
        }
    try:
        from pedalboard import Pedalboard
        from pedalboard.io import AudioFile
    except Exception as exc:
        return {
            "processed": False,
            "reason": f"pedalboard_unavailable: {exc}",
            "input_path": str(source),
            "output_path": str(output),
            "chain": chain.to_dict(),
        }

    board = Pedalboard(_build_pedalboard_effects(chain))
    output.parent.mkdir(parents=True, exist_ok=True)
    with AudioFile(str(source)) as input_file:
        audio = input_file.read(input_file.frames)
        samplerate = input_file.samplerate
    processed = board(audio, samplerate)
    with AudioFile(str(output), "w", samplerate, processed.shape[0]) as output_file:
        output_file.write(processed)
    return {
        "processed": True,
        "input_path": str(source),
        "output_path": str(output),
        "chain": chain.to_dict(),
        "effect_count": len(board),
    }


def _build_pedalboard_effects(chain: VoiceProcessingChain) -> list[Any]:
    from pedalboard import Compressor, Distortion, Gain, HighpassFilter, LowpassFilter, PitchShift, Reverb

    spec = DEFAULT_VOICE_PROCESSING_CHAINS.get(chain.chain, {"effects": []})
    effects: list[Any] = []
    for effect in spec.get("effects", []):
        values = dict(effect)
        effect_type = str(values.pop("type", "")).lower()
        values.update(_params_for_effect(effect_type, chain.chain_params))
        if effect_type == "highpass":
            effects.append(HighpassFilter(**values))
        elif effect_type == "lowpass":
            effects.append(LowpassFilter(**values))
        elif effect_type == "compressor":
            effects.append(Compressor(**values))
        elif effect_type == "gain":
            effects.append(Gain(**values))
        elif effect_type == "reverb":
            effects.append(Reverb(**values))
        elif effect_type == "distortion":
            effects.append(Distortion(**values))
        elif effect_type == "pitch_shift":
            semitones = chain.pitch_shift_semitones or _float(values.pop("semitones", 0), 0.0)
            effects.append(PitchShift(semitones=semitones))
    if chain.pitch_shift_semitones and not any(
        str(effect.get("type", "")).lower() == "pitch_shift"
        for effect in spec.get("effects", [])
    ):
        effects.insert(0, PitchShift(semitones=chain.pitch_shift_semitones))
    return effects


def _voice_processing_values(config: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(config, Mapping):
        return {}
    values = config.get("voice_processing")
    return values if isinstance(values, Mapping) else config


def _params_for_effect(effect_type: str, params: Mapping[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    aliases = {
        "highpass": {"cutoff_frequency_hz": "highpass_hz"},
        "lowpass": {"cutoff_frequency_hz": "lowpass_hz"},
        "compressor": {"threshold_db": "compression_threshold_db", "ratio": "compression_ratio"},
        "gain": {"gain_db": "gain_db"},
        "reverb": {"room_size": "room_size", "wet_level": "wet_level"},
        "distortion": {"drive_db": "distortion_drive_db"},
        "pitch_shift": {"semitones": "pitch_shift_semitones"},
    }
    for target, source in aliases.get(effect_type, {}).items():
        if source in params:
            mapped[target] = params[source]
    return mapped


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
