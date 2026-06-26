"""Compatibility helpers for LitRPG role-script parsing and render readiness."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from podcastfy.tts.script_parser import RoleLine, RoleScriptParseError, parse_role_script


ROLE_TAG_RE = re.compile(
    r"<\s*(?P<close>/)?\s*(?P<role>[A-Za-z][\w-]*)\b(?P<attrs>[^>]*)>",
    re.DOTALL,
)
STYLE_ATTR_RE = re.compile(r"""\bstyle\s*=\s*(['"])(?P<style>.*?)\1""", re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
CUE_TAG_RE = re.compile(
    r"\[(?:BGM_START|BGM_STOP|SFX|AMBIENCE_START|AMBIENCE_STOP)(?::\s*[^\]]*?)?\]",
    re.IGNORECASE,
)


@dataclass(slots=True)
class AudioReadinessIssue:
    """One deterministic issue that should be fixed before paid TTS runs."""

    code: str
    message: str
    severity: str = "error"
    role: str | None = None
    line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AudioReadinessReport:
    """Validation report for role-tagged scripts before final rendering."""

    ready: bool
    issues: list[AudioReadinessIssue]
    warnings: list[AudioReadinessIssue]
    roles: list[str]
    line_count: int
    max_line_chars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "roles": list(self.roles),
            "line_count": self.line_count,
            "max_line_chars": self.max_line_chars,
            "issue_count": len(self.issues),
            "warning_count": len(self.warnings),
        }


def validate_audio_readiness(
    script: str,
    *,
    allowed_roles: Iterable[str] | None = None,
    required_roles: Iterable[str] | None = None,
    voice_map: Mapping[str, str] | None = None,
    role_instructions: Mapping[str, str] | None = None,
    max_line_chars: int = 900,
) -> AudioReadinessReport:
    """Validate a role-tagged script before spending TTS provider calls.

    This intentionally lives next to the compatibility parser instead of
    changing ``parse_role_script`` behavior: lower-level parser callers can keep
    accepting loose markup, while final audio rendering gets a hard gate.
    """
    text = str(script or "")
    issues: list[AudioReadinessIssue] = []
    warnings: list[AudioReadinessIssue] = []
    allowed = {str(role).upper() for role in allowed_roles or []}
    required = {str(role).upper() for role in required_roles or []}
    voices = {str(role).upper(): str(voice) for role, voice in dict(voice_map or {}).items()}
    instructions = {
        str(role).upper(): str(value)
        for role, value in dict(role_instructions or {}).items()
        if str(value).strip()
    }

    if not text.strip():
        issues.append(AudioReadinessIssue("empty_script", "Script is empty."))
        return AudioReadinessReport(False, issues, warnings, [], 0, max_line_chars)

    issues.extend(_attribute_issues(text))
    issues.extend(_outside_dialogue_issues(text))

    try:
        lines = parse_role_script(text)
    except RoleScriptParseError as exc:
        issues.append(
            AudioReadinessIssue(
                "malformed_dialogue",
                f"Malformed role-tagged dialogue: {exc}",
            )
        )
        lines = []

    roles = sorted({line.role for line in lines})
    present_roles = set(roles)
    unknown_roles = sorted(role for role in present_roles if allowed and role not in allowed)
    if unknown_roles:
        issues.append(
            AudioReadinessIssue(
                "unsupported_role",
                f"Unsupported role tags: {', '.join(unknown_roles)}.",
            )
        )

    missing_required = sorted(role for role in required if role not in present_roles)
    if missing_required:
        issues.append(
            AudioReadinessIssue(
                "missing_required_role",
                f"Missing required role tags: {', '.join(missing_required)}.",
            )
        )

    default_voice = voices.get("DEFAULT") or voices.get("default")
    for line_number, line in enumerate(lines, 1):
        if len(line.text) > max_line_chars:
            issues.append(
                AudioReadinessIssue(
                    "overlong_line",
                    f"{line.role} line has {len(line.text)} characters; split it below {max_line_chars}.",
                    role=line.role,
                    line_number=line_number,
                )
            )
        if voices and not (voices.get(line.role) or default_voice):
            issues.append(
                AudioReadinessIssue(
                    "missing_voice",
                    f"No voice configured for role {line.role}.",
                    role=line.role,
                    line_number=line_number,
                )
            )
        if line.style and line.role not in instructions:
            warnings.append(
                AudioReadinessIssue(
                    "style_without_role_instruction",
                    f"{line.role} has a line style but no base role instruction.",
                    severity="warning",
                    role=line.role,
                    line_number=line_number,
                )
            )

    return AudioReadinessReport(
        ready=not issues,
        issues=issues,
        warnings=warnings,
        roles=roles,
        line_count=len(lines),
        max_line_chars=max_line_chars,
    )


def _attribute_issues(script: str) -> list[AudioReadinessIssue]:
    issues: list[AudioReadinessIssue] = []
    for match in ROLE_TAG_RE.finditer(COMMENT_RE.sub("", script)):
        if match.group("close"):
            continue
        role = match.group("role").upper()
        attrs = (match.group("attrs") or "").strip()
        if not attrs:
            continue
        style_match = STYLE_ATTR_RE.search(attrs)
        without_style = STYLE_ATTR_RE.sub("", attrs).strip()
        line_number = script.count("\n", 0, match.start()) + 1
        if re.search(r"\bstyle\s*=", attrs) and style_match is None:
            issues.append(
                AudioReadinessIssue(
                    "malformed_style_attribute",
                    f"Malformed style attribute on <{role}>; quote style values.",
                    role=role,
                    line_number=line_number,
                )
            )
        if without_style:
            issues.append(
                AudioReadinessIssue(
                    "unsupported_attribute",
                    f"Unsupported attributes on <{role}>: {without_style}. Only style is supported.",
                    role=role,
                    line_number=line_number,
                )
            )
    return issues


def _outside_dialogue_issues(script: str) -> list[AudioReadinessIssue]:
    scrubbed = CUE_TAG_RE.sub("", COMMENT_RE.sub("", script))
    stack_depth = 0
    cursor = 0
    issues: list[AudioReadinessIssue] = []
    for match in ROLE_TAG_RE.finditer(scrubbed):
        gap = scrubbed[cursor : match.start()]
        if stack_depth == 0 and gap.strip():
            issues.append(
                AudioReadinessIssue(
                    "text_outside_role_tags",
                    "Text outside role tags will not be rendered reliably.",
                    line_number=scrubbed.count("\n", 0, cursor) + 1,
                )
            )
            break
        stack_depth += -1 if match.group("close") else 1
        stack_depth = max(stack_depth, 0)
        cursor = match.end()
    tail = scrubbed[cursor:]
    if not issues and stack_depth == 0 and tail.strip():
        issues.append(
            AudioReadinessIssue(
                "text_outside_role_tags",
                "Text outside role tags will not be rendered reliably.",
                line_number=scrubbed.count("\n", 0, cursor) + 1,
            )
        )
    return issues


__all__ = [
    "AudioReadinessIssue",
    "AudioReadinessReport",
    "RoleLine",
    "RoleScriptParseError",
    "parse_role_script",
    "validate_audio_readiness",
]
