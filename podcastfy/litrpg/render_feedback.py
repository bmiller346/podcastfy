"""Deterministic render-loop feedback for LitRPG audio artifacts."""

from __future__ import annotations

import audioop
import math
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


KNOWN_PACES = {
    "measured",
    "urgent",
    "clipped",
    "flat",
    "slow",
    "fast",
    "neutral",
    "breathless",
    "deadpan",
}
KNOWN_REGISTERS = {
    "bureaucratic_default",
    "hostile_pleasure",
    "genuine_alarm",
    "corporate_panic",
    "genuine_awe",
    "stripped_plain",
    "inner_monologue",
    "memory",
    "void",
}
KNOWN_OPENAI_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "marin",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
}
KNOWN_OPENAI_MODELS = {
    "gpt-4o-mini-tts",
    "gpt-4o-mini-tts-2025-12-15",
    "tts-1",
    "tts-1-hd",
}
KNOWN_EDGE_VOICE_PREFIXES = ("en-",)


@dataclass
class DirectiveValidation:
    valid: bool
    reason: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class RenderFeedback:
    segment_id: str
    attempt: int
    provider: str
    model: str
    peak_db: float | None
    rms_db: float | None
    silence_ratio: float | None
    duration_seconds: float | None
    clipping_detected: bool
    tts_valley_risk: bool
    score: float
    verdict: str
    human_review_required: bool
    notes: list[str] = field(default_factory=list)


def validate_directive(
    directive: Mapping[str, Any], provider: str | None = None
) -> DirectiveValidation:
    """Validate cheap structural performance-directive constraints."""

    if not isinstance(directive, Mapping):
        return DirectiveValidation(False, "directive must be a mapping")

    intensity = _optional_float(directive.get("intensity"))
    if "intensity" in directive:
        if intensity is None:
            return DirectiveValidation(False, "intensity must be numeric")
        if not 0.0 <= intensity <= 1.0:
            return DirectiveValidation(False, "intensity must be between 0.0 and 1.0")

    for key in ("pause_before_ms", "pause_after_ms"):
        if key not in directive:
            continue
        pause = _optional_float(directive.get(key))
        if pause is None:
            return DirectiveValidation(False, f"{key} must be numeric")
        if not 0 <= pause <= 2000:
            return DirectiveValidation(False, f"{key} must be between 0 and 2000ms")

    pace = _normalized(directive.get("pace"))
    if pace and pace not in KNOWN_PACES:
        return DirectiveValidation(False, f"unknown pace: {pace}")

    register = _normalized(
        directive.get("register")
        or directive.get("performance_register")
        or directive.get("announcer_register")
    )
    if register and register not in KNOWN_REGISTERS:
        return DirectiveValidation(False, f"unknown register: {register}")

    scene_type = _normalized(
        directive.get("scene_type")
        or directive.get("acoustic_scene_type")
        or directive.get("room_type")
    )
    if register == "inner_monologue" and intensity is not None and intensity > 0.85:
        return DirectiveValidation(False, "inner monologue intensity cannot exceed 0.85")
    if scene_type in {"void", "memory"} and pace == "urgent":
        return DirectiveValidation(False, "void/memory scene cannot use urgent pace")

    exaggeration = _optional_float(
        directive.get("exaggeration") or directive.get("chatterbox_exaggeration")
    )
    provider_key = _normalized(provider or directive.get("provider"))
    if exaggeration is not None and exaggeration > 0.95 and "chatterbox" in provider_key:
        return DirectiveValidation(False, "Chatterbox exaggeration above 0.95 risks distortion")

    warnings = _provider_warnings(directive, provider_key)
    return DirectiveValidation(True, warnings=warnings)


