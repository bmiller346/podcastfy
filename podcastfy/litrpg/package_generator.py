"""LLM-driven series package generation for local audio serials."""

from __future__ import annotations

import importlib
import json
from typing import Any, Mapping

from podcastfy.litrpg.prompts import ROLE_TAGS


PACKAGE_GENERATOR_STAGE = "series_package"
SERIES_PACKAGE_SCHEMA_VERSION = 1
MINIMUM_CHARACTER_PACKAGES = 15


def build_series_package_prompt(
    *,
    premise: str,
    series_id: str = "",
    genre: str = "",
    baseline_text: str = "",
    target_character_count: int = MINIMUM_CHARACTER_PACKAGES,
) -> str:
    """Build the prompt that turns a premise into reusable series artifacts."""

    role_tags = ", ".join(ROLE_TAGS)
    genre_label = genre.strip() or "audio serial"
    is_litrpg = "litrpg" in genre_label.casefold()
    mechanics_note = (
        "LitRPG class, skill, stat, loot, or mechanic hook"
        if is_litrpg
        else "genre-specific story function, ability, job, social role, or recurring hook"
    )
    package_name = (
        "LitRPG audio series package" if is_litrpg else f"{genre_label} audio series package"
    )
    generator_name = (
        "litrpg-series-package" if is_litrpg else "audio-series-package"
    )
    mechanics_requirement = (
        "Make mechanics practical and story-driving: class hooks, home-base rules, faction leverage, and bizarre loot logic."
        if is_litrpg
        else "Make story rules practical and reusable: character constraints, setting rules, faction or relationship leverage, recurring set pieces, and escalation logic."
    )
    baseline_section = (
        baseline_text.strip()
        if baseline_text.strip()
        else "No baseline package was provided. Invent a fresh but reusable style bible."
    )
    return f"""Create a reusable {package_name} from this premise.

Series id: {series_id or "derive a short stable slug from the premise"}
Genre/style: {genre_label}
Premise:
{premise.strip()}

Baseline package or style seed:
{baseline_section}

Return only one JSON object. Do not include markdown fences or commentary.

Required top-level shape:
{{
  "schema_version": {SERIES_PACKAGE_SCHEMA_VERSION},
  "series_id": "short-series-id",
  "premise": "clean premise summary",
  "metadata": {{
    "generator": "{generator_name}",
    "genre": "{genre_label}",
    "baseline_used": true,
    "notes": []
  }},
  "system_announcer": {{
    "name": "System Announcer",
    "voice_pillars": [],
    "tone_rules": [],
    "sample_announcements": [],
    "audio_notes": [],
    "forbidden_moves": []
  }},
  "characters": [
    {{
      "role": "HERO",
      "name": "Character name",
      "function": "story function",
      "class_or_mechanic": "{mechanics_note}",
      "personality": [],
      "voice": {{
        "archetype": "distinct acoustic/personality profile",
        "delivery": "how they sound",
        "pace": "slow/medium/fast",
        "sample_lines": []
      }},
      "arc": [],
      "audio_notes": []
    }}
  ],
  "familiar": {{
    "name": "",
    "system_role": "",
    "stat_sheet": {{}},
    "vocabulary": [],
    "sample_lines": [],
    "audio_notes": []
  }},
  "home_base": {{
    "name": "",
    "advantages": [],
    "vulnerabilities": [],
    "upgrade_hooks": [],
    "audio_notes": []
  }},
  "floor_rules": {{
    "floor_one": [],
    "mechanics": [],
    "failure_states": [],
    "reward_logic": []
  }},
  "faction_map": [
    {{
      "name": "",
      "agenda": "",
      "attitude_to_protagonists": "",
      "audio_identity": ""
    }}
  ],
  "bestiary": [
    {{
      "name": "",
      "entity_type": "mob|monster|suspect|hazard|anomaly|creature|rival",
      "category": "",
      "first_seen": "",
      "recurrence": "",
      "visual_signature": [],
      "behavior_rules": [],
      "abilities": [],
      "weaknesses": [],
      "resistances": [],
      "loot_table": [],
      "voice": "",
      "rules": [],
      "notes": []
    }}
  ],
  "encounters": [
    {{
      "name": "",
      "encounter_type": "boss|setpiece|case|scene-threat|social encounter|mystery beat",
      "status": "planned|active|defeated|escaped|recurring",
      "location": "",
      "first_seen": "",
      "participants": [],
      "phase_rules": [],
      "weaknesses": [],
      "stakes": "",
      "resolution": "",
      "rewards": [],
      "return_conditions": [],
      "rules": [],
      "notes": []
    }}
  ],
  "sample_announcements": [],
  "audio_performance_notes": []
}}

Generation requirements:
- Create at least {target_character_count} character or role packages.
- Include the major premise leads plus useful recurring roles, rivals, factions, vendors, bosses, and game-show/audience voices.
- Include durable bestiary/world-entity entries for recurring mobs, monsters, suspects, hazards, anomalies, or creature types that should not be reinvented later.
- Include encounter entries for specific bosses, fights, cases, mystery scenes, setpieces, or social threats that may be referenced later.
- If the chosen genre has no System, announcer, stats, or game-show layer, keep those fields empty or reinterpret them as narrator/showrunner/audio-production guidance.
- Keep any announcer or system voice distinct from direct imitation of existing performers or franchises.
- If baseline text is provided, preserve its useful structure and performance intent, but adapt it to this original series.
- {mechanics_requirement}
- Write for audio production: sample lines, timing, delivery, and reusable voice direction.
- Use preferred role tags where useful: {role_tags}.
"""


