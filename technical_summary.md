# Technical Summary — Local & Hosted LLM API

*A non-technical walkthrough of what this project is, why it is shaped this way,
and what every part does. Written so that a reader who has not seen the code can
follow the whole story.*

---

## What is this?

A small web service that lets other programs ask an AI model a question over HTTP.
The clever part: the same service can talk to **two completely different places**
that run the model —

1. **Your own laptop** (an Ollama instance running a `llama3.2:3b` model), and
2. **The cloud** (a hosted "OpenAI-compatible" provider, configured via `.env`).

Both are reached through the **same code path**, the same request format, the same
response format. That is not an accident — it is the entire point of the build.

## Why is "one code path" valuable?

In a real application you don't want to write two different APIs for "model on
laptop" vs "model in cloud." You want to write the calling code **once** and be able
to switch where the model runs by changing a configuration value, not by rewriting
your application. This is what the shared `ask_model` function achieves.

## How does it work mechanically?

Every backend in this project speaks OpenAI's *chat completions* protocol — the same
wire format OpenAI's own servers use (`POST /v1/chat/completions`). Ollama happens to
expose that exact protocol at `http://localhost:11434/v1`. LM Studio does the same at
`http://localhost:1234/v1` once its local server is started from the app. Groq exposes it
in the cloud at `https://api.groq.com/openai/v1`. So when you point the
official `openai` Python library at any of those addresses (instead of OpenAI's own
cloud), the library politely talks wherever `base_url` points. Same client. Same code.
Different address.

Three things must be true about the server for the client to work against it:
(1) it is reachable at the configured `base_url`; (2) it accepts the same JSON request
and returns the same JSON response schema; (3) it accepts the key header without
rejecting it (Ollama/LM Studio don't validate it at all).

```
POST /chat/local   ->  client(base_url=localhost:11434/v1)  ->  ask_model -> Ollama
POST /chat/hosted  ->  client(base_url=api.groq.com/...v1)  ->  ask_model -> hosted API
```

The one shared function at the heart of both paths:

```python
def ask_model(client, model, message):
    response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": message}])
    return response.choices[0].message.content
```

## What is in each file?

- **`app/model_client.py`** — the shared pattern. `get_client(use_local)` decides
  whether you get a local or a hosted client; `ask_model` is the single, backend-blind
  function that does the actual model call; `server_up(base_url, key)` is a free
  reachability probe (`GET /models`, 3s timeout) that powers auto-routing.
- **`app/main.py`** — the FastAPI service. Two endpoints (`/chat/local`,
  `/chat/hosted`) that share the same request/response contract and both delegate to
  `ask_model`. If the backend fails, the endpoint turns the error into a clean HTTP 502.
- **`tests/test_app.py`** — 13 tests. Every test replaces the real client with a
  **fake** that returns a known, fixed answer, so the tests never touch a network, a
  running server, or spend money. They verify: (a) the happy path returns the reply,
  (b) the right request is actually built, (c) real errors propagate instead of being
  swallowed, (d) the endpoints return valid shapes, (e) validation errors and backend
  failures produce correct HTTP status codes, and (f) auto-routing probes are mocked
  (free) and route local-vs-hosted correctly.
- **`.env` / `.env.example`** — secrets handled safely. `.env` holds the real key
  and is git-ignored from the first commit; `.env.example` documents the variables
  with placeholder values.

## How do we know it works?

1. `/chat/local` was called live with `curl` against the real Ollama server —
   evidence saved in `evidence/chat_local_live.json`.
2. `/chat/hosted` was called live against Groq's free tier (`qwen/qwen3.8-27b`) —
   evidence saved in `evidence/chat_hosted_live.json`.
3. The bonus auto-routing endpoint was called live — Ollama up → routed local;
   evidence in `evidence/health_live.json` and `evidence/chat_auto_live.json`.
4. Interactive docs (`/docs`) respond with HTTP 200.
5. The test suite (which needs no backend at all) passes 13/13.

## What we could NOT do (and why)

- **No real training loop for LoRA/PEFT was run.** Most laptops cannot train even a
  small model; the task explicitly stops at "explain the config." The written
  explanation (`PEFT_LORA_EXPLANATION.md`) is grounded in the Hugging Face LoRA
  reference rather than a local training run.
  → *Impact: understanding, not practice, for the fine-tuning side of today's topic.*

- **The hosted provider is Groq (free tier), not OpenAI itself.** Trainer-approved:
  the lesson is about the OpenAI-compatible contract, not the vendor. The only
  consequence is Groq's free-tier OTPM rate cap, which was handled with an optional
  `max_tokens=500` guardrail in `ask_model`.
  → *Impact: same code path, real live evidence; a different `.env` swaps providers.*

## Key decisions and alternatives

| Decision | Why this way | Why not the alternative |
|----------|--------------|--------------------------|
| Hosted provider read from `HOSTED_BASE_URL` / `HOSTED_API_KEY` env vars | The task's lesson is provider-agnostic; supports Groq (free, trainer-approved) or OpenAI with **zero code change** | Hardcoding OpenAI means the code only ever works for one paid provider |
| Errors propagate raw out of `ask_model` | The lesson's error-path test asserts the real exception (e.g. `ConnectionError`) reaches the caller | Wrapping errors in a custom exception hides the original type and would fail the spec's test |
| Tests patch `app.main.get_client` with `MagicMock` | Tests the endpoint contract without a backend | A real (unpatched) call would hit the network and be non-deterministic |
| `.env` added to `.gitignore` before first commit | A leaked key is billable and unrecoverable — ignoring it first makes a leak impossible | Adding `.gitignore` later risks an accidental commit history entry |

## Limitations summary

- Model latency/quality depends on the local machine (CPU-only here) or the provider's free tier rate limits (Groq OTPM cap).
- The quantization level (`q4_K_M`) chosen Monday directly trades off in a serving context: more aggressive quantization means faster responses and less RAM, at some cost to output quality — a meaningful tradeoff when you have a latency budget for incoming HTTP calls, not just when checking a model works at all.
- Local model `llama3.2:3b` is a small model; it is suitable for demos, not production reasoning.
- Provider is Groq rather than OpenAI itself (trainer-approved) — contract identical, billing-free.