def score_rendered_audio(
    audio_path: str | Path,
    segment_id: str,
    attempt: int = 1,
    provider: str = "",
    model: str = "",
    expected_duration_seconds: float | None = None,
    segment_text: str = "",
    directive: Mapping[str, Any] | None = None,
) -> RenderFeedback:
    """Score a rendered audio file with deterministic local metrics."""

    notes: list[str] = []
    path = Path(audio_path)
    metrics = _read_audio_metrics(path)
    if metrics.get("error"):
        notes.append(str(metrics["error"]))

    peak_db = metrics.get("peak_db")
    rms_db = metrics.get("rms_db")
    silence_ratio = metrics.get("silence_ratio")
    duration_seconds = metrics.get("duration_seconds")
    clipping_detected = bool(metrics.get("clipping_detected"))

    score = 1.0
    if not path.exists() or metrics.get("error"):
        score -= 0.65
    if rms_db is None or rms_db < -45:
        score -= 0.35
        notes.append("near-silent audio")
    if silence_ratio is not None and silence_ratio > 0.45:
        score -= min(0.3, (silence_ratio - 0.45) * 0.5)
        notes.append("high silence ratio")
    if clipping_detected:
        score -= 0.25
        notes.append("clipping detected")
    text = str(segment_text or "").strip()
    if text and (duration_seconds is None or duration_seconds < 0.35):
        score -= 0.25
        notes.append("very short output for non-empty text")
    if expected_duration_seconds and duration_seconds is not None and expected_duration_seconds > 0:
        drift = abs(duration_seconds - expected_duration_seconds) / expected_duration_seconds
        if drift > 0.35:
            score -= min(0.25, drift * 0.25)
            notes.append("large duration drift")

    tts_valley_risk = _tts_valley_risk(
        segment_text=text,
        duration_seconds=duration_seconds,
        rms_db=rms_db,
        silence_ratio=silence_ratio,
    )
    if tts_valley_risk:
        score -= 0.15
        notes.append("short-line or low-energy TTS valley risk")

    score = round(max(0.0, min(1.0, score)), 3)
    verdict = "accepted" if score >= 0.72 else "needs_review"
    human_review_required = verdict != "accepted"
    return RenderFeedback(
        segment_id=str(segment_id),
        attempt=int(attempt),
        provider=str(provider or ""),
        model=str(model or ""),
        peak_db=_round_optional(peak_db),
        rms_db=_round_optional(rms_db),
        silence_ratio=_round_optional(silence_ratio, digits=4),
        duration_seconds=_round_optional(duration_seconds),
        clipping_detected=clipping_detected,
        tts_valley_risk=tts_valley_risk,
        score=score,
        verdict=verdict,
        human_review_required=human_review_required,
        notes=notes,
    )


def render_feedback_to_dict(feedback: RenderFeedback) -> dict[str, Any]:
    return asdict(feedback)


def directive_validation_to_dict(validation: DirectiveValidation) -> dict[str, Any]:
    return asdict(validation)


def directive_invalid_feedback(
    *,
    segment_id: str,
    attempt: int = 1,
    provider: str = "",
    model: str = "",
    validation: DirectiveValidation,
) -> RenderFeedback:
    notes = [validation.reason] if validation.reason else []
    notes.extend(validation.warnings)
    return RenderFeedback(
        segment_id=segment_id,
        attempt=attempt,
        provider=provider,
        model=model,
        peak_db=None,
        rms_db=None,
        silence_ratio=None,
        duration_seconds=None,
        clipping_detected=False,
        tts_valley_risk=False,
        score=0.0,
        verdict="directive_invalid",
        human_review_required=True,
        notes=notes,
    )


