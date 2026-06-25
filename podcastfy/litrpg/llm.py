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
        model: str = "gpt-5.5",
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
