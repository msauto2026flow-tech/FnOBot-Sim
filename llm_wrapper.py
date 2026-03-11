"""Simple wrapper for calling Claude Sonnet or Opus endpoints.

This module provides a minimal class that reads API keys from the environment
and sends requests to the appropriate HTTP endpoints.  It uses the
"requests" package, which is already a dependency of the project.

Usage example::

    from fnobot.llm_wrapper import LLMClient

    client = LLMClient()
    result = client.claude("Say hello to the world")
    print(result["completion"])

    # or invoke Opus (OpenAI's Responses API)
    resp = client.opus("Translate this text to French.")
    print(resp)

Environment variables:

* ``ANTHROPIC_API_KEY`` – required for Claude calls
* ``OPENAI_API_KEY`` – required for Opus/OpenAI calls

You can also set ``ANTHROPIC_API_URL`` to override the base URL for what
endpoint to hit (the default is ``https://api.anthropic.com/v1/complete``).
"""

import os
import requests
from typing import Any, Dict, Optional


class LLMClient:
    def __init__(self):
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        # allow override for testing/enterprise
        self.anthropic_url = os.getenv("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/complete")
        self.openai_url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")

    def claude(
        self,
        prompt: str,
        model: str = "claude-sonnet-4.6",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Call an Anthropic Claude model.

        ``kwargs`` are merged into the JSON body, which may include parameters
        such as ``max_tokens`` or ``temperature``.
        """
        if not self.anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment")

        headers = {"x-api-key": self.anthropic_key, "Content-Type": "application/json"}
        payload: Dict[str, Any] = {"model": model, "prompt": prompt, **kwargs}
        resp = requests.post(self.anthropic_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def opus(
        self,
        prompt: str,
        model: str = "gpt-4o",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Call OpenAI's Responses API ("Opus").

        This sends the ``prompt`` as ``input``; additional keyword arguments are
        merged into the request body.
        """
        if not self.openai_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment")

        headers = {"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"}
        payload: Dict[str, Any] = {"model": model, "input": prompt, **kwargs}
        resp = requests.post(self.openai_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    # quick CLI for experimentation
    import argparse

    parser = argparse.ArgumentParser(description="Call Claude or Opus from the command line")
    parser.add_argument("model", choices=["claude", "opus"], help="which endpoint to call")
    parser.add_argument("prompt", help="text prompt to send")
    args = parser.parse_args()

    client = LLMClient()
    if args.model == "claude":
        out = client.claude(args.prompt)
    else:
        out = client.opus(args.prompt)
    print(out)