def build_retry_directive(
    directive: Mapping[str, Any],
    feedback: RenderFeedback,
    attempt: int,
) -> dict[str, Any]:
    """Build a conservative local retry directive without changing unknown keys."""

    adjusted = dict(directive or {})
    provider = str(adjusted.get("provider") or feedback.provider or "")
    intensity = _optional_float(adjusted.get("intensity"))
    silence_ratio = feedback.silence_ratio
    if feedback.tts_valley_risk:
        intensity = min(0.85, (intensity if intensity is not None else 0.5) + 0.10)
    if feedback.rms_db is not None and feedback.rms_db < -36:
        cap = _provider_safe_intensity_cap(provider)
        intensity = min(cap, (intensity if intensity is not None else 0.5) + 0.05)
    if intensity is not None:
        adjusted["intensity"] = round(intensity, 3)

    if silence_ratio is not None and silence_ratio > 0.45:
        for key in ("pause_before_ms", "pause_after_ms"):
            pause = _optional_float(adjusted.get(key))
            if pause is not None:
                adjusted[key] = max(0, int(round(pause * 0.8)))

    validation = validate_directive(adjusted, provider=provider)
    if not validation.valid:
        return dict(directive or {})
    adjusted["retry_attempt"] = int(attempt)
    adjusted["retry_source"] = "deterministic_adjustment"
    return adjusted


def render_feedback_effect_metadata(payload: Any) -> dict[str, Any]:
    """Return safe scalar effect-log metadata from render feedback payloads."""

    feedback = _feedback_records_from_payload(payload)
    validations = _directive_validations_from_payload(payload)
    metadata: dict[str, Any] = {}
    if feedback:
        review_records = [
            item for item in feedback if bool(item.get("human_review_required"))
        ]
        sortable = review_records or feedback
        worst = sorted(
            sortable,
            key=lambda item: _optional_float(item.get("score"))
            if _optional_float(item.get("score")) is not None
            else 999.0,
        )[0]
        score = _optional_float(worst.get("score"))
        metadata.update(
            {
                "render_feedback_score": score,
                "human_review_required": any(
                    bool(item.get("human_review_required")) for item in feedback
                ),
                "segment_id": str(worst.get("segment_id") or ""),
                "attempt": int(worst.get("attempt") or 1),
            }
        )
        selected = next((item for item in feedback if item.get("selected") is True), None)
        if selected:
            metadata["selected_attempt"] = int(selected.get("attempt") or 1)
        if str(worst.get("verdict") or "") == "directive_invalid":
            metadata["directive_valid"] = False
    if validations:
        metadata["directive_valid"] = all(bool(item.get("valid")) for item in validations)
    return metadata


def collect_render_feedback_records(payload: Any) -> list[dict[str, Any]]:
    """Collect render feedback records from a result, audio metadata, or effect entry."""

    records = _feedback_records_from_payload(payload)
    if records:
        return records
    if isinstance(payload, Mapping):
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("render_feedback_score") is not None:
            return [
                {
                    "segment_id": str(metadata.get("segment_id") or ""),
                    "attempt": int(metadata.get("attempt") or 1),
                    "score": _optional_float(metadata.get("render_feedback_score")),
                    "verdict": (
                        "directive_invalid"
                        if metadata.get("directive_valid") is False
                        else "needs_review"
                        if metadata.get("human_review_required")
                        else "accepted"
                    ),
                    "human_review_required": bool(metadata.get("human_review_required")),
                    "directive_valid": metadata.get("directive_valid"),
                }
            ]
    return []


def _provider_warnings(directive: Mapping[str, Any], provider_key: str) -> list[str]:
    warnings: list[str] = []
    voice = str(directive.get("voice") or "").strip()
    model = str(directive.get("model") or "").strip()
    if provider_key == "openai":
        if voice and voice not in KNOWN_OPENAI_VOICES:
            warnings.append(f"unknown OpenAI voice: {voice}")
        if model and model not in KNOWN_OPENAI_MODELS:
            warnings.append(f"unknown OpenAI model: {model}")
    if provider_key == "edge" and voice and not voice.startswith(KNOWN_EDGE_VOICE_PREFIXES):
        warnings.append(f"unknown Edge voice option: {voice}")
    return warnings


def _provider_safe_intensity_cap(provider: str) -> float:
    provider_key = _normalized(provider)
    if "chatterbox" in provider_key:
        return 0.95
    return 0.85