def generate_series_package(
    *,
    premise: str,
    llm: Any,
    series_id: str = "",
    genre: str = "",
    baseline_text: str = "",
    storage_dir: str | None = None,
    save: bool = False,
) -> dict[str, Any]:
    """Generate, coerce, validate, and optionally save a series package draft."""

    prompt = build_series_package_prompt(
        premise=premise,
        series_id=series_id,
        genre=genre,
        baseline_text=baseline_text,
    )
    raw_response = llm.generate(prompt=prompt, stage=PACKAGE_GENERATOR_STAGE)
    draft = extract_series_package_json(raw_response)
    package = coerce_series_package(
        draft,
        premise=premise,
        series_id=series_id,
        genre=genre,
        baseline_text=baseline_text,
    )
    if save:
        save_generated_series_package(package, storage_dir=storage_dir)
    return package


def extract_series_package_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response."""

    decoder = json.JSONDecoder()
    source = _strip_json_fence(str(text or "").strip())
    for index, char in enumerate(source):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(source[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("Series package response did not contain a JSON object")


def coerce_series_package(
    data: Mapping[str, Any] | None,
    *,
    premise: str = "",
    series_id: str = "",
    genre: str = "",
    baseline_text: str = "",
) -> dict[str, Any]:
    """Coerce a partial or loose model response into the package draft shape."""

    values = dict(data or {})
    clean_series_id = str(values.get("series_id") or series_id or "default-series")
    clean_premise = str(values.get("premise") or premise or "").strip()

    package: dict[str, Any] = {
        "schema_version": _int_or_default(
            values.get("schema_version"), SERIES_PACKAGE_SCHEMA_VERSION
        ),
        "series_id": clean_series_id,
        "premise": clean_premise,
        "metadata": _coerce_metadata(values.get("metadata"), baseline_text, genre),
        "system_announcer": _coerce_system_announcer(
            values.get("system_announcer"), baseline_text=baseline_text
        ),
        "characters": _coerce_characters(values.get("characters"), clean_premise),
        "familiar": _coerce_named_section(
            values.get("familiar"),
            defaults={
                "name": "Familiar",
                "system_role": "Registered companion with mechanically useful interruptions.",
                "stat_sheet": {},
                "vocabulary": [],
                "sample_lines": [],
                "audio_notes": [],
            },
        ),
        "home_base": _coerce_named_section(
            values.get("home_base"),
            defaults={
                "name": "Home Base",
                "advantages": [],
                "vulnerabilities": [],
                "upgrade_hooks": [],
                "audio_notes": [],
            },
        ),
        "floor_rules": _coerce_named_section(
            values.get("floor_rules"),
            defaults={
                "floor_one": [],
                "mechanics": [],
                "failure_states": [],
                "reward_logic": [],
            },
        ),
        "faction_map": _coerce_factions(values.get("faction_map")),
        "bestiary": _coerce_bestiary(
            values.get("bestiary")
            or values.get("world_entities")
            or values.get("entities")
            or values.get("monsters")
            or values.get("mobs")
        ),
        "encounters": _coerce_encounters(
            values.get("encounters")
            or values.get("encounter_registry")
            or values.get("bosses")
        ),
        "sample_announcements": _string_list(values.get("sample_announcements")),
        "audio_performance_notes": _string_list(values.get("audio_performance_notes")),
    }
    if not package["sample_announcements"]:
        package["sample_announcements"] = list(
            package["system_announcer"].get("sample_announcements") or []
        )
    if not package["audio_performance_notes"]:
        package["audio_performance_notes"] = list(
            package["system_announcer"].get("audio_notes") or []
        )
    package["validation_metadata"] = validate_series_package(package)
    return package


def validate_series_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Return non-fatal package validation metadata."""

    errors: list[str] = []
    warnings: list[str] = []
    characters = package.get("characters")
    if not isinstance(characters, list):
        errors.append("characters must be a list")
        character_count = 0
    else:
        character_count = len(characters)
        if character_count < MINIMUM_CHARACTER_PACKAGES:
            errors.append(
                f"series package requires at least {MINIMUM_CHARACTER_PACKAGES} character packages"
            )
        missing_names = [
            str(index)
            for index, character in enumerate(characters)
            if isinstance(character, Mapping) and not character.get("name")
        ]
        if missing_names:
            warnings.append("some character packages are missing names")

    for key in ("system_announcer", "familiar", "home_base", "floor_rules"):
        if not isinstance(package.get(key), Mapping):
            errors.append(f"{key} must be an object")
    for key in ("faction_map", "bestiary", "encounters"):
        if not isinstance(package.get(key), list):
            errors.append(f"{key} must be a list")

    if not package.get("premise"):
        warnings.append("premise is empty")
    if not package.get("sample_announcements"):
        warnings.append("sample_announcements is empty")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "character_count": character_count,
        "schema_version": package.get("schema_version"),
    }


