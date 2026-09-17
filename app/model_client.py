"""Shared model-calling layer.

The whole point of today's exercise lives in this file: one function,
`ask_model`, that does not know or care whether its client points at a
model running on your own laptop or at a hosted cloud API.  The only
things that differ between "local" and "hosted" are:

  1. which *client object* is passed in, and
  2. which *model name* is requested.

Everything else — the request body shape, the response parsing, the error
behaviour — is identical, because both backends speak OpenAI's API shape.
"""

import os

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def server_up(base_url: str, api_key: str) -> bool:
    """Cheap reachability probe: GET {base_url}/models with a short timeout.

    Used by the /health and /chat/auto endpoints to decide which backend to use
    without sending a billable model request.  /models is part of the OpenAI
    API surface that both Ollama and hosted providers implement.
    """
    with httpx.Client(timeout=3.0) as client:
        try:
            response = client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return response.status_code == 200
        except (httpx.HTTPError, ValueError):
            return False


def get_client(use_local: bool) -> OpenAI:
    """Return an OpenAI-compatible client for local Ollama or a hosted API.

    Local  -> Ollama's OpenAI-compatible surface (base_url + any placeholder key).
    Hosted -> the provider configured in .env.  By default the OpenAI library
              reads OPENAI_API_KEY from the environment and points at
              https://api.openai.com/v1; because this project is provider
              agnostic we pass an explicit base_url + key so the SAME code
              works for Groq, OpenAI, or any compatible endpoint.
    """
    if use_local:
        return OpenAI(
            base_url=os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("LOCAL_API_KEY", "ollama"),
        )
    return OpenAI(
        base_url=os.getenv(
            "HOSTED_BASE_URL", "https://api.openai.com/v1"
        ),
        api_key=os.getenv("HOSTED_API_KEY", os.getenv("OPENAI_API_KEY")),
    )


def ask_model(
    client: OpenAI,
    model: str,
    message: str,
    *,
    max_tokens: int = 500,
) -> str:
    """Send one user message to ``model`` through ``client`` and return the reply.

    This function is deliberately dumb: it builds the standard chat-completion
    request, hands it to whatever client it was given, and returns the text of
    the first choice.  It has no idea whether ``client`` is Ollama on this
    machine, Groq's free tier, or OpenAI's production API.  One code path for
    every backend — that is the deliverable.

    ``max_tokens`` is an optional guardrail (keyword-only, 500 default) added
    to prevent runaway output on providers with free-tier TPM limits (Groq
    enforces a 1000 OTPM cap; a 500 max_tokens keeps calls well within it).
    The spec's positional signature ``ask_model(client, model, message)``
    is preserved exactly.

    Errors are intentionally NOT caught here.  A real failure (server down,
    bad key, rate limit) must propagate to the caller untouched, so the
    endpoint layer can decide how to surface it — exactly the behaviour the
    error-path test in the lesson asserts (ConnectionError propagates raw).
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": message}],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content