def _feedback_records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    raw = payload.get("render_feedback")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, Mapping)]
    for key in ("audio_metadata", "metadata"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            records = _feedback_records_from_payload(nested)
            if records:
                return records
    return []


def _directive_validations_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    raw = payload.get("directive_validations")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, Mapping)]
    single = payload.get("directive_validation")
    if isinstance(single, Mapping):
        return [dict(single)]
    for key in ("audio_metadata", "metadata"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            records = _directive_validations_from_payload(nested)
            if records:
                return records
    return []


def _read_audio_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"error": "audio file missing"}
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            frame_rate = audio.getframerate()
            frames = audio.readframes(audio.getnframes())
            return _metrics_from_pcm(
                frames,
                channels=channels,
                sample_width=sample_width,
                frame_rate=frame_rate,
            )
    except Exception as wave_error:
        try:
            return _read_with_pydub(path)
        except Exception:
            return {"error": f"unreadable audio: {wave_error}"}


def _read_with_pydub(path: Path) -> dict[str, Any]:
    from pydub import AudioSegment

    segment = AudioSegment.from_file(path)
    return _metrics_from_pcm(
        segment.raw_data,
        channels=segment.channels,
        sample_width=segment.sample_width,
        frame_rate=segment.frame_rate,
    )


def _metrics_from_pcm(
    frames: bytes,
    *,
    channels: int,
    sample_width: int,
    frame_rate: int,
) -> dict[str, Any]:
    if not frames or sample_width <= 0 or frame_rate <= 0 or channels <= 0:
        return {"error": "audio contains no PCM frames"}
    frame_count = len(frames) / (sample_width * channels)
    duration_seconds = frame_count / frame_rate
    peak = audioop.max(frames, sample_width)
    rms = audioop.rms(frames, sample_width)
    max_amplitude = float(2 ** (8 * sample_width - 1))
    peak_db = _dbfs(peak, max_amplitude)
    rms_db = _dbfs(rms, max_amplitude)
    clipping_threshold = int(max_amplitude * 0.98)
    clipping_detected = peak >= clipping_threshold
    silence_ratio = _silence_ratio(
        frames,
        channels=channels,
        sample_width=sample_width,
        frame_rate=frame_rate,
        threshold_db=-50.0,
    )
    return {
        "duration_seconds": duration_seconds,
        "peak_db": peak_db,
        "rms_db": rms_db,
        "silence_ratio": silence_ratio,
        "clipping_detected": clipping_detected,
    }


def _silence_ratio(
    frames: bytes,
    *,
    channels: int,
    sample_width: int,
    frame_rate: int,
    threshold_db: float,
) -> float:
    chunk_frames = max(1, int(frame_rate * 0.05))
    chunk_size = chunk_frames * sample_width * channels
    if chunk_size <= 0:
        return 1.0
    silent = 0
    total = 0
    max_amplitude = float(2 ** (8 * sample_width - 1))
    for start in range(0, len(frames), chunk_size):
        chunk = frames[start : start + chunk_size]
        if not chunk:
            continue
        total += 1
        if _dbfs(audioop.rms(chunk, sample_width), max_amplitude) <= threshold_db:
            silent += 1
    return silent / total if total else 1.0


def _tts_valley_risk(
    *,
    segment_text: str,
    duration_seconds: float | None,
    rms_db: float | None,
    silence_ratio: float | None,
) -> bool:
    words = len(segment_text.split())
    if words and words <= 4 and duration_seconds is not None and duration_seconds < 0.7:
        return True
    if rms_db is not None and rms_db < -36 and (silence_ratio or 0.0) > 0.2:
        return True
    return False


def _dbfs(value: int | float, max_amplitude: float) -> float:
    if value <= 0:
        return -96.0
    return 20.0 * math.log10(float(value) / max_amplitude)


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_optional(value: Any, *, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None
