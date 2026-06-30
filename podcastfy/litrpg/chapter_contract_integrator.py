"""Compact chapter contract assembly for subsystem outputs."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.comedy_pressure import build_comedy_beats
from podcastfy.litrpg.faction_ops import plan_faction_move
from podcastfy.litrpg.floor_identity import build_floor_identity
from podcastfy.litrpg.mechanics_engine import build_encounter_contract, format_encounter_context
from podcastfy.litrpg.promise_forge import format_promise_forge_context
from podcastfy.litrpg.setpiece_engine import build_setpiece_contract
from podcastfy.litrpg.threat_forge import forge_threat_contract


CONTEXT_KEYS = (
    "active_artifacts",
    "active_arc_pressure",
    "faction_move",
    "floor_identity",
    "encounter",
    "setpiece",
    "comedy_beats",
    "promise_forge",
    "forbidden_moves",
)


def assemble_chapter_contract(
    *,
    chapter_contract: Mapping[str, Any] | None = None,
    world_state: Mapping[str, Any] | None = None,
    arc_context: Mapping[str, Any] | None = None,
    conspiracy_context: Mapping[str, Any] | None = None,
    world_register: Mapping[str, Any] | None = None,
    floor_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble bounded, source-labeled context without exposing hidden truth."""

    chapter = dict(chapter_contract or {})
    world = dict(world_state or {})
    arcs = dict(arc_context or {})
    floor = build_floor_identity(
        floor=int(chapter.get("floor") or 1),
        floor_plan=floor_plan,
        world_register=world_register,
        chapter_contract=chapter,
    )
    threat = forge_threat_contract(floor_identity=floor, chapter_contract=chapter)
    encounter = build_encounter_contract(
        chapter_contract=chapter,
        character_state=world.get("characters") if isinstance(world.get("characters"), Mapping) else {},
        artifact_state=world.get("artifacts") if isinstance(world.get("artifacts"), Mapping) else {},
        threat_contract=threat,
        floor_identity=floor,
    )
    faction_move = plan_faction_move(
        conspiracy_context=conspiracy_context,
        chapter_contract=chapter,
        floor_identity=floor,
    )
    setpiece = build_setpiece_contract(
        chapter_contract=chapter,
        floor_identity=floor,
        encounter_contract=encounter,
    )
    comedy = build_comedy_beats(
        chapter_contract=chapter,
        setpiece_contract=setpiece,
        character_context=arcs,
    )
    return {
        "schema_version": 1,
        "source": "chapter_contract_integrator",
        "chapter": _compact_mapping(chapter, allowed=("book", "chapter", "title", "phase", "premise", "character_focus", "must_not_use")),
        "active_artifacts": _active_artifacts(world, chapter),
        "active_arc_pressure": _compact_arc_pressure(arcs),
        "faction_move": faction_move,
        "floor_identity": floor,
        "encounter": encounter,
        "setpiece": setpiece,
        "comedy_beats": comedy,
        "promise_forge": chapter.get("promise_forge") if isinstance(chapter.get("promise_forge"), Mapping) else {},
        "forbidden_moves": _forbidden_moves(chapter, arcs, conspiracy_context),
        "hidden_truth_isolated": True,
    }