def save_generated_series_package(
    package: Mapping[str, Any],
    *,
    storage_dir: str | None = None,
) -> Any | None:
    """Save through Worker A's package storage API when it is available.

    This lane intentionally does not own the storage module. The bridge is
    permissive so it can work with the final API names without making tests
    depend on that module.
    """

    try:
        package_store = importlib.import_module("podcastfy.litrpg.packages")
    except ModuleNotFoundError:
        return None

    if hasattr(package_store, "save_series_package"):
        save_func = package_store.save_series_package
    elif hasattr(package_store, "save_package"):
        save_func = package_store.save_package
    else:
        return None

    payload = _storage_package_payload(package)
    attempts = []
    if storage_dir is not None:
        attempts.extend(
            [
                lambda: save_func(storage_dir, payload),
                lambda: save_func(storage_dir=storage_dir, package=payload),
                lambda: save_func(payload, storage_dir=storage_dir),
            ]
        )
    attempts.extend(
        [
            lambda: save_func(package=payload),
            lambda: save_func("data/litrpg", payload),
            lambda: save_func(payload),
        ]
    )

    last_type_error: TypeError | None = None
    for attempt in attempts:
        try:
            return attempt()
        except TypeError as exc:
            last_type_error = exc
            continue
    if last_type_error is not None:
        raise last_type_error
    return None


