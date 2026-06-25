"""LLM adapters for LitRPG generation and review."""

from __future__ import annotations

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
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key) if api_key else OpenAI()
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity

    def generate(self, *, prompt: str, stage: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            reasoning={"effort": self.reasoning_effort},
            text={"verbosity": self.verbosity},
            metadata={"litrpg_stage": stage},
        )
        return _response_text(response)


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