def format_integrated_chapter_context(contract: Mapping[str, Any]) -> str:
    """Return prose-safe context blocks with internal source labels."""

    data = dict(contract or {})
    blocks = []
    if data.get("floor_identity"):
        floor = data["floor_identity"]
        blocks.append(
            "[floor_identity]\n"
            f"- grammar: {floor.get('name')} | visual={_join(floor.get('visual_grammar'))} | economy={_join(floor.get('economy'))}\n"
            f"- traversal: {floor.get('traversal_constraint')} | exploit={floor.get('exploit_pattern')}"
        )
    if data.get("encounter"):
        blocks.append(format_encounter_context(data["encounter"]))
    if data.get("faction_move"):
        move = data["faction_move"]
        blocks.append(
            "[faction_ops]\n"
            f"- {move.get('faction')}: action={move.get('visible_action')}; goal={move.get('apparent_goal')}; "
            f"hidden_label={move.get('hidden_motive_label')}; constraint={move.get('legal_system_constraint')}; "
            f"cost={move.get('cost')}; awareness={move.get('protagonist_awareness_level')}; "
            f"counterplay={move.get('counterplay_path')}"
        )
    if data.get("setpiece"):
        setpiece = data["setpiece"]
        blocks.append(
            "[setpiece_engine]\n"
            f"- toy={setpiece.get('toy')}; rule={setpiece.get('rule')}; wrong={setpiece.get('goes_wrong')}; image={setpiece.get('remembered_image')}"
        )
    if data.get("comedy_beats"):
        lines = ["[comedy_pressure]"]
        for beat in list(data.get("comedy_beats") or [])[:3]:
            if isinstance(beat, Mapping):
                lines.append(f"- {beat.get('pressure_source')}: {beat.get('setup')} -> {beat.get('escalation')} / {beat.get('grounding_reaction')}")
        blocks.append("\n".join(lines))
    promise_block = format_promise_forge_context(data.get("promise_forge") if isinstance(data.get("promise_forge"), Mapping) else None)
    if promise_block:
        blocks.append(promise_block)
    if data.get("active_artifacts"):
        blocks.append("[world_state.active_artifacts]\n" + "\n".join(f"- {item}" for item in data["active_artifacts"][:5]))
    if data.get("active_arc_pressure"):
        blocks.append("[emotional_arcs.active_pressure]\n" + "\n".join(f"- {item}" for item in data["active_arc_pressure"][:5]))
    if data.get("forbidden_moves"):
        blocks.append("[forbidden_moves]\n" + "\n".join(f"- {item}" for item in data["forbidden_moves"][:8]))
    return "\n\n".join(block for block in blocks if block)


def validate_integrated_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in CONTEXT_KEYS if key not in contract]
    issues = []
    payload = json.dumps({key: value for key, value in contract.items() if key != "hidden_truth_isolated"}).lower()
    if "truth_document" in payload:
        issues.append("truth_document leaked into integrated contract")
    return {"passed": not missing and not issues, "missing": missing, "issues": issues}


def _active_artifacts(world: Mapping[str, Any], chapter: Mapping[str, Any]) -> list[str]:
    wanted = {str(item) for item in _string_list(chapter.get("active_artifacts") or chapter.get("artifact_focus"))}
    artifacts = world.get("artifacts") if isinstance(world.get("artifacts"), Mapping) else {}
    lines = []
    for artifact_id, artifact in artifacts.items():
        if wanted and str(artifact_id) not in wanted:
            continue
        if not isinstance(artifact, Mapping):
            continue
        lines.append(f"{artifact_id}: locked_name={artifact.get('locked_name') or artifact_id}; state={artifact.get('state') or {}}")
    return lines[:5]


def _compact_arc_pressure(arcs: Mapping[str, Any]) -> list[str]:
    pressure = arcs.get("arc_pressure") if isinstance(arcs.get("arc_pressure"), Sequence) else []
    lines = []
    for item in pressure:
        if isinstance(item, Mapping):
            lines.append(f"{item.get('character')}: coping={item.get('current_coping_mode')}; allowed={item.get('allowed_shift')}")
    return lines


def _forbidden_moves(chapter: Mapping[str, Any], arcs: Mapping[str, Any], conspiracy: Mapping[str, Any] | None) -> list[str]:
    values = _string_list(chapter.get("must_not_use"))
    values.extend(_string_list(arcs.get("forbidden_arc_moves")))
    if isinstance(conspiracy, Mapping):
        values.extend(_string_list(conspiracy.get("forbidden_revelations")))
    return _dedupe(values)


def _compact_mapping(value: Mapping[str, Any], *, allowed: Sequence[str]) -> dict[str, Any]:
    return {key: value[key] for key in allowed if key in value}


def _join(value: Any) -> str:
    return "; ".join(_string_list(value)[:4])


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [str(item) for item in value.values() if str(item or "").strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value).strip() else []


def _dedupe(values: Sequence[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result
