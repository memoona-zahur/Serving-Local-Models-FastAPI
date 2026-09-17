# Week 07 · Wed · Build — REPORT

**Serving Local Models Through FastAPI — Quantization, LoRA/PEFT, and Real OpenAI-Compatible API Access**

This is the single start-to-end report for today's build. Read it top to bottom and
everything is covered: what was built, why it is shaped this way, how it was proven to
work, the written PEFT/LoRA explanation, and the honest limitations.

---

## 1. Framing (what today is about)

Monday showed that a local model is a real file on disk that can be run command-by-command
with `ollama run`. But a REPL is for a human; a production application needs a **stable,
well-defined HTTP contract** — a request shape, a response shape, and the freedom to swap
*what* generates the response *behind* that contract without touching any caller.

Today's build proves the two halves of that idea with real working code:

1. **Wrap a local model** in a FastAPI service — the real shape a local model takes in a
   production system (not `ollama run` in application code).
2. **Use the exact same code path** to reach a hosted provider — so your application code
   doesn't know or care whether the model runs on your laptop or in someone's datacenter.

The unifying trick: **both backends speak OpenAI's chat-completions API shape**, so one
client code path covers them all.

## 2. The core idea — one contract, two backends

Ollama exposes an OpenAI-compatible surface at `http://localhost:11434/v1` (the same
request/response shape as `POST https://api.openai.com/v1/chat/completions`). Groq does
the same at `https://api.groq.com/openai/v1`. The official `openai` Python package works
against any of them — you only change `base_url` (+ `api_key` is any placeholder for a
local server that doesn't check it).

```
              ┌────────────────────────────────────────────────────────────┐
              │                     FastAPI service                        │
              │                                                            │
 POST /chat/local   ──► get_client(use_local=True)   ──► ask_model ──► Ollama  (localhost:11434/v1)
 POST /chat/hosted  ──► get_client(use_local=False)  ──► ask_model ──► Groq   (api.groq.com/openai/v1)
              │                                                            │
              └────────────────────────────────────────────────────────────┘
```

The single shared function that both paths run:

```python
def ask_model(client: OpenAI, model: str, message: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": message}],
    )
    return response.choices[0].message.content
```

`ask_model` has no idea whether `client` points at a laptop or a datacenter. The **only**
things that differ between the local call and the hosted call are (a) the client object
and (b) the model name. That is the entire point of standardizing on one API contract.

## 3. What was built

| File | Purpose |
|------|---------|
| `app/model_client.py` | `get_client(use_local)` picks local vs hosted; `ask_model` is the shared, backend-blind call |
| `app/main.py` | FastAPI app: `POST /chat/local`, `POST /chat/hosted`, same Pydantic contract |
| `tests/test_app.py` | 8 tests, every external call mocked |
| `.env.example` | documented env variables (no real secrets) |
| `PEFT_LORA_EXPLANATION.md` | the written LoRA/PEFT deliverable |

Key design choice — the hosted backend reads `HOSTED_BASE_URL` / `HOSTED_API_KEY` /
`HOSTED_MODEL` from the environment, so the **same code** serves Groq (approved free
option) or OpenAI with zero code change. This extends the lesson's "one function, two
backends" into "one function, any OpenAI-compatible backend."

## 4. How it was proven to work

### 4.1 `/chat/local` — LIVE verified (real Ollama reply)

```
$ curl -s -X POST http://localhost:8001/chat/local -H "Content-Type: application/json" \
       -d '{"message":"In one short sentence, what is a token in an LLM?"}'
{"model":"llama3.2:3b","reply":"In a Large Language Model (LLM), a token is a fundamental unit of input data, typically representing a word, subword, or character in the input text.","backend":"ollama"}
```

Saved as `evidence/chat_local_live.json`. `/docs` (FastAPI interactive docs) responds 200.

### 4.2 `/chat/hosted` — LIVE verified against Groq's free tier

Live response (Groq + `qwen/qwen3.8-27b`, via the service — same request shape as
`/chat/local`, different backend):

```
{"model":"qwen/qwen3.8-27b","reply":"hosted works via Groq with Qwen 3.8 27B","backend":"hosted"}
```

Saved as `evidence/chat_hosted_live.json`. Two backends, one code path, zero code change
between them.

### 4.3 The test suite — no real backend, no spend

```
8 passed
```

Every test replaces the client with `unittest.mock.MagicMock`, so the suite needs no
Ollama server, no network, and spends nothing. Beyond the required happy/error pair, two
adversarial tests catch failures that *look* correct:

- `test_builds_the_correct_request` — asserts the exact `model=` and `messages=[...]`
  that reached the client, so a silently-wrong model name cannot pass.
- `test_does_not_swallow_or_rewrap_error` — asserts exceptions propagate untouched, so a
  hidden "return a placeholder on failure" bug cannot pass.
- Endpoint-level checks: response shape, Pydantic 422 on a bad body, clean 502 when the
  backend dies.

### 4.4 Automated integrity audit

`verify_project.py` runs a 6-check audit (structure, tests, `.env` git-ignored, `.env`
untracked, no secret patterns in tracked files, both routes registered). Result:

```
6/6 checks passed
```

## 5. API key handled safely (non-negotiable)

- The real Groq key lives **only** in `.env`.
- `.env` was added to `.gitignore` **before the first commit** — no secret ever entered
  git history (`git log`/`git show` verified).
- Code reads it from the environment (`python-dotenv`); it never appears in source, a
  print, or a commit.
- `.env.example` documents the variables with placeholders and is safe to commit.

## 6. PEFT / LoRA — what the config actually controls

*Full write-up: `PEFT_LORA_EXPLANATION.md`.*

In a few lines: **`r`** is the rank of the two low-rank update matrices LoRA trains per
layer — it sets how many parameters the adapter has, so a small `r` is a cheap,
underpowered adapter and a very large `r` approaches a full matrix update and erases the
memory savings. **`target_modules`** chooses *which* layers get an adapter injected
(typically the attention projections `q_proj`/`v_proj`); untouched layers stay fully
frozen. Training is dramatically cheaper than full fine-tuning because the base model's
billions of weights are frozen and only the few million adapter parameters update — the
difference between needing many GPUs and fitting on a laptop.

How the three concepts relate (also from the lessons): **quantization** shrinks an
already-trained model so it runs cheaply; **LoRA** and **PEFT** shrink the cost of
*adapting* a model in the first place.

## 7. Decisions and alternatives (why, not just what)

| Decision | Why this way | Why not the alternative |
|----------|--------------|--------------------------|
| Hosted provider read from env (`HOSTED_BASE_URL`/`HOSTED_API_KEY`) | Same code serves Groq or OpenAI; trainer-approved Groq with zero code change | Hardcoding OpenAI = works only for one paid provider |
| `max_tokens=500` keyword-only guardrail in `ask_model` | Groq's free tier enforces a 1000 OTPM cap; live testing showed a full response can exceed it | No cap risks a 429 on hosted, or a runaway token bill on a paid provider |
| Errors propagate raw out of `ask_model` | The lesson's error-path test asserts the real exception reaches the caller | Wrapping in a custom exception fails the spec's test and hides the original type |
| Tests patch `get_client` with `MagicMock` | Verifies endpoint contract without backend | A real call is non-deterministic, slow, brittle offline, and costs money |
| `.gitignore` with `.env` from commit one | A leaked key is billable and unrecoverable | Adding it later risks an accidental history entry |
| Single `main` branch | Explicitly agreed for this task | n/a (feature branch waived) |

## 8. Honest limitations

- **Local model quality/latency**: `llama3.2:3b` on CPU-only hardware is suitable for
  demos, not production reasoning; latency and output quality depend on the machine.
- **Hosted free-tier limits**: Groq's free tier enforces an OTPM cap (hence the
  `max_tokens=500` guardrail); a high-QPS caller would still hit it — fine for this
  course's usage.
- **No real LoRA training loop**: laptop-infeasible per the task; the explanation is
  grounded in the Hugging Face LoRA reference, not a local training run.
- **Determinism**: model output is inherently non-deterministic (sampling); tests are
  deterministic because they mock the client.

## 9. Requirements → delivery map

| Requirement | Delivered where | Proof |
|-------------|-----------------|-------|
| Build `/chat/local` wrapping an Ollama model | `app/main.py` — `chat_local()` | live curl reply in `evidence/chat_local_live.json` |
| Build `/chat/hosted` (same shape, hosted) | `app/main.py` — `chat_hosted()` | live curl reply in `evidence/chat_hosted_live.json` |
| Real key stored safely (`.env`, `.gitignore` from the start) | `.gitignore`; `.env` (untracked) | `verify_project.py` secret-safety checks |
| Refactor into one shared `ask_model(client, model, message)` | `app/model_client.py`; both endpoints delegate | grep both endpoints; tests assert the call |
| Written PEFT/LoRA explanation (`r`, `target_modules`, why cheap) | `PEFT_LORA_EXPLANATION.md` + §6 above | document exists |
| Tests mocking the client — happy + error path, no real calls | `tests/test_app.py` — 8 tests | `pytest` 8 passed; all via `MagicMock` |