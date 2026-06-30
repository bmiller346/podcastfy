"""Deterministic performance contracts for role-tagged LitRPG audio."""

from __future__ import annotations

import html
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.script_parser import parse_role_script
from podcastfy.tts.script_parser import RoleLine


ANNOUNCER_ROLES = {"SYSTEM", "ANNOUNCER", "SYSTEM_ANNOUNCER"}
ANNOUNCER_REGISTER_UNLOCK_CONDITIONS: dict[str, dict[str, Any]] = {
    "bureaucratic_default": {
        "scarcity_level": 1,
        "transition": "hold",
        "min_chapter": 1,
        "max_uses_per_book": None,
        "requires_apex_beat": False,
    },
    "hostile_pleasure": {
        "scarcity_level": 2,
        "transition": "slide",
        "min_chapter": 1,
        "max_uses_per_book": None,
        "requires_apex_beat": False,
    },
    "genuine_alarm": {
        "scarcity_level": 4,
        "transition": "snap",
        "min_chapter": 10,
        "max_uses_per_book": 3,
        "requires_apex_beat": False,
    },
    "corporate_panic": {
        "scarcity_level": 4,
        "transition": "slide",
        "min_chapter": 15,
        "max_uses_per_book": 4,
        "requires_apex_beat": False,
    },
    "genuine_awe": {
        "scarcity_level": 5,
        "transition": "collapse",
        "min_chapter": 30,
        "max_uses_per_book": 1,
        "requires_apex_beat": True,
    },
    "stripped_plain": {
        "scarcity_level": 5,
        "transition": "strip",
        "min_chapter": 30,
        "max_uses_per_book": 1,
        "requires_apex_beat": True,
    },
}


@dataclass(frozen=True, slots=True)
class AnnouncerRegister:
    """Controlled Announcer register shift metadata."""

    name: str
    transition_from: str | None
    transition_type: str
    earned_by: str
    scarcity_level: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    performance_register: str | None = None
    prior_register: str | None = None
    register_transition: str | None = None
    register_scarcity_level: int = 0
    register_earned_by: str = ""

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
        if self.performance_register:
            flags.append(f"performance register {self.performance_register}")
        if self.prior_register:
            flags.append(f"prior register {self.prior_register}")
        if self.register_transition:
            flags.append(f"register transition {self.register_transition}")
        if self.register_scarcity_level:
            flags.append(f"register scarcity {self.register_scarcity_level}")
        if self.register_earned_by:
            flags.append(f"register earned by {self.register_earned_by}")
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
    prior_register_by_role: dict[str, str] = {}
    cue_indices_by_role: dict[str, int] = {}
    for index, line in enumerate(lines, 1):
        cue = _cue_for_line(line.role, cues, cue_indices_by_role)
        source_style = str(line.style or "").strip()
        style_and_cue = " ".join(
            str(part or "")
            for part in (
                source_style,
                cue.get("emotion"),
                cue.get("delivery"),
                cue.get("timing"),
                cue.get("register"),
                cue.get("performance_register"),
                cue.get("announcer_register"),
            )
        ).casefold()
        register = _performance_register_for(line, cue, style_and_cue)
        prior_register = prior_register_by_role.get(line.role)
        transition = _register_transition_for(register, prior_register, cue)
        scarcity_level = _register_scarcity_level(register)
        earned_by = _register_earned_by(cue)
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
                reference_clip_id=_reference_clip_id_for(
                    role=line.role,
                    performance_register=register,
                    reference_clip_ids=references,
                ),
                source_style=source_style,
                performance_register=register,
                prior_register=prior_register,
                register_transition=transition,
                register_scarcity_level=scarcity_level,
                register_earned_by=earned_by,
            )
        )
        previous_role = line.role
        if register:
            prior_register_by_role[line.role] = register
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
        if contract.performance_register:
            role_summary += f", register {contract.performance_register}"
        if contract.register_transition:
            role_summary += f", transition {contract.register_transition}"
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


def _cues_by_role(cues: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    by_role: dict[str, list[Mapping[str, Any]]] = {}
    for cue in cues:
        role = str(cue.get("role") or "").upper()
        if role:
            by_role.setdefault(role, []).append(cue)
    return by_role


def _cue_for_line(
    role: str,
    cues_by_role: Mapping[str, Sequence[Mapping[str, Any]]],
    cue_indices_by_role: dict[str, int],
) -> Mapping[str, Any]:
    cues = list(cues_by_role.get(role) or [])
    if not cues:
        return {}
    index = cue_indices_by_role.get(role, 0)
    cue_indices_by_role[role] = index + 1
    if index < len(cues):
        return cues[index]
    return cues[-1]


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


def _performance_register_for(
    line: RoleLine,
    cue: Mapping[str, Any],
    style_and_cue: str,
) -> str | None:
    explicit = (
        cue.get("announcer_register")
        or cue.get("performance_register")
        or cue.get("register")
    )
    if explicit:
        return _normalize_register(str(explicit))
    if line.role not in ANNOUNCER_ROLES:
        return None
    if "genuine awe" in style_and_cue or "genuine_awe" in style_and_cue:
        return "genuine_awe"
    if "stripped" in style_and_cue or "plain" in style_and_cue:
        return "stripped_plain"
    if "corporate panic" in style_and_cue or "forced calm" in style_and_cue:
        return "corporate_panic"
    if "alarm" in style_and_cue or "destabilized" in style_and_cue:
        return "genuine_alarm"
    if "pleasure" in style_and_cue or "enjoying" in style_and_cue:
        return "hostile_pleasure"
    return "bureaucratic_default"


def _register_transition_for(
    performance_register: str | None,
    prior_register: str | None,
    cue: Mapping[str, Any],
) -> str | None:
    if not performance_register:
        return None
    explicit = cue.get("register_transition") or cue.get("transition_type")
    if explicit:
        return str(explicit).strip().lower().replace(" ", "_")
    if prior_register is None or prior_register == performance_register:
        return None
    rules = ANNOUNCER_REGISTER_UNLOCK_CONDITIONS.get(performance_register, {})
    return str(rules.get("transition") or "shift")


def _register_scarcity_level(performance_register: str | None) -> int:
    if not performance_register:
        return 0
    rules = ANNOUNCER_REGISTER_UNLOCK_CONDITIONS.get(performance_register, {})
    return int(rules.get("scarcity_level") or 1)


def _register_earned_by(cue: Mapping[str, Any]) -> str:
    return str(
        cue.get("register_earned_by")
        or cue.get("earned_by")
        or cue.get("trigger")
        or ""
    ).strip()


def _reference_clip_id_for(
    *,
    role: str,
    performance_register: str | None,
    reference_clip_ids: Mapping[str, str],
) -> str | None:
    role_key = role.upper()
    if performance_register:
        register_key = performance_register.upper()
        for key in (
            f"{role_key}:{register_key}",
            f"{role_key}/{register_key}",
            f"{role_key}.{register_key}",
        ):
            if key in reference_clip_ids:
                return reference_clip_ids[key]
    return reference_clip_ids.get(role_key)


def _normalize_register(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _safe_role(role: str) -> str:
    normalized = "".join(char for char in role.upper() if char.isalnum() or char in {"_", "-"})
    return normalized or "NARRATOR"
