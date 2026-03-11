"""Simple command-line gateway for the Claude endpoint.

This module exists so that the VS Code Copilot chat can invoke
``python -m fnobot.claude_tool`` as a tool.  It delegates to the
existing ``LLMClient`` class from ``fnobot.llm_wrapper``.

Usage from Python::

    from fnobot.claude_tool import call_claude
    resp = call_claude("Hello Claude", model="claude-sonnet-4.6")

Usage from the command line::

    # basic prompt only
    python -m fnobot.claude_tool "What is the weather in Mumbai?"

    # specify model or temperature
    python -m fnobot.claude_tool --model claude-sonnet-4.6 --temperature 0.2 "Explain VWAP"

When used as a Copilot tool the chat agent can run something like::

    @tool claude
    {
        "prompt": "Write a haiku about options",
        "temperature": 0.5
    }

and the tool will return the parsed JSON response from the API.

Environment variables:

* ANTHROPIC_API_KEY must be set (see fnobot/llm_wrapper.py for details).
"""

import argparse
import json
import sys
from typing import Any, Dict

from fnobot.llm_wrapper import LLMClient


def call_claude(prompt: str, model: str = "claude-sonnet-4.6", **kwargs: Any) -> Dict[str, Any]:
    """Invoke Claude and return the raw JSON response.

    Parameters mirror those of ``LLMClient.claude``.  ``prompt`` is
    required; all other arguments are passed through to the API.
    """
    client = LLMClient()
    return client.claude(prompt, model=model, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI gateway to the Claude endpoint")
    parser.add_argument("prompt", help="Prompt text to send to Claude")
    parser.add_argument("--model", default="claude-sonnet-4.6",
                        help="Claude model to use")
    # allow arbitrary additional args via key=value pairs
    parser.add_argument("--param", action="append", default=[],
                        help="Additional JSON key=value parameters (can be repeated)")
    args = parser.parse_args()

    extra: Dict[str, Any] = {}
    for kv in args.param:
        if "=" not in kv:
            parser.error("--param values must be key=value")
        k, v = kv.split("=", 1)
        # try to parse JSON value
        try:
            extra[k] = json.loads(v)
        except Exception:
            extra[k] = v

    try:
        resp = call_claude(args.prompt, model=args.model, **extra)
        # pretty print
        json.dump(resp, sys.stdout, indent=2)
        sys.stdout.write("\n")
    except Exception as e:
        sys.stderr.write(f"Error calling Claude: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