def _storage_package_payload(package: Mapping[str, Any]) -> dict[str, Any]:
    """Return a Worker-A-storage-compatible view of the rich draft package."""

    announcer = package.get("system_announcer")
    announcer_data = dict(announcer) if isinstance(announcer, Mapping) else {}
    storage_announcer = {
        "name": str(announcer_data.get("name") or "System Announcer"),
        "voice": "; ".join(_string_list(announcer_data.get("voice_pillars"))),
        "tone": "; ".join(_string_list(announcer_data.get("tone_rules"))),
        "purpose": "Reusable System performance profile for the series.",
        "rules": _string_list(announcer_data.get("forbidden_moves")),
        "sample_lines": _string_list(
            announcer_data.get("sample_announcements")
            or announcer_data.get("sample_lines")
        ),
        "delivery_notes": _string_list(announcer_data.get("audio_notes")),
        "audio_cues": _string_list(announcer_data.get("audio_cues")),
        "metadata": {
            "voice_pillars": _string_list(announcer_data.get("voice_pillars")),
            "tone_rules": _string_list(announcer_data.get("tone_rules")),
        },
    }

    characters = []
    character_source = package.get("characters")
    if not isinstance(character_source, list):
        character_source = []
    for item in character_source:
        if not isinstance(item, Mapping):
            continue
        voice = item.get("voice")
        voice_data = dict(voice) if isinstance(voice, Mapping) else {}
        characters.append(
            {
                "name": str(item.get("name") or ""),
                "role": str(item.get("role") or ""),
                "character_class": str(item.get("class_or_mechanic") or ""),
                "voice": str(
                    voice_data.get("delivery")
                    or voice_data.get("archetype")
                    or item.get("voice")
                    or ""
                ),
                "personality": "; ".join(_string_list(item.get("personality"))),
                "arc": "; ".join(_string_list(item.get("arc"))),
                "rules": _string_list(item.get("rules")),
                "sample_lines": _string_list(voice_data.get("sample_lines")),
                "relationships": _string_list(item.get("relationships")),
                "notes": _string_list(item.get("audio_notes")),
                "metadata": {"voice": voice_data},
            }
        )

    familiar = package.get("familiar")
    familiar_data = dict(familiar) if isinstance(familiar, Mapping) else {}
    home_base = package.get("home_base")
    home_data = dict(home_base) if isinstance(home_base, Mapping) else {}
    floor_rules = package.get("floor_rules")
    floor_data = dict(floor_rules) if isinstance(floor_rules, Mapping) else {}

    return {
        "schema_version": package.get("schema_version", SERIES_PACKAGE_SCHEMA_VERSION),
        "series_id": str(package.get("series_id") or "default-series"),
        "premise": str(package.get("premise") or ""),
        "metadata": dict(package.get("metadata") or {}),
        "system_announcer": storage_announcer,
        "characters": characters,
        "familiar": {
            "name": str(familiar_data.get("name") or ""),
            "species": str(familiar_data.get("species") or ""),
            "system_role": str(familiar_data.get("system_role") or ""),
            "voice": "; ".join(_string_list(familiar_data.get("audio_notes"))),
            "vocabulary": _string_list(familiar_data.get("vocabulary")),
            "rules": _string_list(familiar_data.get("rules")),
            "sample_lines": _string_list(familiar_data.get("sample_lines")),
            "notes": _string_list(familiar_data.get("audio_notes")),
            "metadata": {
                "stat_sheet": familiar_data.get("stat_sheet")
                if isinstance(familiar_data.get("stat_sheet"), Mapping)
                else {}
            },
        },
        "home_base": {
            "name": str(home_data.get("name") or ""),
            "description": str(home_data.get("description") or ""),
            "advantages": _string_list(home_data.get("advantages")),
            "vulnerabilities": _string_list(home_data.get("vulnerabilities")),
            "rules": _string_list(home_data.get("rules")),
            "upgrades": _string_list(
                home_data.get("upgrade_hooks") or home_data.get("upgrades")
            ),
            "notes": _string_list(home_data.get("audio_notes")),
        },
        "floor_rules": {
            "floor": str(floor_data.get("floor") or "floor_one"),
            "premise": "; ".join(_string_list(floor_data.get("floor_one"))),
            "rules": _string_list(floor_data.get("mechanics") or floor_data.get("rules")),
            "hazards": _string_list(floor_data.get("hazards")),
            "rewards": _string_list(floor_data.get("reward_logic") or floor_data.get("rewards")),
            "constraints": _string_list(
                floor_data.get("failure_states") or floor_data.get("constraints")
            ),
            "notes": _string_list(floor_data.get("notes")),
        },
        "faction_map": package.get("faction_map") or [],
        "bestiary": package.get("bestiary") or [],
        "encounters": package.get("encounters") or [],
    }


