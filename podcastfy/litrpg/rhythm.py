"""Prose rhythm and reader-proxy prompt helpers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TargetRhythm:
    """Deterministic prose rhythm targets derived from a chapter contract."""

    tempo: str
    sentence_rhythm: str
    humor_timing: str
    density_length_discipline: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def classify_target_rhythm(chapter_contract: Mapping[str, Any] | None) -> TargetRhythm:
    """Classify prose rhythm targets from explicit or numeric contract values."""

    contract = dict(chapter_contract or {})
    tempo = _first_text(
        contract,
        "tempo",
        "pacing",
        "pace",
        "rhythm",
        fallback=_tempo_from_tension(contract.get("tension") or contract.get("base_tension")),
    )
    normalized_tempo = _normalize_tempo(tempo)
    sentence_rhythm = _first_text(
        contract,
        "sentence_rhythm",
        "sentenceRhythm",
        "sentence_cadence",
        fallback=_sentence_rhythm_for_tempo(normalized_tempo),
    )
    humor_timing = _first_text(
        contract,
        "humor_timing",
        "humorTiming",
        "comic_timing",
        fallback=_humor_timing(
            contract.get("absurdity"),
            tension=contract.get("tension") or contract.get("base_tension"),
        ),
    )
    density = _first_text(
        contract,
        "density_length_discipline",
        "density",
        "length_discipline",
        "lengthDiscipline",
        fallback=_density_length_discipline(
            normalized_tempo,
            creativity=contract.get("creativity"),
        ),
    )
    return TargetRhythm(
        tempo=normalized_tempo,
        sentence_rhythm=sentence_rhythm,
        humor_timing=humor_timing,
        density_length_discipline=density,
    )


def build_prose_rhythm_prompt(
    final_script: str,
    chapter_contract: Mapping[str, Any] | None = None,
    genre: str = "LitRPG",
) -> str:
    """Build a strict-JSON prose rhythm validation prompt."""

    target = classify_target_rhythm(chapter_contract)
    profile = _genre_profile(genre)
    schema = {
        "verdict": "pass|revise|block",
        "scores": {
            "tempo_match": "0-10",
            "sentence_rhythm": "0-10",
            "humor_timing": "0-10",
            "density_length_discipline": "0-10",
            "read_aloud_flow": "0-10",
        },
        "paragraph_fixes": [
            {
                "paragraph_index": 1,
                "problem": "specific rhythm issue",
                "fix_instruction": "concrete rewrite instruction, not rewritten prose",
            }
        ],
        "blocking_issue": "",
    }
    return f"""Prose Rhythm Validator for a {profile["story_label"]}.

Target rhythm:
{json.dumps(target.to_dict(), indent=2, sort_keys=True)}

Chapter contract:
{json.dumps(_jsonable(chapter_contract or {}), indent=2, sort_keys=True)}

Validate the final script against the target rhythm. Score only the prose surface: tempo control, sentence rhythm, humor timing, density/length discipline, and read-aloud flow.

Rules:
- Return only strict JSON. No markdown, commentary, or prose outside the JSON object.
- Use the exact top-level keys in this schema: verdict, scores, paragraph_fixes, blocking_issue.
- paragraph_fixes must name paragraph-level repair instructions; do not rewrite the full script.
- A pass requires every score to be 8 or higher and no blocking issue.
- Apply {profile["cleverness_constraint"]}.
- Penalize paragraphs that violate tempo value "{target.tempo}" or sentence rhythm "{target.sentence_rhythm}".

JSON schema:
{json.dumps(schema, indent=2, sort_keys=True)}

Final script:
{final_script}"""


def build_reader_proxy_prompt(
    final_script: str,
    chapter_contract: Mapping[str, Any] | None = None,
    genre: str = "LitRPG",
) -> str:
    """Build a strict-JSON reader-proxy scoring prompt."""

    target = classify_target_rhythm(chapter_contract)
    profile = _genre_profile(genre)
    schema = {
        "verdict": "pass|revise|block",
        "scores": {
            "binge_worthiness": "0-10",
            "surprise_novelty": "0-10",
            "genre_specific_cleverness_lateral_intelligence": "0-10",
            "next_chapter_desire": "0-10",
        },
        "reader_proxy_notes": [
            {
                "category": "binge_worthiness|surprise_novelty|genre_specific_cleverness_lateral_intelligence|next_chapter_desire",
                "issue": "what a target reader feels",
                "fix_instruction": "specific revision pressure",
            }
        ],
        "blocking_issue": "",
    }
    return f"""Reader Proxy for a {profile["story_label"]}.

Target rhythm:
{json.dumps(target.to_dict(), indent=2, sort_keys=True)}

