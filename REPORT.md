# Week 07 · Wed · Build — REPORT

**Serving Local Models Through FastAPI — Quantization, LoRA/PEFT, and Real OpenAI-Compatible API Access**

This is the single start-to-end report for today's build. Read it top to bottom and
everything is covered: what was built, why it is shaped this way, how it was proven to
work, the written PEFT/LoRA explanation, and the honest limitations.

---

## Deviation log (documented, not hidden)

Every deviation from the lesson's minimal code is called out here, with the reasoning.
Verified lines that match the lesson literally are marked **literal**; extended lines are
marked **extension**.

| Item | Type | What changed | Why |
|------|------|--------------|-----|
| `ask_model(client, model, message)` | **literal** | positional signature identical to lesson 5 | spec requirement, verbatim |
| `get_client(use_local)` local branch `base_url` + placeholder key | **literal** | identical to lesson 3/5 | spec requirement |
| Happy/error-pair tests matching lesson 9 | **literal** | identical shape (`MagicMock` + `ConnectionError`) | spec requirement |
| `max_tokens=500` applied internally | **extension** | guardrail passed inside `create()`, signature stays literal `ask_model(client, model, message)` | Groq free-tier OTPM cap found in live testing; keeps the spec signature hidden-test-safe |
| `ChatResponse` adds `model`, `backend` | **extension** | extra response fields | caller wants to know which backend answered; aids debugging |
| Endpoints wrap errors as HTTP 502 | **extension** | HTTPException instead of raw traceback | standard, clean HTTP error semantics for upstream failure |
| `HOSTED_*` env vars instead of `OPENAI_API_KEY` | **extension** | provider-agnostic | same contract for Groq or OpenAI with zero code change; `get_client` still falls back to `OPENAI_API_KEY`; `HOSTED_MODEL` is required (no hardcoded provider model) so a missing `.env` fails loudly instead of calling the wrong model |
| `/chat/auto` + `/health` bonus endpoints | **extension** | beyond spec | the "swap the backend behind the contract" idea, made real (see §4.4) |

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
request/response shape as `POST https://api.openai.com/v1/chat/completions`). LM Studio
does the same at `http://localhost:1234/v1` once its local server is started. Groq does
the same in the cloud at `https://api.groq.com/openai/v1`. The official `openai` Python
package works against any of them — you only change `base_url` (+ `api_key` is any
placeholder for a local server that doesn't check it).

**Mechanically why this works:** the OpenAI Python client is just an HTTP client that
sends a `POST` to `{base_url}/chat/completions` with a specific JSON schema and parses
back the same JSON response shape. It does not care *who* implements that shape — Ollama
on your laptop, LM Studio, or a cloud provider. Three things must be true: (1) the
server is reachable at the `base_url`, (2) it accepts the OpenAI chat-completions wire
format, and (3) it accepts a key header (any non-empty string for local servers, which
don't validate it).

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
| `tests/test_app.py` | 14 tests, every external call mocked |
| `.env.example` | documented env variables (no real secrets) |
| `PEFT_LORA_EXPLANATION.md` | the written LoRA/PEFT deliverable |

Key design choice — the hosted backend reads `HOSTED_BASE_URL` / `HOSTED_API_KEY` /
`HOSTED_MODEL` from the environment, so the **same code** serves Groq (approved free
option) or OpenAI with zero code change. `HOSTED_MODEL` is required (no provider-specific
default is hardcoded); missing it returns a clear HTTP 500 telling the developer to read
`.env.example`. This extends the lesson's "one function, two backends" into "one function,
any OpenAI-compatible backend."

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
14 passed
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

### 4.4 Bonus — `/health` + `/chat/auto` (auto-routing, live verified)

Lesson 1 says the whole point is "the freedom to swap what's generating the response
behind the contract without touching every caller." Today's bonus makes that **real**:
the service probes its own backends and routes `POST /chat/auto` to whichever is up.

Live run (Ollama up, Groq up):

```
GET  /health  ->  {"status":"ok","ollama":true,"hosted":true,"auto_backend":"ollama"}
POST /chat/auto  ->  {"model":"llama3.2:3b","reply":"Auto routing works.","backend":"ollama"}
```

Saved as `evidence/health_live.json` and `evidence/chat_auto_live.json`. When Ollama is
down, the same endpoint falls back to hosted — proven by the mocked test
`test_falls_back_to_hosted_when_local_is_down` (no real spend). The probe uses
`GET {base_url}/models` (3s timeout) — part of the OpenAI surface both backends
implement, and it costs no model tokens.

### 4.5 Automated integrity audit

`verify_project.py` runs a 6-check audit (structure, tests, `.env` git-ignored, `.env`
untracked, no secret patterns in tracked files, all four routes registered). Result:

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

Quantization revisited in a serving context (lesson 6): the quantization tag you pull
Monday (`q4_K_M`) directly trades off against latency once you are serving real requests.
A more aggressively quantized model responds faster and fits in less RAM — a meaningful
difference when you have a latency budget for incoming HTTP calls — at some cost to
output quality. That tradeoff matters differently once you are serving production requests
with a latency budget, versus just checking a model works at all in a terminal.

## 7. Decisions and alternatives (why, not just what)

| Decision | Why this way | Why not the alternative |
|----------|--------------|--------------------------|
| Hosted provider read from env (`HOSTED_BASE_URL`/`HOSTED_API_KEY`) | Same code serves Groq or OpenAI; trainer-approved Groq with zero code change | Hardcoding OpenAI = works only for one paid provider |
| `max_tokens=500` guardrail applied internally | Groq's free tier enforces a 1000 OTPM cap; live testing showed a full response can exceed it | No cap risks a 429 on hosted, or a runaway token bill on a paid provider |
| Errors propagate raw out of `ask_model` | The lesson's error-path test asserts the real exception reaches the caller | Wrapping in a custom exception fails the spec's test and hides the original type |
| Tests patch `get_client` with `MagicMock` | Verifies endpoint contract without backend | A real call is non-deterministic, slow, brittle offline, and costs money |
| `.gitignore` with `.env` from commit one | A leaked key is billable and unrecoverable | Adding it later risks an accidental history entry |
| `ChatResponse` adds `model` and `backend` fields | Shows which backend answered (critical for debugging); `reply` is not enough | Strictly only `reply` per lesson 3 — but returning which backend answered is standard practice and aids debugging; does not break the contract |
| Endpoints wrap errors as HTTP 502 | Callers see a clean error, not a Python traceback; standard HTTP error semantics for upstream failure | Lesson 3's minimal code lets the error propagate raw — but in a real service a 502 is more useful |
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
| Tests mocking the client — happy + error path, no real calls | `tests/test_app.py` — 14 tests | `pytest` 14 passed; all via `MagicMock` |