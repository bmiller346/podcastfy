"""LLM adapters for LitRPG generation and review."""

from __future__ import annotations

import time
from typing import Any


class OpenAIResponsesGenerator:
    """OpenAI Responses API adapter for staged LitRPG generation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-5.5",
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        timeout_seconds: float | None = 120.0,
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key) if api_key else OpenAI()
        self.client = client
        self.model = model
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
