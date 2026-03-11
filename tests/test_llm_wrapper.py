import os
import pytest

from fnobot.llm_wrapper import LLMClient


def test_missing_keys_raise():
    # ensure environment vars aren't set for this test
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)
    client = LLMClient()
    with pytest.raises(RuntimeError):
        client.claude("foo")
    with pytest.raises(RuntimeError):
        client.opus("bar")


@pytest.mark.skipif(
    "ANTHROPIC_API_KEY" not in os.environ,
    reason="No Anthropic API key provided",
)
def test_claude_call():
    client = LLMClient()
    # simple smoke test; we only check that we get a dict with 'completion'
    resp = client.claude("Hello!")
    assert isinstance(resp, dict)
    assert "completion" in resp


@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ,
    reason="No OpenAI API key provided",
)
def test_opus_call():
    client = LLMClient()
    resp = client.opus("Hello!")
    assert isinstance(resp, dict)
    # Responses API returns 'output' usually
    assert "output" in resp or "choices" in resp
