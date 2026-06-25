from podcastfy.litrpg.llm import OpenAIResponsesGenerator


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


def test_openai_responses_generator_uses_gpt55_and_stage_metadata():
    client = FakeClient()
    generator = OpenAIResponsesGenerator(
        client=client,
        model="gpt-5.5",
        reasoning_effort="low",
        verbosity="low",
    )

    text = generator.generate(prompt="Write chapter part", stage="script")

    assert text == "generated script"
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.5"
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
