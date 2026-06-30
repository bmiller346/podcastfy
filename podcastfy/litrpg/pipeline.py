"""High-level local LitRPG episode generation pipeline."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from podcastfy.litrpg.config import LitRPGConfig, load_litrpg_config
from podcastfy.litrpg.effect_log import append_effect_log_entry
from podcastfy.litrpg.effect_log import build_effect_log_entry
from podcastfy.litrpg.effect_log import effect_log_path
from podcastfy.litrpg.engine import LitRPGEngine
from podcastfy.litrpg.episode_store import EpisodeStore
from podcastfy.litrpg.render_feedback import directive_invalid_feedback
from podcastfy.litrpg.render_feedback import directive_validation_to_dict
from podcastfy.litrpg.render_feedback import build_retry_directive
from podcastfy.litrpg.render_feedback import build_directive_revision_prompt
from podcastfy.litrpg.render_feedback import render_feedback_to_dict
from podcastfy.litrpg.render_feedback import render_feedback_effect_metadata
from podcastfy.litrpg.render_feedback import parse_directive_revision
from podcastfy.litrpg.render_feedback import score_rendered_audio
from podcastfy.litrpg.render_feedback import validate_directive
from podcastfy.litrpg.settings import get_provider_api_key, load_litrpg_settings
from podcastfy.litrpg.state_delta import apply_delta_to_state, extract_state_delta
from podcastfy.litrpg.state_store import load_series_state, next_episode_number
from podcastfy.litrpg.state_store import save_series_state


def generate_litrpg_audio_episode(
    *,
    premise: str,
    llm: Any,
    storage_dir: str | Path = "data/litrpg",
    series_id: str = "default-series",
    episode_number: int | None = None,
    render_audio: bool = True,
    tts: Any | None = None,
    tts_model: str | None = None,
    tts_api_key: str | None = None,
    tts_options: dict[str, Any] | None = None,
    conversation_config: dict[str, Any] | None = None,
    litrpg_config: LitRPGConfig | None = None,
    render_loop: dict[str, Any] | None = None,
    performance_directives: list[dict[str, Any]] | None = None,
    replay_existing: bool = True,
    settings_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate or replay one local LitRPG audio episode.

    The LLM and TTS objects are injectable so this can run in tests without
    external API calls.
    """
    config = litrpg_config or load_litrpg_config()
    settings = load_litrpg_settings(settings_path)
    provider_options = dict(tts_options or {})
    provider = str(
        provider_options.get("provider")
        or tts_model
        or settings.get("default_tts_provider")
        or "edge"
    )
    provider_model = str(
        provider_options.get("model")
        or settings.get("default_tts_model")
        or provider
    )
    audio_format = str(
        provider_options.get("format")
        or settings.get("default_tts_format")
        or "mp3"
    )
    storage_path = Path(storage_dir)
    series_dir = storage_path / "series" / series_id
    state = load_series_state(series_dir)
    state_payload = asdict(state)
    episode_store = EpisodeStore(storage_path)
    resolved_episode_number = episode_number or _resolve_episode_number(
        episode_store=episode_store,
        premise=premise,
        series_id=series_id,
        state_payload=state_payload,
        config=config,
        replay_existing=replay_existing,
        fallback_episode_number=next_episode_number(state),
    )
    replayable_bundle = _find_replayable_bundle(
        episode_store=episode_store,
        premise=premise,
        series_id=series_id,
        state_payload=state_payload,
        config=config,
        replay_existing=replay_existing,
        require_audio=render_audio,
    )
    loop_config = _render_loop_config(render_loop)
    renderer = None
    if render_audio and replayable_bundle is None:
        from podcastfy.litrpg.renderer import RoleScriptRenderer
        from podcastfy.text_to_speech import TextToSpeech

        renderer_tts = tts or TextToSpeech(
            model=provider,
            api_key=tts_api_key or get_provider_api_key(provider, settings),
            conversation_config=_conversation_config_with_tts_options(
                conversation_config,
                provider=provider,
                model=provider_model,
                audio_format=audio_format,
                provider_options=provider_options,
            ),
        )
        renderer = RoleScriptRenderer(tts=renderer_tts)
        if loop_config["enabled"]:
            renderer = FeedbackRenderer(
                inner=renderer,
                render_loop=loop_config,
                provider=provider,
                model=provider_model,
                directives=performance_directives or [],
                llm=llm,
            )

    engine = LitRPGEngine(
        llm=llm,
        state_store=lambda episode_number: state_payload,
        episode_store=episode_store,
        tts_renderer=renderer,
        config=config,
    )
    result = engine.generate_episode(
        premise=premise,
        series_id=series_id,
        episode_number=resolved_episode_number,
        replay_existing=replay_existing,
        require_audio_for_replay=render_audio,
    )
    if loop_config["enabled"] and isinstance(result.get("audio_metadata"), dict):
        audio_metadata = dict(result.get("audio_metadata") or {})
        if "render_feedback" in audio_metadata:
            result["render_feedback"] = list(audio_metadata.get("render_feedback") or [])
        result["render_loop"] = dict(audio_metadata.get("render_loop") or loop_config)

    if not result.get("replayed"):
        state = apply_delta_to_state(
            state,
            extract_state_delta(result, mechanics_context=_mechanics_context_from_state(state)),
        )
        state.episode_number = max(state.episode_number, resolved_episode_number)
        save_series_state(series_dir, state)
        if render_audio and result.get("audio_metadata"):
            _append_audio_render_effect(
                storage_path=storage_path,
                series_id=series_id,
                episode_number=resolved_episode_number,
                provider=provider,
                model=provider_model,
                input_payload={
                    "premise": premise,
                    "episode_number": resolved_episode_number,
                    "provider": provider,
                    "model": provider_model,
                },
                output_payload=result.get("audio_metadata"),
            )

    return result


