"""LLM adapters for LitRPG generation and review."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class OpenAIResponsesGenerator:
    """OpenAI Responses API adapter for staged LitRPG generation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-5.4",
        base_url: str | None = None,
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        timeout_seconds: float | None = 120.0,
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client_kwargs = {}
            if api_key:
                client_kwargs["api_key"] = api_key
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
        self.client = client
        self.model = model
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.timeout_seconds = timeout_seconds

    def generate(self, *, prompt: str, stage: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs = {
                    "model": self.model,
                    "input": prompt,
                    "reasoning": {"effort": self.reasoning_effort},
                    "text": {"verbosity": self.verbosity},
                    "metadata": {"litrpg_stage": stage},
                }
                if self.timeout_seconds is not None:
                    kwargs["timeout"] = self.timeout_seconds
                response = self.client.responses.create(**kwargs)
                return _response_text(response)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(
            f"OpenAI generation failed for stage {stage!r} after {self.max_retries} attempts"
        ) from last_error


class IntentRoutingOpenAI:
    """Route OpenAI calls to cheaper or stronger models by stage/prompt intent."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = "gpt-5.4-mini",
        strong_model: str = "gpt-5.4",
        cheap_model: str = "gpt-5.4-mini",
        nano_model: str = "gpt-5.4-nano",
        reasoning_effort: str = "low",
        strong_reasoning_effort: str = "medium",
        verbosity: str = "medium",
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        timeout_seconds: float | None = 120.0,
        prompt_char_threshold: int = 12000,
        generator_factory: Any = OpenAIResponsesGenerator,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = default_model
        self.default_model = default_model
        self.strong_model = strong_model
        self.cheap_model = cheap_model
        self.nano_model = nano_model
        self.reasoning_effort = reasoning_effort
        self.strong_reasoning_effort = strong_reasoning_effort
        self.verbosity = verbosity
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.timeout_seconds = timeout_seconds
        self.prompt_char_threshold = prompt_char_threshold
        self.generator_factory = generator_factory
        self.generators: dict[tuple[str, str], Any] = {}
        self.calls: list[dict[str, str]] = []

    def generate(self, *, prompt: str, stage: str) -> str:
        intent = classify_openai_intent(
            stage=stage,
            prompt=prompt,
            prompt_char_threshold=self.prompt_char_threshold,
        )
        model = self._model_for_intent(intent)
        reasoning = self.strong_reasoning_effort if intent == "strong" else self.reasoning_effort
        self.calls.append({"stage": stage, "intent": intent, "model": model})
        return str(
            self._generator(model=model, reasoning_effort=reasoning).generate(
                prompt=prompt,
                stage=stage,
            )
        )

    def _model_for_intent(self, intent: str) -> str:
        if intent == "strong":
            return self.strong_model
        if intent == "nano":
            return self.nano_model
        if intent == "cheap":
            return self.cheap_model
        return self.default_model

    def _generator(self, *, model: str, reasoning_effort: str) -> Any:
        key = (model, reasoning_effort)
        if key not in self.generators:
            self.generators[key] = self.generator_factory(
                api_key=self.api_key,
                model=model,
                base_url=self.base_url,
                reasoning_effort=reasoning_effort,
                verbosity=self.verbosity,
                max_retries=self.max_retries,
                retry_backoff_seconds=self.retry_backoff_seconds,
                timeout_seconds=self.timeout_seconds,
            )
        return self.generators[key]


def classify_openai_intent(
    *,
    stage: str,
    prompt: str,
    prompt_char_threshold: int = 12000,
) -> str:
    """Classify the model tier needed for a staged OpenAI call."""

    stage_key = stage.casefold()
    base_stage = stage_key.split(":", 1)[0]
    if base_stage in {
        "premise_intake",
        "series_package",
        "chapter_review",
        "visual_state_update",
        "mechanics",
    }:
        return "strong"
    if base_stage in {
        "review",
        "director",
        "description",
        "tonal",
        "showmanship",
        "hook",
        "rhythm",
        "reader_proxy",
    }:
        return "cheap"
    if base_stage in {"settings_probe", "smoke", "status"}:
        return "nano"

    prompt_key = prompt.casefold()
    strong_terms = (
        "series arc",
        "book plan",
        "continuity",
        "foreshadow",
        "world register",
        "story bible",
        "mechanics gate",
        "structural audit",
    )
    if len(prompt) >= prompt_char_threshold or any(term in prompt_key for term in strong_terms):
        return "strong"
    return "cheap"


class GeminiGenerator:
    """Gemini generateContent API adapter for staged LitRPG generation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        system: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = 120.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini generation requires a valid API key.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.system = system
        self.temperature = temperature
        self.top_p = top_p
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def generate(self, *, prompt: str, stage: str) -> str:
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
        }
        system = self.system or f"You are a staged LitRPG generation assistant. Current stage: {stage}."
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        generation_config: dict[str, Any] = {}
        if self.temperature is not None:
            generation_config["temperature"] = self.temperature
        if self.top_p is not None:
            generation_config["topP"] = self.top_p
        if self.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = self.max_output_tokens
        if generation_config:
            payload["generationConfig"] = generation_config

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._post_generate(payload)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(
            f"Gemini generation failed for stage {stage!r} with model {self.model!r} "
            f"after {self.max_retries} attempts"
        ) from last_error

    def _post_generate(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/models/{self.model}:generateContent",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini is unavailable at {self.base_url!r}: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini response was not valid JSON") from exc
        return _gemini_response_text(data)


