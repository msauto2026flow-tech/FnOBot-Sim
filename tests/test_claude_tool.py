import os
import pytest

from fnobot import claude_tool
from fnobot.llm_wrapper import LLMClient


class DummyClient:
    def claude(self, prompt, model="claude-sonnet-4.6", **kwargs):
        return {"prompt": prompt, "model": model, "kwargs": kwargs}


def test_call_claude_monkeypatch(monkeypatch):
    # patch LLMClient so we don't make a network request
    monkeypatch.setattr(claude_tool, "LLMClient", lambda: DummyClient())
    resp = claude_tool.call_claude("test prompt", temperature=0.7)
    assert resp["prompt"] == "test prompt"
    assert resp["model"] == "claude-sonnet-4.6"
    assert resp["kwargs"]["temperature"] == 0.7


def test_cli_no_key(monkeypatch, capsys):
    # ensure environment variable missing causes runtime error exit
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        claude_tool.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error calling Claude" in captured.err
