"""Post-generation audio QA for LitRPG performance contracts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.performance import LinePerformanceContract


DEFAULT_VOICE_SIMILARITY_THRESHOLD = 0.82


@dataclass(frozen=True, slots=True)
class AudioPerformanceQAIssue:
    """One deterministic audio-performance QA issue or warning."""

    code: str
    message: str
    severity: str = "error"
    line_id: str = ""
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AudioPerformanceQAReport:
    """Post-generation QA result for generated audio."""

    ready: bool
    quarantine_required: bool
    transcript_checked: bool
    voice_similarity_checked: bool
    issues: list[AudioPerformanceQAIssue] = field(default_factory=list)
    warnings: list[AudioPerformanceQAIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "quarantine_required": self.quarantine_required,
            "transcript_checked": self.transcript_checked,
            "voice_similarity_checked": self.voice_similarity_checked,
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "issue_count": len(self.issues),
            "warning_count": len(self.warnings),
            "metadata": dict(self.metadata),
        }


def build_audio_performance_qa(
    contracts: Sequence[LinePerformanceContract],
    *,
    transcript_lines: Mapping[str, str] | Sequence[str] | None = None,
    voice_similarity_scores: Mapping[str, float] | None = None,
    voice_similarity_threshold: float = DEFAULT_VOICE_SIMILARITY_THRESHOLD,
) -> AudioPerformanceQAReport:
    """Validate generated audio evidence against exact performance contracts.

    ``transcript_lines`` should come from ASR after audio generation. It may be a
    mapping keyed by line_id or a sequence in contract order. ``voice_similarity``
    scores may be keyed by line_id or by role.
    """

    contract_list = list(contracts)
    issues: list[AudioPerformanceQAIssue] = []
    warnings: list[AudioPerformanceQAIssue] = []
    transcript_map = _transcript_map(contract_list, transcript_lines)
    transcript_checked = transcript_lines is not None
    if transcript_checked:
        issues.extend(_transcript_issues(contract_list, transcript_map))
    else:
        warnings.append(
            AudioPerformanceQAIssue(
                "transcript_unavailable",
                "No post-generation transcript was supplied; exact-text audio QA was not checked.",
                severity="warning",
            )
        )

    score_map = {
        str(key).upper(): float(value)
        for key, value in dict(voice_similarity_scores or {}).items()
        if _is_number(value)
    }
    voice_checked = bool(score_map)
    warnings.extend(_voice_similarity_warnings(contract_list, score_map))
    issues.extend(
        _voice_similarity_issues(
            contract_list,
            score_map,
            threshold=float(voice_similarity_threshold),
        )
    )

    return AudioPerformanceQAReport(
        ready=not issues,
        quarantine_required=bool(issues),
        transcript_checked=transcript_checked,
        voice_similarity_checked=voice_checked,
        issues=issues,
        warnings=warnings,
        metadata={
            "contract_count": len(contract_list),
            "voice_similarity_threshold": float(voice_similarity_threshold),
        },
    )


def quarantine_record_from_audio_qa(
    report: AudioPerformanceQAReport,
    *,
    audio_path: str,
    contracts: Sequence[LinePerformanceContract],
) -> dict[str, Any]:
    """Build a compact quarantine record for failed audio performance QA."""

    return {
        "status": "quarantined",
        "reason": "audio_performance_qa_failed",
        "audio_path": audio_path,
        "issues": [issue.to_dict() for issue in report.issues],
        "warnings": [warning.to_dict() for warning in report.warnings],
        "contracts": [contract.to_dict() for contract in contracts],
    }


def _transcript_map(
    contracts: Sequence[LinePerformanceContract],
    transcript_lines: Mapping[str, str] | Sequence[str] | None,
) -> dict[str, str]:
    if transcript_lines is None:
        return {}
    if isinstance(transcript_lines, Mapping):
        return {str(key): str(value) for key, value in transcript_lines.items()}
    return {
        contract.line_id: str(transcript_lines[index])
        for index, contract in enumerate(contracts)
        if index < len(transcript_lines)
    }


def _transcript_issues(
    contracts: Sequence[LinePerformanceContract],
    transcript_map: Mapping[str, str],
) -> list[AudioPerformanceQAIssue]:
    issues: list[AudioPerformanceQAIssue] = []
    for contract in contracts:
        if contract.line_id not in transcript_map:
            issues.append(
                AudioPerformanceQAIssue(
                    "missing_transcript_line",
                    f"No generated-audio transcript was supplied for {contract.line_id}.",
                    line_id=contract.line_id,
                    role=contract.role,
                )
            )
            continue
        expected = _normalize_spoken_text(contract.text)
        actual = _normalize_spoken_text(transcript_map[contract.line_id])
        if expected != actual:
            issues.append(
                AudioPerformanceQAIssue(
                    "transcript_text_mismatch",
                    f"{contract.line_id} transcript drifted from exact contract text.",
                    line_id=contract.line_id,
                    role=contract.role,
                )
            )
    return issues


def _voice_similarity_warnings(
    contracts: Sequence[LinePerformanceContract],
    score_map: Mapping[str, float],
) -> list[AudioPerformanceQAIssue]:
    warnings: list[AudioPerformanceQAIssue] = []
    if not score_map and any(contract.reference_clip_id for contract in contracts):
        warnings.append(
            AudioPerformanceQAIssue(
                "voice_similarity_unavailable",
                "Reference clips exist but no voice similarity scores were supplied.",
                severity="warning",
            )
        )
        return warnings
    for contract in contracts:
        if not contract.reference_clip_id:
            continue
        if _score_for_contract(contract, score_map) is None:
            warnings.append(
                AudioPerformanceQAIssue(
                    "voice_similarity_line_unchecked",
                    f"No voice similarity score was supplied for {contract.line_id}.",
                    severity="warning",
                    line_id=contract.line_id,
                    role=contract.role,
                )
            )
    return warnings


def _voice_similarity_issues(
    contracts: Sequence[LinePerformanceContract],
    score_map: Mapping[str, float],
    *,
    threshold: float,
) -> list[AudioPerformanceQAIssue]:
    issues: list[AudioPerformanceQAIssue] = []
    for contract in contracts:
        if not contract.reference_clip_id:
            continue
        score = _score_for_contract(contract, score_map)
        if score is not None and score < threshold:
            issues.append(
                AudioPerformanceQAIssue(
                    "voice_similarity_below_threshold",
                    f"{contract.line_id} voice similarity {score:.3f} fell below {threshold:.3f}.",
                    line_id=contract.line_id,
                    role=contract.role,
                )
            )
    return issues


def _score_for_contract(
    contract: LinePerformanceContract,
    score_map: Mapping[str, float],
) -> float | None:
    line_key = contract.line_id.upper()
    role_key = contract.role.upper()
    if line_key in score_map:
        return score_map[line_key]
    if role_key in score_map:
        return score_map[role_key]
    return None


def _normalize_spoken_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
