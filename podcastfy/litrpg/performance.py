"""Deterministic performance contracts for role-tagged LitRPG audio."""

from __future__ import annotations

import html
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.script_parser import parse_role_script
from podcastfy.tts.script_parser import RoleLine


ANNOUNCER_ROLES = {"SYSTEM", "ANNOUNCER", "SYSTEM_ANNOUNCER"}


@dataclass(frozen=True, slots=True)
class LinePerformanceContract:
    """A line-level performance contract passed between script and audio."""

    line_id: str
    role: str
    text: str
    pace: str
    weight: str
    pause_before_ms: int
    pause_after_ms: int
    internal_state: str
    must_not_soften: bool = False
    must_not_comedify: bool = False
    reference_clip_id: str | None = None
    source_style: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def style_instruction(self) -> str:
        """Return compact provider-facing direction for this exact line."""

        flags = []
        if self.must_not_soften:
            flags.append("must not soften")
        if self.must_not_comedify:
            flags.append("must not comedify")
        if self.reference_clip_id:
            flags.append(f"reference clip {self.reference_clip_id}")
        if self.source_style:
            flags.append(f"source style {self.source_style}")
        flag_text = "; ".join(flags) if flags else "no extra interpretation"
        return (
            "Speak exactly the supplied text; do not add, omit, paraphrase, or rewrite. "
            f"pace {self.pace}; weight {self.weight}; internal state {self.internal_state}; "
            f"pause before {self.pause_before_ms}ms; pause after {self.pause_after_ms}ms; {flag_text}."
        )


def build_line_performance_contracts(
    script: str,
    *,
    director_cues: Sequence[Mapping[str, Any]] | None = None,
    reference_clip_ids: Mapping[str, str] | None = None,
) -> list[LinePerformanceContract]:
    """Build deterministic line contracts from role-tagged script and cue data."""

    cues = _cues_by_role(director_cues or [])
    references = {str(role).upper(): str(value) for role, value in dict(reference_clip_ids or {}).items()}
    lines = parse_role_script(script)
    contracts: list[LinePerformanceContract] = []
    previous_role = ""
    for index, line in enumerate(lines, 1):
        cue = cues.get(line.role, {})
        source_style = str(line.style or "").strip()
        style_and_cue = " ".join(
            str(part or "") for part in (source_style, cue.get("emotion"), cue.get("delivery"), cue.get("timing"))
        ).casefold()
        contracts.append(
            LinePerformanceContract(
                line_id=f"line-{index:04d}",
                role=line.role,
                text=line.text,
                pace=_pace_for(line, style_and_cue),
                weight=_weight_for(line, style_and_cue),
                pause_before_ms=180 if previous_role and previous_role != line.role else 0,
                pause_after_ms=_pause_after_ms(line.text, style_and_cue),
                internal_state=_internal_state_for(line, cue, style_and_cue),
                must_not_soften=_must_not_soften(line.role, style_and_cue),
                must_not_comedify=_must_not_comedify(line.role, style_and_cue),
                reference_clip_id=references.get(line.role),
                source_style=source_style,
            )
        )
        previous_role = line.role
    return contracts


def format_contract_script(contracts: Sequence[LinePerformanceContract]) -> str:
    """Render contracts back to role-tagged script with line-level style data."""

    blocks = []
    for contract in contracts:
        role = _safe_role(contract.role)
        style = html.escape(contract.style_instruction(), quote=True)
        text = html.escape(contract.text, quote=False)
        blocks.append(f'<{role} style="{style}">{text}</{role}>')
    return "\n".join(blocks)


def summarize_contracts_by_role(
    contracts: Sequence[LinePerformanceContract],
) -> dict[str, str]:
    """Return role-level summaries suitable for existing TTS instruction APIs."""

    summaries: dict[str, list[str]] = {}
    for contract in contracts:
        role_summary = (
            f"{contract.line_id}: exact-text performance, pace {contract.pace}, "
            f"weight {contract.weight}, state {contract.internal_state}"
        )
        if contract.must_not_soften:
            role_summary += ", do not soften"
        if contract.must_not_comedify:
            role_summary += ", do not comedify"
        summaries.setdefault(contract.role, []).append(role_summary)
    return {
        role: "Performance contract discipline: " + "; ".join(lines[:8]) + "."
        for role, lines in summaries.items()
    }


def merge_performance_role_instructions(
    base_instructions: Mapping[str, str],
    contracts: Sequence[LinePerformanceContract],
) -> dict[str, str]:
    """Append per-role performance summaries without losing baseline casting."""

    merged = {str(role).upper(): str(text) for role, text in dict(base_instructions or {}).items()}
    for role, summary in summarize_contracts_by_role(contracts).items():
        existing = merged.get(role, "").strip()
        merged[role] = f"{existing} {summary}".strip()
    return merged


def _cues_by_role(cues: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_role: dict[str, Mapping[str, Any]] = {}
    for cue in cues:
        role = str(cue.get("role") or "").upper()
        if role and role not in by_role:
            by_role[role] = cue
    return by_role


def _pace_for(line: RoleLine, style_and_cue: str) -> str:
    if any(word in style_and_cue for word in ("urgent", "breathless", "speed-up", "interrupt", "panic")):
        return "urgent"
    if any(word in style_and_cue for word in ("deadpan", "flat", "cold")):
        return "flat"
    if line.role in ANNOUNCER_ROLES or any(word in style_and_cue for word in ("clipped", "crisp")):
        return "clipped"
    if any(word in style_and_cue for word in ("slow", "grief", "dread", "reverent")):
        return "measured"
    return "measured"


def _weight_for(line: RoleLine, style_and_cue: str) -> str:
    text = line.text.casefold()
    if any(word in style_and_cue for word in ("grief", "dread", "awe", "threat", "triumph")):
        return "heavy"
    if any(word in text for word in ("warning", "quest", "penalty", "violation", "death", "cost")):
        return "heavy"
    if any(word in style_and_cue for word in ("joke", "light", "banter")):
        return "light"
    return "neutral"


def _pause_after_ms(text: str, style_and_cue: str) -> int:
    if any(word in style_and_cue for word in ("hard stop", "long pause")):
        return 450
    stripped = text.strip()
    if stripped.endswith("?"):
        return 260
    if stripped.endswith("!"):
        return 190
    return 140


def _internal_state_for(
    line: RoleLine,
    cue: Mapping[str, Any],
    style_and_cue: str,
) -> str:
    emotion = str(cue.get("emotion") or "").strip().replace(" ", "_")
    if emotion:
        return emotion
    if "false cheer" in style_and_cue:
        return "false_cheer"
    if any(word in style_and_cue for word in ("contempt", "hostile", "crisp", "clipped")):
        return "dry_hostility"
    if any(word in style_and_cue for word in ("fear", "panic")):
        return "genuine_fear"
    if line.role in ANNOUNCER_ROLES:
        return "dry_hostility"
    return "focused"


def _must_not_soften(role: str, style_and_cue: str) -> bool:
    return role in ANNOUNCER_ROLES or any(
        word in style_and_cue for word in ("hostile", "contempt", "dread", "threat", "grief")
    )


def _must_not_comedify(role: str, style_and_cue: str) -> bool:
    return role in ANNOUNCER_ROLES or any(
        word in style_and_cue for word in ("fear", "panic", "dread", "grief", "injury", "cost")
    )


def _safe_role(role: str) -> str:
    normalized = "".join(char for char in role.upper() if char.isalnum() or char in {"_", "-"})
    return normalized or "NARRATOR"