Chapter contract:
{json.dumps(_jsonable(chapter_contract or {}), indent=2, sort_keys=True)}

Score the final script as a target reader deciding whether to keep listening immediately.

Rules:
- Return only strict JSON. No markdown, commentary, or prose outside the JSON object.
- Score binge-worthiness, surprise/novelty, {profile["cleverness_metric"]}, and next-chapter desire.
- Apply {profile["cleverness_constraint"]}.
- Reward endings that create clear next-chapter desire without spending protected reveals too early.
- Use tempo value "{target.tempo}" as reader-experience context, not as a standalone plot score.
- A pass requires every score to be 8 or higher and no blocking issue.

JSON schema:
{json.dumps(schema, indent=2, sort_keys=True)}

Final script:
{final_script}"""


def parse_verdict_and_scores(text: str) -> dict[str, Any]:
    """Parse verdict and scores from a JSON response or embedded JSON object."""

    data = _loads_json_object(text)
    scores = data.get("scores") if isinstance(data.get("scores"), Mapping) else {}
    parsed_scores: dict[str, int | float] = {}
    for key, value in scores.items():
        if isinstance(value, (int, float)):
            parsed_scores[str(key)] = value
            continue
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        if match:
            number = float(match.group(0))
            parsed_scores[str(key)] = int(number) if number.is_integer() else number
    return {
        "verdict": str(data.get("verdict") or "").lower(),
        "scores": parsed_scores,
    }


def _genre_profile(genre: str) -> dict[str, str]:
    clean = (genre or "story").strip()
    if "litrpg" in clean.casefold():
        return {
            "story_label": "LitRPG audio chapter",
            "cleverness_metric": "DCC/LitRPG lateral intelligence",
            "cleverness_constraint": (
                "the DCC/LitRPG lateral intelligence constraint: clever solutions "
                "must use established mechanics, inventory, spatial rules, stat tradeoffs, "
                "quest wording, cooldowns, or system loopholes instead of generic luck"
            ),
        }
    label = clean if clean else "generic"
    return {
        "story_label": f"{label} story chapter",
        "cleverness_metric": "generic story cleverness and lateral intelligence",
        "cleverness_constraint": (
            f"generic story logic for {label}: clever turns must be motivated by character, "
            "setup, pressure, place, and consequence rather than game mechanics"
        ),
    }


def _first_text(mapping: Mapping[str, Any], *keys: str, fallback: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _normalize_tempo(value: str) -> str:
    clean = str(value or "").strip()
    lowered = clean.casefold()
    if any(word in lowered for word in ("frantic", "fast", "high", "urgent", "sprint")):
        return "fast"
    if any(word in lowered for word in ("slow", "low", "quiet", "breathing")):
        return "slow"
    if any(word in lowered for word in ("moderate", "mid", "steady", "balanced")):
        return "moderate"
    return clean or "moderate"


def _tempo_from_tension(value: Any) -> str:
    tension = _number(value)
    if tension is None:
        return "moderate"
    if tension >= 7:
        return "fast"
    if tension <= 3:
        return "slow"
    return "moderate"


def _sentence_rhythm_for_tempo(tempo: str) -> str:
    if tempo == "fast":
        return "short punchy sentences with clipped escalation and minimal interior drift"
    if tempo == "slow":
        return "longer sensory lines mixed with clean short turns for emphasis"
    return "varied medium sentences alternating action, reaction, and brief reflection"


def _humor_timing(absurdity: Any, *, tension: Any) -> str:
    absurdity_value = _number(absurdity)
    tension_value = _number(tension)
    if tension_value is not None and tension_value >= 7:
        return "micro-jokes after danger beats only; never deflate injury or stakes"
    if absurdity_value is not None and absurdity_value >= 7:
        return "frequent absurd reveals with grounded character reactions as the laugh beat"
    if absurdity_value is not None and absurdity_value <= 3:
        return "dry restraint; jokes land as pressure relief after consequence"
    return "banter and observation spaced between plot turns without stalling momentum"


def _density_length_discipline(tempo: str, *, creativity: Any) -> str:
    creativity_value = _number(creativity)
    if tempo == "fast":
        return "lean paragraphs, no lore dumps, one image or tactic per beat"
    if creativity_value is not None and creativity_value >= 7:
        return "specific weird details allowed, but each paragraph must advance choice or consequence"
    if tempo == "slow":
        return "room for texture, but every paragraph needs a purpose and clean exit line"
    return "moderate density with concise setup, payoff, and transition discipline"


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
    except TypeError:
        if isinstance(value, Mapping):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_jsonable(item) for item in value]
        return str(value)
    return value


def _loads_json_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            return {}
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}
