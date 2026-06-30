"""Audio rendering adapter for LitRPG role-tagged episode scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from podcastfy.litrpg.audio_provider import load_reference_clips
from podcastfy.litrpg.audio_provider import provider_name_for_contract
from podcastfy.litrpg.performance import build_line_performance_contracts
from podcastfy.litrpg.performance import format_contract_script
from podcastfy.litrpg.performance import merge_performance_role_instructions
from podcastfy.litrpg.performance_qa import build_audio_performance_qa
from podcastfy.litrpg.performance_qa import quarantine_record_from_audio_qa
from podcastfy.litrpg.script_parser import validate_audio_readiness
from podcastfy.litrpg.sfx import build_mix_plan
from podcastfy.litrpg.sfx import map_assets_for_cue_sheet
from podcastfy.litrpg.sfx import parse_cue_sheet
from podcastfy.litrpg.sfx_mix import mix_audio_locally
from podcastfy.litrpg.voice_processing import apply_voice_processing_to_file
from podcastfy.litrpg.voice_processing import voice_processing_chain_for_role

if TYPE_CHECKING:
    from podcastfy.text_to_speech import TextToSpeech


class RoleScriptRenderer:
    """Render an engine bundle's role-tagged script into bundle audio files."""

    def __init__(
        self,
        *,
        tts: "TextToSpeech",
        output_filename: str = "final.mp3",
        audio_qa_probe: Any | None = None,
        audio_performance_provider: Any | None = None,
    ) -> None:
        self.tts = tts
        self.output_filename = output_filename
        self.audio_qa_probe = audio_qa_probe
        self.audio_performance_provider = audio_performance_provider

    def render_episode(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        source_script = str(bundle.get("script_with_cues") or bundle.get("script") or "")
        cue_sheet_payload = bundle.get("cue_sheet")
        cue_sheet = (
            parse_cue_sheet(source_script)
            if not isinstance(cue_sheet_payload, Mapping)
            else cue_sheet_payload
        )
        script = str(cue_sheet.get("clean_script") if isinstance(cue_sheet, Mapping) else cue_sheet.clean_script)
        if not script.strip():
            raise ValueError("Cannot render LitRPG episode without a script")

        storage_metadata = dict(bundle.get("storage_metadata") or {})
        bundle_path = storage_metadata.get("bundle_path")
        if not bundle_path:
            raise ValueError("Cannot render LitRPG episode without bundle_path")

        audio_dir = Path(bundle_path) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        output_path = audio_dir / self.output_filename
        prose_gate = _prose_qa_gate_from_bundle(bundle)
        if not prose_gate["ready"]:
            return _write_skipped_audio_metadata(
                bundle_path=Path(bundle_path),
                output_path=output_path,
                prose_gate=prose_gate,
            )

        voice_map = _voice_map_from_config(dict(bundle.get("config") or {}))
        role_instructions = _role_instructions_from_config(dict(bundle.get("config") or {}))
        role_instructions.update(
            {
                str(role).upper(): str(instruction)
                for role, instruction in dict(bundle.get("role_instructions") or {}).items()
                if str(instruction).strip()
            }
        )
        role_tags = _role_tags_from_bundle(bundle, voice_map, role_instructions)
        raw_readiness = validate_audio_readiness(
            script,
            allowed_roles=role_tags,
            voice_map=voice_map,
            role_instructions=role_instructions,
            max_line_chars=int(bundle.get("max_tts_line_chars") or 900),
        )
        if not raw_readiness.ready:
            issue_text = "; ".join(issue.message for issue in raw_readiness.issues)
            raise ValueError(f"LitRPG audio readiness failed: {issue_text}")

        director_cues = _director_cues_from_bundle(bundle)
        performance_contracts = build_line_performance_contracts(
            script,
            director_cues=director_cues,
            reference_clip_ids=_reference_clip_ids_from_bundle(bundle),
        )
        contracted_script = format_contract_script(performance_contracts)
        role_instructions = merge_performance_role_instructions(
            role_instructions,
            performance_contracts,
        )
        readiness = validate_audio_readiness(
            contracted_script,
            allowed_roles=role_tags,
            voice_map=voice_map,
            role_instructions=role_instructions,
            max_line_chars=int(bundle.get("max_tts_line_chars") or 900),
        )
        if not readiness.ready:
            issue_text = "; ".join(issue.message for issue in readiness.issues)
            raise ValueError(f"LitRPG audio readiness failed: {issue_text}")

        audio_provider_routes: list[dict[str, Any]] = []
        if self.audio_performance_provider is not None:
            audio_provider_routes = _render_with_audio_performance_provider(
                self.audio_performance_provider,
                performance_contracts=performance_contracts,
                output_path=output_path,
                bundle=bundle,
                bundle_path=Path(bundle_path),
            )
        else:
            self.tts.convert_script_to_speech(
                contracted_script,
                str(output_path),
                voice_map,
                role_tags=role_tags or None,
                role_instructions=role_instructions,
            )

        voice_processing_result = _apply_dialogue_voice_processing(
            output_path=output_path,
            bundle=bundle,
            performance_contracts=performance_contracts,
        )
        dialogue_for_mix = Path(
            voice_processing_result.get("output_path")
            if voice_processing_result.get("processed")
            else output_path
        )

        asset_mappings = list(bundle.get("asset_mappings") or [])
        if not asset_mappings:
            asset_mappings = [
                mapping.to_dict()
                for mapping in map_assets_for_cue_sheet(cue_sheet)
            ]
        mix_plan = dict(bundle.get("mix_plan") or build_mix_plan(cue_sheet, asset_mappings=asset_mappings))
        mixed_path = audio_dir / f"{output_path.stem}_mixed{output_path.suffix}"
        mix_result = mix_audio_locally(
            dialogue_path=dialogue_for_mix,
            output_path=mixed_path,
            mix_plan=mix_plan,
            asset_mappings=asset_mappings,
        )
        transcript_lines = _transcript_lines_from_bundle(bundle)
        voice_similarity_scores = _voice_similarity_scores_from_bundle(bundle)
        probe_result = _run_audio_qa_probe(
            self.audio_qa_probe,
            audio_path=output_path,
            contracts=performance_contracts,
        )
        if transcript_lines is None:
            transcript_lines = probe_result.get("transcript_lines")
        if not voice_similarity_scores:
            voice_similarity_scores = probe_result.get("voice_similarity_scores") or {}
        audio_performance_qa = build_audio_performance_qa(
            performance_contracts,
            transcript_lines=transcript_lines,
            voice_similarity_scores=voice_similarity_scores,
            voice_similarity_threshold=float(
                bundle.get("voice_similarity_threshold") or 0.82
            ),
            performance_context=_performance_context_from_bundle(bundle),
        )

        metadata = {
            "status": "quarantined" if audio_performance_qa.quarantine_required else "rendered",
            "audio_path": str(output_path),
            "format": output_path.suffix.lstrip("."),
            "role_instructions": role_instructions,
            "voice_map": voice_map,
            "role_tags": role_tags,
            "audio_readiness": readiness.to_dict(),
            "director_cues": director_cues,
            "performance_contracts": [
                contract.to_dict() for contract in performance_contracts
            ],
            "audio_performance_qa": audio_performance_qa.to_dict(),
            "audio_provider_routes": audio_provider_routes,
            "voice_processing": voice_processing_result,
            "contracted_script": contracted_script,
            "cue_sheet": cue_sheet if isinstance(cue_sheet, Mapping) else cue_sheet.to_dict(),
            "asset_mappings": asset_mappings,
            "mix_plan": mix_plan,
            "mix_result": mix_result,
        }
        if mix_result.get("mixed"):
            metadata["mixed_audio_path"] = mix_result["output_path"]
        if audio_performance_qa.quarantine_required:
            quarantine_path = Path(bundle_path) / "audio_quarantine.json"
            with quarantine_path.open("w", encoding="utf-8") as quarantine_file:
                json.dump(
                    quarantine_record_from_audio_qa(
                        audio_performance_qa,
                        audio_path=str(output_path),
                        contracts=performance_contracts,
                    ),
                    quarantine_file,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                quarantine_file.write("\n")
            metadata["audio_quarantine_path"] = str(quarantine_path)
        metadata_path = Path(bundle_path) / "audio_metadata.json"
        with metadata_path.open("w", encoding="utf-8") as metadata_file:
            json.dump(metadata, metadata_file, ensure_ascii=True, indent=2, sort_keys=True)
            metadata_file.write("\n")
        metadata["audio_metadata_path"] = str(metadata_path)
        return metadata


def _write_skipped_audio_metadata(
    *,
    bundle_path: Path,
    output_path: Path,
    prose_gate: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = {
        "status": "skipped",
        "reason": str(prose_gate.get("reason") or "prose_qa_not_ready"),
        "audio_render_skipped": True,
        "audio_path": None,
        "planned_audio_path": str(output_path),
        "format": output_path.suffix.lstrip("."),
        "prose_qa_gate": dict(prose_gate),
        "audio_provider_routes": [],
        "voice_processing": {
            "processed": False,
            "reason": str(prose_gate.get("reason") or "prose_qa_not_ready"),
        },
    }
    metadata_path = bundle_path / "audio_metadata.json"
    with metadata_path.open("w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, ensure_ascii=True, indent=2, sort_keys=True)
        metadata_file.write("\n")
    metadata["audio_metadata_path"] = str(metadata_path)
    return metadata


def _voice_map_from_config(config: Mapping[str, Any]) -> dict[str, str]:
    voices = dict(config.get("voices") or {})
    voice_map: dict[str, str] = {}
    for role, voice_config in voices.items():
        if isinstance(voice_config, Mapping):
            voice = voice_config.get("voice")
        else:
            voice = voice_config
        if voice:
            voice_map[str(role).upper()] = str(voice)
    if "default" not in voice_map and "NARRATOR" in voice_map:
        voice_map["default"] = voice_map["NARRATOR"]
    return voice_map


def _prose_qa_gate_from_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return whether prose has passed upstream QA before audio spend."""

    evidence: dict[str, Any] = {}
    for label, value in _prose_ready_candidates(bundle):
        ready = _coerce_ready_value(value)
        if ready is None:
            continue
        evidence[label] = ready

    quarantine = bundle.get("quarantine")
    if isinstance(quarantine, Mapping):
        status = str(quarantine.get("status") or "").strip().lower()
        if status in {"quarantined", "blocked"}:
            evidence["quarantine.status"] = status

    blocked = [
        label
        for label, value in evidence.items()
        if value is False or str(value).lower() in {"quarantined", "blocked"}
    ]
    return {
        "ready": not blocked,
        "reason": "prose_qa_not_ready" if blocked else "",
        "blocked_by": blocked,
        "evidence": evidence,
    }


def _prose_ready_candidates(bundle: Mapping[str, Any]) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = []
    qa = bundle.get("qa")
    if isinstance(qa, Mapping) and "ready" in qa:
        candidates.append(("qa.ready", qa["ready"]))
    render = bundle.get("render")
    if isinstance(render, Mapping) and "ready" in render:
        candidates.append(("render.ready", render["ready"]))
    metadata = bundle.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("qa_ready", "render_ready"):
            if key in metadata:
                candidates.append((f"metadata.{key}", metadata[key]))
        metadata_qa = metadata.get("qa")
        if isinstance(metadata_qa, Mapping) and "ready" in metadata_qa:
            candidates.append(("metadata.qa.ready", metadata_qa["ready"]))
        metadata_render = metadata.get("render")
        if isinstance(metadata_render, Mapping) and "ready" in metadata_render:
            candidates.append(("metadata.render.ready", metadata_render["ready"]))
        audio_readiness = metadata.get("audio_readiness")
        if isinstance(audio_readiness, Mapping) and "render_ready" in audio_readiness:
            candidates.append(
                ("metadata.audio_readiness.render_ready", audio_readiness["render_ready"])
            )
    return candidates


def _coerce_ready_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "ready", "passed", "pass", "1"}:
        return True
    if text in {"false", "no", "not_ready", "blocked", "quarantined", "0"}:
        return False
    return None


def _role_instructions_from_config(config: Mapping[str, Any]) -> dict[str, str]:
    voices = dict(config.get("voices") or {})
    instructions: dict[str, str] = {}
    for role, voice_config in voices.items():
        if not isinstance(voice_config, Mapping):
            continue
        role_instruction = voice_config.get("instructions") or voice_config.get("style")
        if role_instruction:
            instructions[str(role).upper()] = str(role_instruction)
    return instructions


def _role_tags_from_bundle(
    bundle: Mapping[str, Any],
    voice_map: Mapping[str, str],
    role_instructions: Mapping[str, str],
) -> list[str]:
    explicit = bundle.get("role_tags")
    if isinstance(explicit, (list, tuple, set)):
        return sorted({str(role).upper() for role in explicit})
    roles = {
        role.upper()
        for role in [*voice_map.keys(), *role_instructions.keys()]
        if str(role).lower() != "default"
    }
    return sorted(roles)


def _director_cues_from_bundle(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    cues = bundle.get("director_cues")
    if isinstance(cues, list):
        return [dict(cue) for cue in cues if isinstance(cue, Mapping)]
    qa = bundle.get("qa")
    if not isinstance(qa, Mapping):
        metadata = bundle.get("metadata")
        qa = metadata.get("qa") if isinstance(metadata, Mapping) else None
    if not isinstance(qa, Mapping):
        return []
    extracted: list[dict[str, Any]] = []
    for part in qa.get("parts", []):
        if not isinstance(part, Mapping):
            continue
        audits = part.get("audits")
        director = audits.get("director") if isinstance(audits, Mapping) else None
        raw_cues = director.get("cues") if isinstance(director, Mapping) else None
        if isinstance(raw_cues, list):
            extracted.extend(dict(cue) for cue in raw_cues if isinstance(cue, Mapping))
    return extracted


def _reference_clip_ids_from_bundle(bundle: Mapping[str, Any]) -> dict[str, str]:
    references = bundle.get("reference_clip_ids") or bundle.get("voice_reference_clip_ids")
    if not isinstance(references, Mapping):
        references = {}
    normalized = {
        str(role).upper(): str(value)
        for role, value in dict(references).items()
        if str(value).strip()
    }
    config = bundle.get("config")
    voices = config.get("voices") if isinstance(config, Mapping) else None
    if isinstance(voices, Mapping):
        for role, voice_config in voices.items():
            if not isinstance(voice_config, Mapping):
                continue
            clip_id = voice_config.get("reference_clip_id")
            if clip_id and str(role).upper() not in normalized:
                normalized[str(role).upper()] = str(clip_id)
    return normalized


def _transcript_lines_from_bundle(bundle: Mapping[str, Any]) -> Any | None:
    for key in (
        "post_generation_transcript_lines",
        "generated_audio_transcript_lines",
        "audio_transcript_lines",
    ):
        value = bundle.get(key)
        if isinstance(value, Mapping):
            return {str(line_id): str(text) for line_id, text in value.items()}
        if isinstance(value, list):
            return [str(text) for text in value]
    return None


def _voice_similarity_scores_from_bundle(bundle: Mapping[str, Any]) -> dict[str, float]:
    value = (
        bundle.get("voice_similarity_scores")
        or bundle.get("post_generation_voice_similarity_scores")
    )
    if not isinstance(value, Mapping):
        return {}
    scores: dict[str, float] = {}
    for key, score in value.items():
        try:
            scores[str(key)] = float(score)
        except (TypeError, ValueError):
            continue
    return scores


def _run_audio_qa_probe(
    probe: Any,
    *,
    audio_path: Path,
    contracts: Sequence[Any],
) -> dict[str, Any]:
    if probe is None:
        return {}
    result: dict[str, Any] = {}
    if hasattr(probe, "transcribe_lines"):
        transcript = probe.transcribe_lines(
            audio_path=str(audio_path),
            contracts=list(contracts),
        )
        if transcript is not None:
            result["transcript_lines"] = transcript
    if hasattr(probe, "voice_similarity_scores"):
        scores = probe.voice_similarity_scores(
            audio_path=str(audio_path),
            contracts=list(contracts),
        )
        if scores is not None:
            result["voice_similarity_scores"] = scores
    return result


def _render_with_audio_performance_provider(
    provider_or_map: Any,
    *,
    performance_contracts: Sequence[Any],
    output_path: Path,
    bundle: Mapping[str, Any],
    bundle_path: Path,
) -> list[dict[str, Any]]:
    reference_clips = load_reference_clips(
        bundle.get("reference_clips") or bundle.get("reference_clip_paths"),
        base_dir=bundle_path,
    )
    routing_config = _audio_performance_config_from_bundle(bundle)
    routes: list[dict[str, Any]] = []
    chunks: list[bytes] = []
    for contract in performance_contracts:
        provider = provider_or_map
        provider_name = getattr(provider, "provider_name", "injected")
        if isinstance(provider_or_map, Mapping):
            provider_name = provider_name_for_contract(contract, routing_config)
            provider = provider_or_map.get(provider_name)
            if provider is None:
                raise ValueError(
                    f"No audio performance provider configured for {provider_name!r}"
                )
        audio = provider.render_line(contract, reference_clips)
        chunks.append(audio)
        routes.append(
            {
                "line_id": contract.line_id,
                "role": contract.role,
                "performance_register": contract.performance_register,
                "provider": provider_name,
            }
        )
    output_path.write_bytes(b"".join(chunks))
    return routes


def _apply_dialogue_voice_processing(
    *,
    output_path: Path,
    bundle: Mapping[str, Any],
    performance_contracts: Sequence[Any],
) -> dict[str, Any]:
    config = bundle.get("config")
    if not isinstance(config, Mapping):
        config = {}
    roles = [str(contract.role).upper() for contract in performance_contracts]
    role = roles[0] if roles and len(set(roles)) == 1 else "DIALOGUE"
    register = (
        str(performance_contracts[0].performance_register)
        if performance_contracts and len({contract.performance_register for contract in performance_contracts}) == 1
        else None
    )
    chain = voice_processing_chain_for_role(
        role,
        config.get("voice_processing") if isinstance(config.get("voice_processing"), Mapping) else {},
        performance_register=register,
    )
    processed_path = output_path.with_name(f"{output_path.stem}_processed{output_path.suffix}")
    result = apply_voice_processing_to_file(output_path, processed_path, chain)
    result["role"] = role
    result["performance_register"] = register
    return result


def _audio_performance_config_from_bundle(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    config = bundle.get("audio_performance")
    if isinstance(config, Mapping):
        return config
    config = bundle.get("audio_performance_routing")
    return config if isinstance(config, Mapping) else {}


def _performance_context_from_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in ("chapter_number", "chapter", "phase", "register_usage_counts"):
        if key in bundle:
            context[key] = bundle[key]
    metadata = bundle.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("chapter_number", "chapter", "phase", "register_usage_counts"):
            if key in metadata and key not in context:
                context[key] = metadata[key]
    chapter = bundle.get("chapter")
    if isinstance(chapter, Mapping):
        if "chapter_number" not in context and "number" in chapter:
            context["chapter_number"] = chapter["number"]
        for key in ("phase", "register_usage_counts"):
            if key in chapter and key not in context:
                context[key] = chapter[key]
    chapter_contract = bundle.get("chapter_contract")
    if isinstance(chapter_contract, Mapping):
        if "chapter_number" not in context and "chapter" in chapter_contract:
            context["chapter_number"] = chapter_contract["chapter"]
        for key in ("phase", "register_usage_counts"):
            if key in chapter_contract and key not in context:
                context[key] = chapter_contract[key]
    return context
