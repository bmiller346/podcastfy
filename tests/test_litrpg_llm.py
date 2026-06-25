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
