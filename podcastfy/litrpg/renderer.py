"""Audio rendering adapter for LitRPG role-tagged episode scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from podcastfy.litrpg.script_parser import validate_audio_readiness
from podcastfy.litrpg.sfx import build_mix_plan
from podcastfy.litrpg.sfx import map_assets_for_cue_sheet
from podcastfy.litrpg.sfx import parse_cue_sheet
from podcastfy.litrpg.sfx_mix import mix_audio_locally

if TYPE_CHECKING:
    from podcastfy.text_to_speech import TextToSpeech


class RoleScriptRenderer:
    """Render an engine bundle's role-tagged script into bundle audio files."""

    def __init__(
        self,
        *,
        tts: "TextToSpeech",
        output_filename: str = "final.mp3",
    ) -> None:
        self.tts = tts
        self.output_filename = output_filename

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
        readiness = validate_audio_readiness(
            script,
            allowed_roles=role_tags,
            voice_map=voice_map,
            role_instructions=role_instructions,
            max_line_chars=int(bundle.get("max_tts_line_chars") or 900),
        )
        if not readiness.ready:
            issue_text = "; ".join(issue.message for issue in readiness.issues)
            raise ValueError(f"LitRPG audio readiness failed: {issue_text}")

        self.tts.convert_script_to_speech(
            script,
            str(output_path),
            voice_map,
            role_tags=role_tags or None,
            role_instructions=role_instructions,
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
            dialogue_path=output_path,
            output_path=mixed_path,
            mix_plan=mix_plan,
            asset_mappings=asset_mappings,
        )

        metadata = {
            "audio_path": str(output_path),
            "format": output_path.suffix.lstrip("."),
            "role_instructions": role_instructions,
            "voice_map": voice_map,
            "role_tags": role_tags,
            "audio_readiness": readiness.to_dict(),
            "director_cues": _director_cues_from_bundle(bundle),
            "cue_sheet": cue_sheet if isinstance(cue_sheet, Mapping) else cue_sheet.to_dict(),
            "asset_mappings": asset_mappings,
            "mix_plan": mix_plan,
            "mix_result": mix_result,
        }
        if mix_result.get("mixed"):
            metadata["mixed_audio_path"] = mix_result["output_path"]
        metadata_path = Path(bundle_path) / "audio_metadata.json"
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