class IntentRoutingGemini:
    """Route Gemini calls to cheaper or stronger Gemini models by stage/prompt intent."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        default_model: str = "gemini-2.5-flash-lite",
        strong_model: str = "gemini-2.5-flash",
        cheap_model: str = "gemini-2.5-flash-lite",
        nano_model: str = "gemini-2.5-flash-lite",
        temperature: float | None = None,
        top_p: float | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = 120.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        prompt_char_threshold: int = 12000,
        generator_factory: Any = GeminiGenerator,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = default_model
        self.default_model = default_model
        self.strong_model = strong_model
        self.cheap_model = cheap_model
        self.nano_model = nano_model
        self.temperature = temperature
        self.top_p = top_p
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.prompt_char_threshold = prompt_char_threshold
        self.generator_factory = generator_factory
        self.generators: dict[str, Any] = {}
        self.calls: list[dict[str, str]] = []

    def generate(self, *, prompt: str, stage: str) -> str:
        intent = classify_openai_intent(
            stage=stage,
            prompt=prompt,
            prompt_char_threshold=self.prompt_char_threshold,
        )
        model = self._model_for_intent(intent)
        self.calls.append({"stage": stage, "intent": intent, "model": model})
        return str(self._generator(model=model).generate(prompt=prompt, stage=stage))

    def _model_for_intent(self, intent: str) -> str:
        if intent == "strong":
            return self.strong_model
        if intent == "nano":
            return self.nano_model
        if intent == "cheap":
            return self.cheap_model
        return self.default_model

    def _generator(self, *, model: str) -> Any:
        if model not in self.generators:
            self.generators[model] = self.generator_factory(
                api_key=self.api_key,
                model=model,
                base_url=self.base_url,
                temperature=self.temperature,
                top_p=self.top_p,
                max_output_tokens=self.max_output_tokens,
                timeout_seconds=self.timeout_seconds,
                max_retries=self.max_retries,
                retry_backoff_seconds=self.retry_backoff_seconds,
            )
        return self.generators[model]


class OllamaGenerator:
    """Ollama HTTP API adapter for local staged LitRPG generation."""

    def __init__(
        self,
        *,
        model: str = "dolphin3",
        host: str = "http://localhost:11434",
        system: str | None = None,
        options: dict[str, Any] | None = None,
        timeout_seconds: float | None = 180.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        keep_alive: str | None = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.system = system
        self.options = dict(options or {})
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.keep_alive = keep_alive

    def generate(self, *, prompt: str, stage: str, system: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        resolved_system = system if system is not None else self.system
        if resolved_system:
            payload["system"] = resolved_system
        if self.options:
            payload["options"] = self.options
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._post_generate(payload)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(
            f"Ollama generation failed for stage {stage!r} with model {self.model!r} "
            f"at {self.host!r} after {self.max_retries} attempts"
        ) from last_error

    def _post_generate(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama is unavailable at {self.host!r}: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama response was not valid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Ollama response was not a JSON object")
        if data.get("error"):
            raise RuntimeError(f"Ollama returned an error: {data['error']}")
        text = data.get("response")
        if not isinstance(text, str):
            raise RuntimeError("Ollama response did not include generated text")
        return text


@dataclass(frozen=True, slots=True)
class StageRouting:
    """Stage matching rules for hybrid local/commercial generation."""

    local_exact: tuple[str, ...] = ("script",)
    local_prefixes: tuple[str, ...] = ("part:", "revise:")

    def is_local(self, stage: str) -> bool:
        return stage in self.local_exact or any(
            stage.startswith(prefix) for prefix in self.local_prefixes
        )


class StageRouterLLM:
    """Route generation stages between local prose and commercial review models."""

    def __init__(
        self,
        *,
        local: Any,
        default: Any | None = None,
        routing: StageRouting | None = None,
        allow_local_fallback: bool = False,
    ) -> None:
        if local is None:
            raise ValueError("StageRouterLLM requires a local generator")
        self.local = local
        self.default = default
        self.routing = routing or StageRouting()
        self.allow_local_fallback = allow_local_fallback
        self.calls: list[dict[str, str]] = []

    def generate(self, *, prompt: str, stage: str) -> str:
        if self.routing.is_local(stage):
            self.calls.append({"stage": stage, "backend": "local"})
            try:
                return str(self.local.generate(prompt=prompt, stage=stage))
            except Exception:
                if not (self.allow_local_fallback and self.default is not None):
                    raise
                self.calls[-1]["backend"] = "default_after_local_error"
                return str(self.default.generate(prompt=prompt, stage=stage))

        if self.default is None:
            raise RuntimeError(
                f"No default generation backend is configured for non-local stage {stage!r}"
            )
        self.calls.append({"stage": stage, "backend": "default"})
        return str(self.default.generate(prompt=prompt, stage=stage))


def _response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)

    output = getattr(response, "output", None) or []
    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for content_item in content:
            text = getattr(content_item, "text", None)
            if text:
                parts.append(str(text))
    if parts:
        return "\n".join(parts)
    raise RuntimeError("OpenAI response did not include output text")


def _gemini_response_text(data: Any) -> str:
    if not isinstance(data, dict):
        raise RuntimeError("Gemini response was not a JSON object")
    if data.get("error"):
        raise RuntimeError(f"Gemini returned an error: {data['error']}")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        feedback = data.get("promptFeedback")
        if feedback:
            raise RuntimeError(f"Gemini response did not include candidates: {feedback}")
        raise RuntimeError("Gemini response did not include candidates")
    text_parts: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
    if text_parts:
        return "\n".join(text_parts)
    finish_reason = candidates[0].get("finishReason") if isinstance(candidates[0], dict) else None
    if finish_reason:
        raise RuntimeError(f"Gemini response did not include text; finishReason={finish_reason}")
    raise RuntimeError("Gemini response did not include generated text")
