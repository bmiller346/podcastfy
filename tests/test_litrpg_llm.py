import json

import pytest

from podcastfy.litrpg.llm import GeminiGenerator, IntentRoutingGemini
from podcastfy.litrpg.llm import IntentRoutingOpenAI, OllamaGenerator, OpenAIResponsesGenerator
from podcastfy.litrpg.llm import StageRouterLLM, StageRouting
from podcastfy.litrpg.llm import classify_openai_intent


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"output_text": "generated script"})()


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


class FlakyResponses:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("temporary outage")
        return type("Response", (), {"output_text": "recovered"})()


class FlakyClient:
    def __init__(self):
        self.responses = FlakyResponses()


def test_openai_responses_generator_uses_gpt54_and_stage_metadata():
    client = FakeClient()
    generator = OpenAIResponsesGenerator(
        client=client,
        model="gpt-5.4",
        reasoning_effort="low",
        verbosity="low",
    )

    text = generator.generate(prompt="Write chapter part", stage="script")

    assert text == "generated script"
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.4"
    assert call["reasoning"] == {"effort": "low"}
    assert call["text"] == {"verbosity": "low"}
    assert call["metadata"] == {"litrpg_stage": "script"}


def test_openai_responses_generator_retries_transient_failures(monkeypatch):
    sleeps = []
    monkeypatch.setattr("podcastfy.litrpg.llm.time.sleep", sleeps.append)
    client = FlakyClient()
    generator = OpenAIResponsesGenerator(
        client=client,
        max_retries=3,
        retry_backoff_seconds=0.5,
    )

    text = generator.generate(prompt="Write", stage="part:cold-open")

    assert text == "recovered"
    assert client.responses.calls == 3
    assert sleeps == [0.5, 1.0]


class RecordingGenerator:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        return f"{self.model}:{stage}"


def test_openai_intent_classifier_routes_structural_work_to_stronger_model():
    assert classify_openai_intent(stage="premise_intake", prompt="short") == "strong"
    assert classify_openai_intent(stage="premise_intake_repair", prompt="short") == "strong"
    assert classify_openai_intent(stage="series_package", prompt="short") == "strong"
    assert classify_openai_intent(stage="outline", prompt="short") == "strong"
    assert classify_openai_intent(stage="story_seed_revision", prompt="short") == "strong"
    assert classify_openai_intent(stage="mechanics:cold-open", prompt="short") == "strong"
    assert classify_openai_intent(stage="review:cold-open", prompt="short") == "cheap"
    assert classify_openai_intent(stage="chat", prompt="short") == "cheap"
    assert classify_openai_intent(stage="revision", prompt="short") == "cheap"
    assert classify_openai_intent(stage="smoke", prompt="short") == "nano"
    assert classify_openai_intent(stage="unknown", prompt="Build a continuity ledger") == "strong"


def test_intent_routing_openai_selects_models_by_stage():
    router = IntentRoutingOpenAI(
        api_key="sk-test",
        strong_model="gpt-5.4",
        cheap_model="gpt-5.4-mini",
        nano_model="gpt-5.4-nano",
        generator_factory=RecordingGenerator,
    )

    assert router.generate(prompt="audit", stage="mechanics:cold-open") == "gpt-5.4:mechanics:cold-open"
    assert router.generate(prompt="review", stage="review:cold-open") == "gpt-5.4-mini:review:cold-open"
    assert router.generate(prompt="ping", stage="smoke") == "gpt-5.4-nano:smoke"

    assert router.calls == [
        {"stage": "mechanics:cold-open", "intent": "strong", "model": "gpt-5.4"},
        {"stage": "review:cold-open", "intent": "cheap", "model": "gpt-5.4-mini"},
        {"stage": "smoke", "intent": "nano", "model": "gpt-5.4-nano"},
    ]
    assert router.generators[("gpt-5.4", "medium")].reasoning_effort == "medium"
    assert router.generators[("gpt-5.4-mini", "low")].reasoning_effort == "low"


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_ollama_generator_posts_generate_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"response": "local prose"})

    monkeypatch.setattr("podcastfy.litrpg.llm.urllib.request.urlopen", fake_urlopen)
    generator = OllamaGenerator(
        model="dcc-writer",
        host="http://localhost:11434/",
        system="Write as dark satire.",
        options={"temperature": 0.85, "num_ctx": 32768},
        timeout_seconds=42,
        max_retries=1,
    )

    text = generator.generate(prompt="Draft", stage="part:cold-open")

    assert text == "local prose"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["timeout"] == 42
    assert captured["payload"] == {
        "model": "dcc-writer",
        "prompt": "Draft",
        "stream": False,
        "system": "Write as dark satire.",
        "options": {"temperature": 0.85, "num_ctx": 32768},
    }