def format_series_package_summary(package: Mapping[str, Any], *, max_characters: int = 8) -> str:
    """Format compact package context for chapter and package refinement prompts."""

    lines = [f"Series Package ({package.get('series_id') or 'unknown'})"]
    premise = str(package.get("premise") or "").strip()
    metadata = package.get("metadata")
    if not premise and isinstance(metadata, Mapping):
        premise = str(metadata.get("logline") or metadata.get("premise") or "").strip()
    if premise:
        lines.append(f"Premise: {premise}")

    announcer = package.get("system_announcer")
    if isinstance(announcer, Mapping):
        pillars = _compact_items(_string_list(announcer.get("voice_pillars")), 4)
        if pillars:
            lines.append("System voice: " + "; ".join(pillars))
        samples = _compact_items(_string_list(announcer.get("sample_announcements")), 2)
        if samples:
            lines.append("System samples: " + " | ".join(samples))

    home_base = package.get("home_base")
    if isinstance(home_base, Mapping) and home_base.get("name"):
        advantages = _compact_items(_string_list(home_base.get("advantages")), 3)
        detail = f"Home base: {home_base['name']}"
        if advantages:
            detail += " | advantages: " + "; ".join(advantages)
        lines.append(detail)

    characters = package.get("characters") if isinstance(package.get("characters"), list) else []
    for character in characters[:max_characters]:
        if not isinstance(character, Mapping):
            continue
        pieces = [
            str(character.get("role") or "ROLE"),
            str(character.get("name") or "Unnamed"),
        ]
        if character.get("function"):
            pieces.append(str(character["function"]))
        voice = character.get("voice")
        if isinstance(voice, Mapping) and voice.get("delivery"):
            pieces.append(f"voice: {voice['delivery']}")
        lines.append(" - " + " | ".join(piece for piece in pieces if piece))

    if len(characters) > max_characters:
        lines.append(f"... plus {len(characters) - max_characters} more package role(s).")
    bestiary = package.get("bestiary") if isinstance(package.get("bestiary"), list) else []
    for entity in bestiary[:5]:
        if not isinstance(entity, Mapping):
            continue
        pieces = [
            str(entity.get("entity_type") or "entity"),
            str(entity.get("name") or "Unnamed"),
        ]
        weaknesses = _compact_items(_string_list(entity.get("weaknesses")), 2)
        if weaknesses:
            pieces.append("weaknesses: " + "; ".join(weaknesses))
        behavior = _compact_items(_string_list(entity.get("behavior_rules")), 2)
        if behavior:
            pieces.append("behavior: " + "; ".join(behavior))
        lines.append("Bestiary - " + " | ".join(piece for piece in pieces if piece))
    encounters = package.get("encounters") if isinstance(package.get("encounters"), list) else []
    for encounter in encounters[:4]:
        if not isinstance(encounter, Mapping):
            continue
        pieces = [
            str(encounter.get("encounter_type") or "encounter"),
            str(encounter.get("name") or "Unnamed"),
        ]
        if encounter.get("status"):
            pieces.append(f"status: {encounter['status']}")
        if encounter.get("location"):
            pieces.append(f"location: {encounter['location']}")
        lines.append("Encounter - " + " | ".join(piece for piece in pieces if piece))
    return "\n".join(lines)


