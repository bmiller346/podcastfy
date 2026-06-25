"""Cast planning helpers for LitRPG voice audition workflows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from podcastfy.litrpg.config import LitRPGConfig, load_litrpg_config
from podcastfy.litrpg.prompts import ROLE_TAGS


DEFAULT_PROVIDER = "config"
OPENAI_TTS_MODELS = {"gpt-4o-mini-tts", "tts-1", "tts-1-hd"}


@dataclass(slots=True)
class VoiceProfile:
    """Provider-specific voice selection and direction for one role."""

    provider: str = DEFAULT_PROVIDER
    voice: str = ""
    model: str | None = None
    instructions: str = ""
    style: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
        *,
        provider: str = DEFAULT_PROVIDER,
    ) -> "VoiceProfile":
        if not values:
            return cls(provider=provider)
        tags = values.get("tags") or []
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        return cls(
            provider=str(values.get("provider") or provider or DEFAULT_PROVIDER),
            voice=str(values.get("voice") or ""),
            model=_optional_str(values.get("model")),
            instructions=str(values.get("instructions") or ""),
            style=str(values.get("style") or ""),
            tags=[str(tag) for tag in tags],
        )

    def to_renderer_dict(self) -> dict[str, Any]:
        values: dict[str, Any] = {"voice": self.voice}
        if self.instructions:
            values["instructions"] = self.instructions
        if self.style:
            values["style"] = self.style
        if self.model:
            values["model"] = self.model
        if self.provider and self.provider != DEFAULT_PROVIDER:
            values["provider"] = self.provider
        if self.tags:
            values["tags"] = list(self.tags)
        return values


@dataclass(slots=True)
class CastMember:
    """One cast role with display metadata and audition voice direction."""

    role: str
    display_name: str
    description: str
    archetype: str
    voice_profile: VoiceProfile = field(default_factory=VoiceProfile)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        *,
        provider: str = DEFAULT_PROVIDER,
    ) -> "CastMember":
        role = _normalize_role(values.get("role") or values.get("id"))
        voice_values = values.get("voice_profile") or values.get("voice") or {}
        if not isinstance(voice_values, Mapping):
            voice_values = {"voice": voice_values}
        return cls(
            role=role,
            display_name=str(values.get("display_name") or _title_role(role)),
            description=str(values.get("description") or ""),
            archetype=str(values.get("archetype") or _title_role(role)),
            voice_profile=VoiceProfile.from_mapping(voice_values, provider=provider),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CastPlan:
    """Serializable voice casting plan for a LitRPG chapter or episode."""

    cast_members: list[CastMember]
    provider_defaults: dict[str, Any] = field(default_factory=dict)
    validation_metadata: dict[str, Any] = field(
        default_factory=lambda: {"errors": [], "warnings": []}
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_defaults": dict(self.provider_defaults),
            "cast_members": [member.to_dict() for member in self.cast_members],
            "validation_metadata": dict(self.validation_metadata),
        }

    def member_by_role(self) -> dict[str, CastMember]:
        return {member.role: member for member in self.cast_members}


def build_default_cast_plan(
    config: LitRPGConfig | None = None,
    *,
    provider_defaults: Mapping[str, Any] | None = None,
) -> CastPlan:
    """Build the default 15+ role cast plan from LitRPG role and voice defaults."""
    config = config or load_litrpg_config()
    defaults = {"provider": DEFAULT_PROVIDER}
    defaults.update(dict(provider_defaults or {}))
    provider = str(defaults.get("provider") or DEFAULT_PROVIDER)
    members = [
        _default_member_for_role(role, config=config, provider=provider)
        for role in ROLE_TAGS
    ]
    return CastPlan(cast_members=members, provider_defaults=defaults)


def load_cast_plan_json(
    path: str | Path,
    *,
    config: LitRPGConfig | None = None,
    merge_defaults: bool = True,
) -> CastPlan:
    """Load a cast plan JSON file and optionally merge it over defaults."""
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, Mapping):
        raise ValueError("Cast plan JSON must contain an object")
    return cast_plan_from_mapping(data, config=config, merge_defaults=merge_defaults)


def cast_plan_from_mapping(
    values: Mapping[str, Any],
    *,
    config: LitRPGConfig | None = None,
    merge_defaults: bool = True,
) -> CastPlan:
    """Create a cast plan from mapping data, merging role entries by role id."""
    incoming_provider_defaults = dict(values.get("provider_defaults") or {})
    base = (
        build_default_cast_plan(config, provider_defaults=incoming_provider_defaults)
        if merge_defaults
        else None
    )
    provider_defaults = dict(base.provider_defaults if base else {})
    provider_defaults.update(incoming_provider_defaults)
    provider = str(provider_defaults.get("provider") or DEFAULT_PROVIDER)

    raw_members = values.get("cast_members") or values.get("members") or []
    if not isinstance(raw_members, Sequence) or isinstance(raw_members, (str, bytes)):
        raise ValueError("cast_members must be a list")

    override_members = [
        CastMember.from_mapping(member, provider=provider)
        for member in raw_members
        if isinstance(member, Mapping)
    ]

    if base is None:
        plan = CastPlan(
            cast_members=override_members,
            provider_defaults=provider_defaults,
            validation_metadata=dict(values.get("validation_metadata") or {"errors": [], "warnings": []}),
        )
        return plan

    plan = merge_cast_plan(
        base,
        CastPlan(cast_members=override_members, provider_defaults=provider_defaults),
    )
    if values.get("validation_metadata"):
        plan.validation_metadata = dict(values["validation_metadata"])
    return plan


def merge_cast_plan(defaults: CastPlan, override: CastPlan) -> CastPlan:
    """Merge an override plan into defaults, replacing members with matching roles."""
    merged_defaults = dict(defaults.provider_defaults)
    merged_defaults.update(override.provider_defaults)

    merged_by_role = {member.role: member for member in defaults.cast_members}
    order = [member.role for member in defaults.cast_members]
    for member in override.cast_members:
        if member.role not in merged_by_role:
            order.append(member.role)
        current = merged_by_role.get(member.role)
        merged_by_role[member.role] = _merge_member(current, member)

    return CastPlan(
        cast_members=[merged_by_role[role] for role in order],
        provider_defaults=merged_defaults,
    )


def validate_cast_plan(
    plan: CastPlan,
    *,
    mode: str = "chapter",
    required_roles: Sequence[str] = ROLE_TAGS,
) -> dict[str, Any]:
    """Validate a cast plan and store non-fatal diagnostics on the plan."""
    errors: list[str] = []
    warnings: list[str] = []
    roles_seen: set[str] = set()
    duplicates: set[str] = set()

    for member in plan.cast_members:
        if member.role in roles_seen:
            duplicates.add(member.role)
        roles_seen.add(member.role)
        warnings.extend(_provider_model_warnings(member, plan.provider_defaults))
    warnings = list(dict.fromkeys(warnings))

    if mode == "chapter" and len(plan.cast_members) < 15:
        errors.append("Chapter mode requires at least 15 cast members.")
    if duplicates:
        errors.append(
            "Duplicate role IDs are not allowed: " + ", ".join(sorted(duplicates))
        )

    members = plan.member_by_role()
    for role in [_normalize_role(role) for role in required_roles]:
        member = members.get(role)
        if member is None:
            errors.append(f"Required role {role} is missing from the cast plan.")
        elif not member.voice_profile.voice:
            errors.append(f"Required role {role} must define voice_profile.voice.")

    metadata = {
        "mode": mode,
        "required_roles": [_normalize_role(role) for role in required_roles],
        "cast_member_count": len(plan.cast_members),
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
    }
    plan.validation_metadata = metadata
    return metadata


def generate_audition_script(
    plan: CastPlan,
    *,
    roles: Sequence[str] | None = None,
) -> dict[str, str]:
    """Generate short role-specific audition lines for voice casting."""
    members = plan.member_by_role()
    selected_roles = [_normalize_role(role) for role in (roles or members.keys())]
    scripts: dict[str, str] = {}
    for role in selected_roles:
        member = members.get(role)
        if member is None:
            continue
        line = _audition_line(member)
        scripts[role] = f"<{role}>{line}</{role}>"
    return scripts


def export_voices_for_litrpg_config(plan: CastPlan) -> dict[str, dict[str, Any]]:
    """Export to the ``litrpg_config.voices`` shape consumed by the renderer."""
    voices: dict[str, dict[str, Any]] = {}
    for member in plan.cast_members:
        profile = member.voice_profile
        if profile.voice:
            voices[member.role] = profile.to_renderer_dict()
    return voices


cast_plan_to_litrpg_voices = export_voices_for_litrpg_config


def _default_member_for_role(
    role: str,
    *,
    config: LitRPGConfig,
    provider: str,
) -> CastMember:
    description = config.cast_roles.get(role, f"Default {role.lower()} role.")
    voice_config = config.voices.get(role, {})
    if not isinstance(voice_config, Mapping):
        voice_config = {"voice": voice_config}
    profile = VoiceProfile.from_mapping(voice_config, provider=provider)
    tags = set(profile.tags)
    tags.add(role.lower())
    if role == "SYSTEM":
        tags.update({"announcement", "mechanics"})
    profile.tags = sorted(tags)
    if not profile.instructions:
        profile.instructions = description
    return CastMember(
        role=role,
        display_name=_title_role(role),
        description=description,
        archetype=_archetype_for_role(role),
        voice_profile=profile,
    )


def _merge_member(current: CastMember | None, override: CastMember) -> CastMember:
    if current is None:
        return override
    profile = VoiceProfile(
        provider=override.voice_profile.provider or current.voice_profile.provider,
        voice=override.voice_profile.voice or current.voice_profile.voice,
        model=override.voice_profile.model or current.voice_profile.model,
        instructions=override.voice_profile.instructions or current.voice_profile.instructions,
        style=override.voice_profile.style or current.voice_profile.style,
        tags=override.voice_profile.tags or list(current.voice_profile.tags),
    )
    return CastMember(
        role=override.role,
        display_name=override.display_name or current.display_name,
        description=override.description or current.description,
        archetype=override.archetype or current.archetype,
        voice_profile=profile,
    )


def _provider_model_warnings(
    member: CastMember,
    provider_defaults: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    plan_provider = str(provider_defaults.get("provider") or DEFAULT_PROVIDER)
    profile = member.voice_profile
    if (
        plan_provider != DEFAULT_PROVIDER
        and profile.provider != DEFAULT_PROVIDER
        and profile.provider != plan_provider
    ):
        warnings.append(
            f"{member.role} provider {profile.provider!r} differs from plan provider {plan_provider!r}."
        )

    default_model = _optional_str(provider_defaults.get("model"))
    if default_model:
        warnings.extend(_model_warnings(member.role, plan_provider, default_model))

    model = profile.model
    if not model:
        return warnings
    provider = profile.provider if profile.provider != DEFAULT_PROVIDER else plan_provider
    warnings.extend(_model_warnings(member.role, provider, model))
    return warnings


def _model_warnings(role: str, provider: str, model: str) -> list[str]:
    warnings: list[str] = []
    lower_model = model.lower()
    if provider == "openai" and model not in OPENAI_TTS_MODELS:
        warnings.append(f"{role} model {model!r} is not a known OpenAI TTS model.")
    if provider in {"gemini", "google"} and lower_model.startswith(("gpt-", "tts-")):
        warnings.append(f"{role} model {model!r} looks like an OpenAI model for provider {provider!r}.")
    if provider == "openai" and lower_model.startswith(("gemini", "chirp")):
        warnings.append(f"{role} model {model!r} looks like a Google model for provider 'openai'.")
    return warnings


def _audition_line(member: CastMember) -> str:
    role = member.role
    if role == "SYSTEM":
        return (
            "SYSTEM ANNOUNCEMENT: New quest unlocked. Survive the impossible room, "
            "claim 120 XP, and try not to argue with the user interface."
        )
    if role == "NARRATOR":
        return (
            "The dungeon inhaled, the party leveled up at the worst possible time, "
            "and every torch flame pointed toward the boss door."
        )
    if role in {"BOSS", "VILLAIN"}:
        return (
            "Your stats are charmingly inadequate. Step forward anyway, little hero, "
            "and let the arena teach you arithmetic."
        )
    if role in {"GUIDE", "MENTOR"}:
        return (
            "Listen closely: cooldowns lie, loot glitters, and the safest door is "
            "usually the one growling your name."
        )
    if role in {"BEAST", "MINION"}:
        return (
            "The pack smells fear, fresh loot, and someone who forgot to check their "
            "armor durability."
        )
    return (
        f"I am {member.display_name}, the {member.archetype.lower()}. "
        "Give me the quest marker, a bad idea, and just enough XP to make this heroic."
    )


def _archetype_for_role(role: str) -> str:
    archetypes = {
        "NARRATOR": "cinematic narrator",
        "HERO": "reluctant adventurer",
        "SYSTEM": "hostile game interface",
        "SIDEKICK": "loyal comic counterpoint",
        "BOSS": "setpiece antagonist",
        "RIVAL": "competitive survivor",
        "MENTOR": "guarded veteran",
        "MERCHANT": "opportunistic vendor",
        "HEALER": "dry battlefield medic",
        "TANK": "front-line defender",
        "ROGUE": "sneaky opportunist",
        "MAGE": "rules-minded caster",
        "BEAST": "monster voice",
        "MINION": "enemy crowd texture",
        "GUIDE": "tutorial guide",
        "VILLAIN": "long-arc antagonist",
    }
    return archetypes.get(role, _title_role(role).lower())


def _normalize_role(value: Any) -> str:
    role = str(value or "").strip().upper().replace(" ", "_")
    if not role:
        raise ValueError("Cast member role is required")
    return role


def _title_role(role: str) -> str:
    return role.replace("_", " ").title()


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