class FeedbackRenderer:
    """Renderer wrapper that validates directives and scores the produced audio."""

    def __init__(
        self,
        *,
        inner: Any,
        render_loop: Mapping[str, Any],
        provider: str,
        model: str,
        directives: list[dict[str, Any]],
        llm: Any | None = None,
    ) -> None:
        self.inner = inner
        self.render_loop = dict(render_loop)
        self.provider = provider
        self.model = model
        self.directives = directives
        self.llm = llm

    def render_episode(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        segment_id = _segment_id_from_bundle(bundle)
        current_directives = [dict(item) for item in self.directives]
        validations = [
            validate_directive(directive, provider=self.provider)
            for directive in current_directives
        ]
        validation = next((item for item in validations if not item.valid), None)
        if validation is not None and not validation.valid:
            feedback = directive_invalid_feedback(
                segment_id=segment_id,
                attempt=1,
                provider=self.provider,
                model=self.model,
                validation=validation,
            )
            metadata = {
                "status": "directive_invalid",
                "audio_path": None,
                "audio_render_skipped": True,
                "reason": validation.reason,
                "render_feedback": [render_feedback_to_dict(feedback)],
                "render_loop": dict(self.render_loop),
                "directive_validation": directive_validation_to_dict(validation),
                "directive_validations": [
                    directive_validation_to_dict(item) for item in validations
                ],
            }
            _persist_audio_metadata(bundle, metadata)
            return metadata

        metadata = self._render_with_feedback_loop(bundle, segment_id, current_directives, validations)
        _persist_audio_metadata(bundle, metadata)
        return metadata

    def _render_with_feedback_loop(
        self,
        bundle: Mapping[str, Any],
        segment_id: str,
        directives: list[dict[str, Any]],
        initial_validations: list[Any],
    ) -> dict[str, Any]:
        threshold = float(self.render_loop.get("retry_below_score") or 0.72)
        strategy = str(self.render_loop.get("retry_strategy") or "none")
        max_attempts = int(self.render_loop.get("max_attempts") or 1)
        retry_enabled = strategy != "none" and max_attempts > 1
        attempts_to_run = max_attempts if retry_enabled else 1
        original_output_filename = str(getattr(self.inner, "output_filename", "final.mp3"))
        attempt_records: list[dict[str, Any]] = []
        attempt_metadata: list[dict[str, Any]] = []
        latest_metadata: dict[str, Any] = {}
        current_directives = [dict(item) for item in directives]

        try:
            for attempt in range(1, attempts_to_run + 1):
                if retry_enabled:
                    self._set_attempt_output_filename(original_output_filename, attempt)
                attempt_bundle = _bundle_with_directives(bundle, current_directives)
                latest_metadata = dict(self.inner.render_episode(attempt_bundle))
                if initial_validations or current_directives:
                    latest_metadata["directive_validations"] = [
                        directive_validation_to_dict(item)
                        for item in (
                            initial_validations
                            if attempt == 1
                            else [
                                validate_directive(directive, provider=self.provider)
                                for directive in current_directives
                            ]
                        )
                    ]
                feedback_payload = self._score_attempt(
                    latest_metadata,
                    bundle,
                    segment_id=segment_id,
                    attempt=attempt,
                    directive=current_directives[0] if current_directives else None,
                    threshold=threshold,
                )
                attempt_records.append(feedback_payload)
                attempt_metadata.append(dict(latest_metadata))
                if feedback_payload["score"] >= threshold:
                    feedback_payload.setdefault("notes", []).append("accepted before retry limit")
                    break
                if not retry_enabled or attempt >= max_attempts:
                    break
                next_directives, revision = self._next_retry_directives(
                    current_directives,
                    feedback_payload,
                    strategy=strategy,
                    attempt=attempt + 1,
                    bundle=bundle,
                    history=attempt_records,
                )
                if revision is not None:
                    feedback_payload["revision"] = revision
                    if revision.get("parse_error") or (
                        isinstance(revision.get("validation"), Mapping)
                        and not revision["validation"].get("valid", True)
                    ):
                        feedback_payload.setdefault("notes", []).append(
                            "retry stopped: LLM directive revision failed"
                        )
                        break
                validations = [
                    validate_directive(directive, provider=self.provider)
                    for directive in next_directives
                ]
                invalid = next((item for item in validations if not item.valid), None)
                if invalid is not None:
                    feedback_payload.setdefault("notes", []).append(
                        f"retry stopped: adjusted directive invalid: {invalid.reason}"
                    )
                    break
                current_directives = next_directives
        finally:
            if hasattr(self.inner, "output_filename"):
                self.inner.output_filename = original_output_filename

        if not attempt_records:
            return latest_metadata
        selected_index = _selected_attempt_index(attempt_records)
        for index, record in enumerate(attempt_records):
            record["selected"] = index == selected_index
            record.setdefault("notes", [])
            if record["selected"]:
                record["notes"].append("selected best measured attempt")
        selected_metadata = dict(attempt_metadata[selected_index])
        selected_metadata["render_feedback"] = attempt_records
        selected_metadata["render_loop"] = dict(self.render_loop)
        selected_metadata["render_attempts"] = _attempt_summaries(attempt_records, attempt_metadata)
        if retry_enabled:
            _copy_selected_attempt_to_final(
                selected_metadata,
                original_output_filename=original_output_filename,
            )
        _append_render_attempt_effects(
            bundle,
            provider=self.provider,
            model=self.model,
            attempts=selected_metadata["render_attempts"],
            render_loop=self.render_loop,
        )
        return selected_metadata

    def _score_attempt(
        self,
        metadata: Mapping[str, Any],
        bundle: Mapping[str, Any],
        *,
        segment_id: str,
        attempt: int,
        directive: Mapping[str, Any] | None,
        threshold: float,
    ) -> dict[str, Any]:
        audio_path = metadata.get("audio_path") or metadata.get("mixed_audio_path")
        if audio_path:
            feedback = score_rendered_audio(
                audio_path,
                segment_id=segment_id,
                attempt=attempt,
                provider=self.provider,
                model=self.model,
                expected_duration_seconds=_expected_duration_from_bundle(bundle),
                segment_text=str(bundle.get("script") or ""),
                directive=directive,
            )
            if feedback.score < threshold:
                feedback.human_review_required = True
                if feedback.verdict == "accepted":
                    feedback.verdict = "needs_review"
            payload = render_feedback_to_dict(feedback)
            payload["audio_path"] = str(audio_path)
            payload["directive"] = dict(directive or {})
            return payload
        feedback = directive_invalid_feedback(
            segment_id=segment_id,
            attempt=attempt,
            provider=self.provider,
            model=self.model,
            validation=validate_directive({}),
        )
        feedback.verdict = "missing_audio"
        feedback.notes = ["renderer did not return an audio_path"]
        return render_feedback_to_dict(feedback)

    def _set_attempt_output_filename(self, original_output_filename: str, attempt: int) -> None:
        if not hasattr(self.inner, "output_filename"):
            return
        path = Path(original_output_filename)
        self.inner.output_filename = f"{path.stem}_attempt_{attempt:03d}{path.suffix}"

    def _next_retry_directives(
        self,
        directives: list[dict[str, Any]],
        feedback_payload: Mapping[str, Any],
        *,
        strategy: str,
        attempt: int,
        bundle: Mapping[str, Any],
        history: list[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        if strategy != "llm_revision":
            return (
                _next_retry_directives(
                    directives,
                    feedback_payload,
                    strategy=strategy,
                    attempt=attempt,
                ),
                None,
            )
        if not bool(self.render_loop.get("llm_revision_enabled")):
            return (
                _next_retry_directives(
                    directives,
                    feedback_payload,
                    strategy="deterministic_adjustment",
                    attempt=attempt,
                ),
                {
                    "strategy": "llm_revision",
                    "reason": "llm_revision_enabled is false; used deterministic_adjustment fallback",
                    "risk_notes": ["LLM revision disabled by config"],
                    "parse_error": None,
                    "validation": directive_validation_to_dict(validate_directive({})),
                },
            )
        directive = dict(directives[0]) if directives else {}
        feedback = _feedback_from_payload(feedback_payload)
        prompt = build_directive_revision_prompt(
            str(bundle.get("script") or ""),
            directive,
            feedback,
            history=history[-3:],
            constraints={
                "provider": self.provider,
                "known_validator": "validate_directive",
            },
        )
        revision = {
            "strategy": "llm_revision",
            "reason": "",
            "risk_notes": [],
            "parse_error": None,
            "validation": {},
        }
        try:
            raw = _generate_directive_revision(self.llm, prompt)
            parsed = parse_directive_revision(raw)
        except Exception as exc:
            revision["parse_error"] = str(exc)
            revision["validation"] = directive_validation_to_dict(validate_directive({}))
            return [directive], revision
        revised = dict(parsed["directive"])
        validation = validate_directive(revised, provider=self.provider)
        revision.update(
            {
                "reason": parsed.get("reason", ""),
                "risk_notes": list(parsed.get("risk_notes") or []),
                "validation": directive_validation_to_dict(validation),
            }
        )
        if not validation.valid:
            return [directive], revision
        if len(directives) <= 1:
            return [revised], revision
        return [revised, *[dict(item) for item in directives[1:]]], revision


def _render_loop_config(value: Mapping[str, Any] | None) -> dict[str, Any]:
    config = dict(value or {})
    enabled = bool(config.get("enabled"))
    strategy = str(config.get("retry_strategy") or "none")
    if strategy not in {"none", "same_directive", "deterministic_adjustment", "llm_revision"}:
        strategy = "none"
    effective_strategy = (
        "deterministic_adjustment"
        if strategy == "llm_revision" and not bool(config.get("llm_revision_enabled"))
        else strategy
    )
    return {
        "enabled": enabled,
        "max_attempts": int(config.get("max_attempts") or 1),
        "retry_below_score": float(config.get("retry_below_score") or 0.72),
        "retry_strategy": strategy,
        "llm_revision_enabled": bool(config.get("llm_revision_enabled")),
        "auto_retry_enabled": bool(enabled and effective_strategy != "none" and int(config.get("max_attempts") or 1) > 1),
    }


def _bundle_with_directives(
    bundle: Mapping[str, Any], directives: list[dict[str, Any]]
) -> dict[str, Any]:
    payload = dict(bundle)
    if directives:
        payload["director_cues"] = [dict(item) for item in directives]
    return payload


def _next_retry_directives(
    directives: list[dict[str, Any]],
    feedback_payload: Mapping[str, Any],
    *,
    strategy: str,
    attempt: int,
) -> list[dict[str, Any]]:
    if strategy == "same_directive":
        return [dict(item) for item in directives]
    feedback = _feedback_from_payload(feedback_payload)
    if not directives:
        return [build_retry_directive({}, feedback, attempt)]
    return [
        build_retry_directive(directive, feedback, attempt)
        for directive in directives
    ]


def _feedback_from_payload(payload: Mapping[str, Any]) -> Any:
    from podcastfy.litrpg.render_feedback import RenderFeedback

    return RenderFeedback(
        segment_id=str(payload.get("segment_id") or ""),
        attempt=int(payload.get("attempt") or 1),
        provider=str(payload.get("provider") or ""),
        model=str(payload.get("model") or ""),
        peak_db=payload.get("peak_db"),
        rms_db=payload.get("rms_db"),
        silence_ratio=payload.get("silence_ratio"),
        duration_seconds=payload.get("duration_seconds"),
        clipping_detected=bool(payload.get("clipping_detected")),
        tts_valley_risk=bool(payload.get("tts_valley_risk")),
        score=float(payload.get("score") or 0.0),
        verdict=str(payload.get("verdict") or ""),
        human_review_required=bool(payload.get("human_review_required")),
        notes=list(payload.get("notes") or []),
    )


def _generate_directive_revision(llm: Any, prompt: str) -> str:
    if llm is None:
        raise ValueError("llm_revision strategy requires an llm")
    if hasattr(llm, "generate"):
        return str(llm.generate(prompt=prompt, stage="render_directive_revision"))
    if hasattr(llm, "generate_text"):
        return str(llm.generate_text(prompt=prompt, stage="render_directive_revision"))
    if callable(llm):
        try:
            return str(llm(prompt=prompt, stage="render_directive_revision"))
        except TypeError:
            return str(llm(prompt))
    raise TypeError("llm must be callable or expose generate/generate_text")


def _selected_attempt_index(records: list[Mapping[str, Any]]) -> int:
    best_index = 0
    best_score = -1.0
    for index, record in enumerate(records):
        try:
            score = float(record.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def _attempt_summaries(
    records: list[Mapping[str, Any]], metadata_by_attempt: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    summaries = []
    for index, record in enumerate(records):
        metadata = metadata_by_attempt[index] if index < len(metadata_by_attempt) else {}
        summaries.append(
            {
                "attempt": int(record.get("attempt") or index + 1),
                "score": record.get("score"),
                "verdict": record.get("verdict"),
                "selected": bool(record.get("selected")),
                "audio_path": metadata.get("audio_path"),
                "mixed_audio_path": metadata.get("mixed_audio_path"),
                "human_review_required": bool(record.get("human_review_required")),
                "segment_id": record.get("segment_id"),
            }
        )
    return summaries


def _copy_selected_attempt_to_final(
    metadata: dict[str, Any], *, original_output_filename: str
) -> None:
    selected_audio_path = metadata.get("audio_path")
    if not selected_audio_path:
        return
    source = Path(str(selected_audio_path))
    if not source.exists():
        return
    final = source.with_name(original_output_filename)
    if source.resolve() != final.resolve():
        shutil.copyfile(source, final)
    metadata["selected_attempt_audio_path"] = str(source)
    metadata["audio_path"] = str(final)


def _append_render_attempt_effects(
    bundle: Mapping[str, Any],
    *,
    provider: str,
    model: str,
    attempts: list[Mapping[str, Any]],
    render_loop: Mapping[str, Any],
) -> None:
    storage_metadata = bundle.get("storage_metadata")
    if not isinstance(storage_metadata, Mapping) or not storage_metadata.get("bundle_path"):
        return
    bundle_path = Path(str(storage_metadata["bundle_path"]))
    try:
        storage_path = bundle_path.parents[2]
    except IndexError:
        return
    series_id = str(bundle.get("series_id") or "default-series")
    episode_number = int(bundle.get("episode_number") or 1)
    for attempt in attempts:
        output_payload = {
            "render_feedback": [dict(attempt)],
            "render_loop": dict(render_loop),
        }
        metadata = render_feedback_effect_metadata(output_payload)
        metadata.update(
            {
                "attempt": int(attempt.get("attempt") or 1),
                "selected_attempt": (
                    int(attempt.get("attempt") or 1)
                    if attempt.get("selected")
                    else None
                ),
            }
        )
        entry = build_effect_log_entry(
            series_id=series_id,
            book_number=1,
            chapter_number=episode_number,
            stage="audio_render",
            input_payload={
                "episode_number": episode_number,
                "attempt": int(attempt.get("attempt") or 1),
            },
            output_payload=output_payload,
            provider=provider,
            model=model,
            status="committed",
            metadata=metadata,
        )
        append_effect_log_entry(effect_log_path(storage_path, series_id), entry)


def _segment_id_from_bundle(bundle: Mapping[str, Any]) -> str:
    series_id = str(bundle.get("series_id") or "series")
    episode_number = int(bundle.get("episode_number") or 1)
    return f"{series_id}_episode_{episode_number:03d}"


def _expected_duration_from_bundle(bundle: Mapping[str, Any]) -> float | None:
    config = bundle.get("config")
    if not isinstance(config, Mapping):
        return None
    try:
        minutes = float(config.get("minutes") or 0)
    except (TypeError, ValueError):
        return None
    return minutes * 60 if minutes > 0 else None


def _persist_audio_metadata(bundle: Mapping[str, Any], metadata: dict[str, Any]) -> None:
    path_value = metadata.get("audio_metadata_path")
    if path_value:
        path = Path(str(path_value))
    else:
        storage_metadata = bundle.get("storage_metadata")
        if not isinstance(storage_metadata, Mapping) or not storage_metadata.get("bundle_path"):
            return
        path = Path(str(storage_metadata["bundle_path"])) / "audio_metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(metadata)
    payload["audio_metadata_path"] = str(path)
    metadata["audio_metadata_path"] = str(path)
    with path.open("w", encoding="utf-8") as metadata_file:
        json.dump(payload, metadata_file, ensure_ascii=True, indent=2, sort_keys=True)
        metadata_file.write("\n")


def _mechanics_context_from_state(state: Any) -> dict[str, Any]:
    character = state.character
    return {
        "inventory": list(character.inventory),
        "skills": list(character.skills),
        "class": character.character_class,
        "level": character.level,
        "xp": dict(character.stats).get("xp"),
        "stats": dict(character.stats),
        "cooldowns": dict(state.mechanics.get("cooldowns") or {}),
    }


def _resolve_episode_number(
    *,
    episode_store: EpisodeStore,
    premise: str,
    series_id: str,
    state_payload: dict[str, Any],
    config: LitRPGConfig,
    replay_existing: bool,
    fallback_episode_number: int,
) -> int:
    if not replay_existing:
        return fallback_episode_number
    existing = episode_store.find_existing_bundle(
        {
            "series_id": series_id,
            "premise": premise,
            "state": state_payload,
            "config": _config_payload(config),
        }
    )
    if existing and existing.get("episode_number"):
        return int(existing["episode_number"])
    return fallback_episode_number


def _find_replayable_bundle(
    *,
    episode_store: EpisodeStore,
    premise: str,
    series_id: str,
    state_payload: dict[str, Any],
    config: LitRPGConfig,
    replay_existing: bool,
    require_audio: bool,
) -> dict[str, Any] | None:
    if not replay_existing:
        return None
    return episode_store.find_existing_bundle(
        {
            "series_id": series_id,
            "premise": premise,
            "state": state_payload,
            "config": _config_payload(config),
            "require_audio": require_audio,
        }
    )


def _config_payload(config: LitRPGConfig) -> dict[str, Any]:
    return {
        "minutes": config.minutes,
        "tone": config.tone,
        "episode_structure": config.episode_structure,
        "cast_roles": config.cast_roles,
        "voices": config.voices,
        "effects": config.effects,
    }


def _conversation_config_with_tts_options(
    conversation_config: dict[str, Any] | None,
    *,
    provider: str,
    model: str,
    audio_format: str,
    provider_options: dict[str, Any],
) -> dict[str, Any]:
    config = dict(conversation_config or {})
    tts_config = dict(config.get("text_to_speech") or {})
    tts_config["default_tts_model"] = provider
    tts_config["audio_format"] = audio_format
    provider_config = dict(tts_config.get(provider) or {})
    provider_config["model"] = model
    if provider_options.get("voices"):
        provider_config["default_voices"] = provider_options["voices"]
    tts_config[provider] = provider_config
    config["text_to_speech"] = tts_config
    return config


def _append_audio_render_effect(
    *,
    storage_path: Path,
    series_id: str,
    episode_number: int,
    provider: str,
    model: str,
    input_payload: Any,
    output_payload: Any,
) -> None:
    entry = build_effect_log_entry(
        series_id=series_id,
        book_number=1,
        chapter_number=episode_number,
        stage="audio_render",
        input_payload=input_payload,
        output_payload=output_payload,
        provider=provider,
        model=model,
        status=_audio_render_effect_status(output_payload),
        metadata=render_feedback_effect_metadata(output_payload),
    )
    append_effect_log_entry(effect_log_path(storage_path, series_id), entry)


def _audio_render_effect_status(output_payload: Any) -> str:
    if not isinstance(output_payload, Mapping):
        return "committed"
    status = str(output_payload.get("status") or "").lower()
    if status in {"failed", "failed_render", "error"}:
        return "failed"
    if output_payload.get("audio_render_skipped") or status in {"skipped", "directive_invalid"}:
        return "skipped"
    return "committed"