def _strip_json_fence(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _coerce_metadata(value: Any, baseline_text: str, genre: str = "") -> dict[str, Any]:
    metadata = dict(value) if isinstance(value, Mapping) else {}
    clean_genre = str(metadata.get("genre") or genre or "").strip()
    metadata.setdefault(
        "generator",
        "litrpg-series-package"
        if "litrpg" in clean_genre.casefold()
        else "audio-series-package",
    )
    if clean_genre:
        metadata["genre"] = clean_genre
    metadata["baseline_used"] = bool(baseline_text.strip()) or bool(
        metadata.get("baseline_used")
    )
    metadata.setdefault("notes", [])
    if not isinstance(metadata["notes"], list):
        metadata["notes"] = _string_list(metadata["notes"])
    return metadata


def _coerce_system_announcer(value: Any, *, baseline_text: str) -> dict[str, Any]:
    data = dict(value) if isinstance(value, Mapping) else {}
    sample_lines = _string_list(
        data.get("sample_announcements") or data.get("sample_lines")
    )
    voice_pillars = _string_list(data.get("voice_pillars"))
    if baseline_text.strip() and not voice_pillars:
        voice_pillars = [
            "Uses the supplied baseline package as a performance seed.",
            "Turns rules text into theatrical pressure without copying another narrator.",
        ]
    return {
        "name": str(data.get("name") or "System Announcer"),
        "voice_pillars": voice_pillars,
        "tone_rules": _string_list(data.get("tone_rules")),
        "sample_announcements": sample_lines
        or ["NEW QUEST: Survive the premise long enough to regret the reward."],
        "audio_notes": _string_list(data.get("audio_notes")),
        "forbidden_moves": _string_list(data.get("forbidden_moves")),
    }


def _coerce_characters(value: Any, premise: str) -> list[dict[str, Any]]:
    raw_characters = value if isinstance(value, list) else []
    characters = [
        _coerce_character(character, index=index)
        for index, character in enumerate(raw_characters)
        if isinstance(character, Mapping)
    ]
    seen_roles = {str(character.get("role") or "").upper() for character in characters}
    for role in ROLE_TAGS:
        if len(characters) >= MINIMUM_CHARACTER_PACKAGES and "SYSTEM" in seen_roles:
            break
        if role in seen_roles:
            continue
        characters.append(_default_character(role, premise))
        seen_roles.add(role)
    while len(characters) < MINIMUM_CHARACTER_PACKAGES:
        role = f"SUPPORT_{len(characters) + 1}"
        characters.append(_default_character(role, premise))
    return characters


def _coerce_character(value: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    role = str(value.get("role") or value.get("id") or f"SUPPORT_{index + 1}").upper()
    voice = value.get("voice")
    if not isinstance(voice, Mapping):
        voice = {
            "archetype": str(value.get("archetype") or role.title()),
            "delivery": str(value.get("delivery") or ""),
            "pace": str(value.get("pace") or "medium"),
            "sample_lines": _string_list(value.get("sample_lines")),
        }
    else:
        voice = {
            "archetype": str(voice.get("archetype") or value.get("archetype") or role.title()),
            "delivery": str(voice.get("delivery") or value.get("delivery") or ""),
            "pace": str(voice.get("pace") or "medium"),
            "sample_lines": _string_list(voice.get("sample_lines")),
        }
    return {
        "role": role,
        "name": str(value.get("name") or value.get("display_name") or role.title()),
        "function": str(value.get("function") or value.get("description") or ""),
        "class_or_mechanic": str(value.get("class_or_mechanic") or ""),
        "personality": _string_list(value.get("personality")),
        "voice": voice,
        "arc": _string_list(value.get("arc")),
        "audio_notes": _string_list(value.get("audio_notes")),
    }


def _default_character(role: str, premise: str) -> dict[str, Any]:
    role_name = role.replace("_", " ").title()
    function = {
        "NARRATOR": "Keeps action, place, and emotional stakes clear for audio.",
        "HERO": "Grounded protagonist who treats absurd mechanics as practical problems.",
        "SYSTEM": "Rules and reward voice for announcements, quests, loot, and punishments.",
        "SIDEKICK": "High-contrast companion who creates banter and pressure.",
        "BOSS": "Setpiece antagonist with a strong mechanical weakness.",
        "RIVAL": "Competing crawler or faction face with grudging respect.",
        "MENTOR": "Veteran survivor who knows dungeon etiquette and hidden costs.",
        "MERCHANT": "Vendor or sponsor proxy with useful but suspicious inventory.",
        "HEALER": "Support voice who tracks consequences and triage.",
        "TANK": "Front-line problem solver who turns danger into logistics.",
        "ROGUE": "Trap, theft, and leverage specialist.",
        "MAGE": "Rules-minded mechanics explainer under stress.",
        "BEAST": "Monster, summon, or creature role with a simple distinct sound.",
        "MINION": "Enemy crowd texture for fights and pressure.",
        "GUIDE": "Tutorial or venue voice separate from the hostile System.",
        "VILLAIN": "Long-arc antagonist with strategic interest in the protagonists.",
    }.get(role, "Recurring support role generated from the series premise.")
    return {
        "role": role,
        "name": role_name,
        "function": function,
        "class_or_mechanic": "",
        "personality": [],
        "voice": {
            "archetype": role_name,
            "delivery": "distinct, consistent, audio-first",
            "pace": "medium",
            "sample_lines": [
                f"I am the {role_name.lower()} voice this series needs when the dungeon gets loud."
            ],
        },
        "arc": [],
        "audio_notes": [f"Ground this role in the premise: {premise[:120]}".strip()],
    }


def _coerce_named_section(value: Any, *, defaults: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(value) if isinstance(value, Mapping) else {}
    result = dict(defaults)
    for key, default in defaults.items():
        if key not in data:
            continue
        if isinstance(default, list):
            result[key] = _string_list(data[key])
        elif isinstance(default, dict):
            result[key] = dict(data[key]) if isinstance(data[key], Mapping) else {}
        else:
            result[key] = str(data[key])
    for key, value in data.items():
        if key not in result:
            result[str(key)] = value
    return result


def _coerce_factions(value: Any) -> list[dict[str, str]]:
    if isinstance(value, Mapping):
        source = []
        for name, entry in value.items():
            if isinstance(entry, Mapping):
                item = dict(entry)
                item.setdefault("name", name)
                source.append(item)
            else:
                source.append({"name": name, "agenda": str(entry)})
    elif isinstance(value, list):
        source = [item for item in value if isinstance(item, Mapping)]
    else:
        source = []
    factions = []
    for item in source:
        factions.append(
            {
                "name": str(item.get("name") or "Unnamed faction"),
                "agenda": str(item.get("agenda") or ""),
                "attitude_to_protagonists": str(
                    item.get("attitude_to_protagonists") or ""
                ),
                "audio_identity": str(item.get("audio_identity") or ""),
            }
        )
    return factions


def _coerce_bestiary(value: Any) -> list[dict[str, Any]]:
    source = _coerce_package_list(value, default_text_key="category")
    entries: list[dict[str, Any]] = []
    for item in source:
        entries.append(
            {
                "name": str(item.get("name") or "Unnamed entity"),
                "entity_type": str(
                    item.get("entity_type")
                    or item.get("type")
                    or item.get("kind")
                    or ""
                ),
                "category": str(item.get("category") or ""),
                "first_seen": str(item.get("first_seen") or ""),
                "recurrence": str(item.get("recurrence") or ""),
                "visual_signature": _string_list(
                    item.get("visual_signature") or item.get("visuals")
                ),
                "behavior_rules": _string_list(
                    item.get("behavior_rules") or item.get("behaviors")
                ),
                "abilities": _string_list(item.get("abilities")),
                "weaknesses": _string_list(item.get("weaknesses") or item.get("weakness")),
                "resistances": _string_list(item.get("resistances")),
                "loot_table": _string_list(item.get("loot_table") or item.get("loot")),
                "voice": str(item.get("voice") or item.get("audio_identity") or ""),
                "rules": _string_list(item.get("rules")),
                "notes": _string_list(item.get("notes")),
            }
        )
    return entries


def _coerce_encounters(value: Any) -> list[dict[str, Any]]:
    source = _coerce_package_list(value, default_text_key="stakes")
    entries: list[dict[str, Any]] = []
    for item in source:
        entries.append(
            {
                "name": str(item.get("name") or "Unnamed encounter"),
                "encounter_type": str(
                    item.get("encounter_type")
                    or item.get("type")
                    or item.get("kind")
                    or ""
                ),
                "status": str(item.get("status") or ""),
                "location": str(item.get("location") or item.get("arena") or ""),
                "first_seen": str(item.get("first_seen") or ""),
                "participants": _string_list(item.get("participants")),
                "phase_rules": _string_list(item.get("phase_rules") or item.get("phases")),
                "weaknesses": _string_list(item.get("weaknesses") or item.get("weakness")),
                "stakes": str(item.get("stakes") or ""),
                "resolution": str(item.get("resolution") or ""),
                "rewards": _string_list(item.get("rewards")),
                "return_conditions": _string_list(
                    item.get("return_conditions") or item.get("can_return")
                ),
                "rules": _string_list(item.get("rules")),
                "notes": _string_list(item.get("notes")),
            }
        )
    return entries


def _coerce_package_list(value: Any, *, default_text_key: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        source = []
        for name, entry in value.items():
            if isinstance(entry, Mapping):
                item = dict(entry)
                item.setdefault("name", name)
                source.append(item)
            else:
                source.append({"name": name, default_text_key: str(entry)})
        return source
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _compact_items(items: list[str], limit: int) -> list[str]:
    compact = [item for item in items if item][:limit]
    if len(items) > limit:
        compact.append(f"+{len(items) - limit} more")
    return compact


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
