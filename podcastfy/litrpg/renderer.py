"""Audio rendering adapter for LitRPG role-tagged episode scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

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
        script = str(bundle.get("script") or "")
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
        self.tts.convert_script_to_speech(
            script,
            str(output_path),
            voice_map,
            role_instructions=role_instructions,
        )

        metadata = {
            "audio_path": str(output_path),
            "format": output_path.suffix.lstrip("."),
            "role_instructions": role_instructions,
            "voice_map": voice_map,
        }
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