def test_gemini_generator_posts_generate_content_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "gemini prose"}],
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("podcastfy.litrpg.llm.urllib.request.urlopen", fake_urlopen)
    generator = GeminiGenerator(
        api_key="gemini-key",
        model="gemini-2.5-flash",
        system="Return JSON.",
        temperature=0.2,
        top_p=0.9,
        max_output_tokens=1024,
        timeout_seconds=33,
        max_retries=1,
    )

    text = generator.generate(prompt="Extract seed", stage="premise_intake")

    assert text == "gemini prose"
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )
    assert captured["timeout"] == 33
    assert captured["headers"]["X-goog-api-key"] == "gemini-key"
    assert captured["payload"]["contents"][0]["parts"] == [{"text": "Extract seed"}]
    assert captured["payload"]["systemInstruction"] == {"parts": [{"text": "Return JSON."}]}
    assert captured["payload"]["generationConfig"] == {
        "temperature": 0.2,
        "topP": 0.9,
        "maxOutputTokens": 1024,
    }


def test_intent_routing_gemini_selects_flash_for_strong_and_lite_for_cheap():
    router = IntentRoutingGemini(
        api_key="gemini-key",
        strong_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        nano_model="gemini-2.5-flash-lite",
        generator_factory=RecordingGenerator,
    )

    assert router.generate(prompt="extract", stage="premise_intake") == "gemini-2.5-flash:premise_intake"
    assert router.generate(prompt="review", stage="review:cold-open") == "gemini-2.5-flash-lite:review:cold-open"

    assert router.calls == [
        {"stage": "premise_intake", "intent": "strong", "model": "gemini-2.5-flash"},
        {"stage": "review:cold-open", "intent": "cheap", "model": "gemini-2.5-flash-lite"},
    ]


class RecordingLLM:
    def __init__(self, label, *, fail=False):
        self.label = label
        self.fail = fail
        self.calls = []

    def generate(self, *, prompt, stage):
        self.calls.append({"prompt": prompt, "stage": stage})
        if self.fail:
            raise RuntimeError(f"{self.label} failed")
        return f"{self.label}:{stage}"


def test_stage_router_sends_prose_to_local_and_reviews_to_default():
    local = RecordingLLM("local")
    default = RecordingLLM("default")
    router = StageRouterLLM(local=local, default=default)

    assert router.generate(prompt="draft", stage="part:cold-open") == "local:part:cold-open"
    assert router.generate(prompt="revise", stage="revise:cold-open") == "local:revise:cold-open"
    assert router.generate(prompt="audit", stage="mechanics:cold-open") == "default:mechanics:cold-open"

    assert [call["stage"] for call in local.calls] == ["part:cold-open", "revise:cold-open"]
    assert [call["stage"] for call in default.calls] == ["mechanics:cold-open"]


def test_stage_routing_documents_hybrid_stage_backends():
    routing = StageRouting()

    expected_local = ["script", "part:cold-open", "revise:boss-setpiece"]
    expected_default = [
        "outline",
        "premise_intake",
        "premise_intake_repair",
        "series_package",
        "review:cold-open",
        "director:cold-open",
        "mechanics:cold-open",
        "chapter_review",
        "visual_state_update",
        "hook",
        "rhythm",
        "reader_proxy",
        "story_seed_revision",
        "chat",
    ]

    assert {stage: routing.backend_for(stage) for stage in expected_local} == {
        "script": "local",
        "part:cold-open": "local",
        "revise:boss-setpiece": "local",
    }
    assert {stage: routing.backend_for(stage) for stage in expected_default} == {
        stage: "default" for stage in expected_default
    }
    assert routing.explain("series_package") == "series_package: commercial strong backend"
    assert routing.explain("review:cold-open") == "review:cold-open: commercial cheap backend"
    assert routing.explain("part:cold-open") == "part:cold-open: local prose backend"


def test_stage_router_supports_custom_stage_rules_and_opt_in_fallback():
    local = RecordingLLM("local", fail=True)
    default = RecordingLLM("default")
    router = StageRouterLLM(
        local=local,
        default=default,
        routing=StageRouting(local_exact=("announcer_lines",), local_prefixes=("voice:",)),
        allow_local_fallback=True,
    )

    assert router.generate(prompt="line", stage="announcer_lines") == "default:announcer_lines"
    assert router.calls == [{"stage": "announcer_lines", "backend": "default_after_local_error"}]


def test_stage_router_raises_without_default_for_non_local_stage():
    router = StageRouterLLM(local=RecordingLLM("local"))

    with pytest.raises(RuntimeError, match="No default generation backend"):
        router.generate(prompt="audit", stage="chapter_review")
