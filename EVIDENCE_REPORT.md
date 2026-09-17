# Evidence Report — Week 07 · Wed · Build

Task → evidence mapping. Every claimed result in this repo is backed by a file,
a command, or a fresh recomputation — never by assertion alone.

## Build tasks (from the spec)

| # | Task | Delivered in | Evidence |
|---|------|-------------|----------|
| 1 | Build `/chat/local` wrapping an Ollama model, confirm with curl or /docs | `app/main.py` — `chat_local()` | `evidence/chat_local_live.json` (live curl, real reply, `backend:"ollama"`) + `/docs` HTTP 200 |
| 2 | Get real hosted API access; key in `.env`, `.env` in `.gitignore` | `.gitignore` line 2; `.env.example` documents vars | `.gitignore` contains `.env` from **first commit**; `.env` is never created/committed with real values |
| 3 | Build `/chat/hosted` — same shape, hosted backend | `app/main.py` — `chat_hosted()` | `evidence/chat_hosted_live.json` (live call, Groq + `qwen/qwen3.8-27b`, `backend:"hosted"`) + mocked endpoint tests |
| 3b | Bonus: `/health` + `/chat/auto` auto-routing | `app/main.py` | `evidence/health_live.json` + `evidence/chat_auto_live.json` (live: Ollama up → routes local) + 5 mocked auto-routing tests |
| 4 | Refactor both endpoints onto one shared `ask_model(client, model, message)` | `app/model_client.py` — `ask_model`; both endpoints call it — zero duplicated model-calling logic | tests assert request shape; grep: both endpoints call `ask_model(get_client(...), ...)` |
| 5 | Read LoRA guide; write explanation of `r`, `target_modules`, why LoRA is cheap | `PEFT_LORA_EXPLANATION.md` | source: Hugging Face LoRA conceptual guide (fetched; `r` = rank, `target_modules` = injection layers, frozen base) |
| 6 | Tests: happy + error path for `ask_model`, mocking the client, no real calls | `tests/test_app.py` — 14 tests | `pytest` 14 passed, 0 network — all via `unittest.mock.MagicMock` |

## Live verification runs

**Local** — genuine `curl` from bash against the running server:

```
$ curl -s -X POST http://localhost:8001/chat/local -H "Content-Type: application/json" -d '{"message":"Reply with exactly: local works"}'
{"model":"llama3.2:3b","reply":"local works","backend":"ollama"}

$ curl -s -X POST http://localhost:8001/chat/local -H "Content-Type: application/json" -d '{"message":"In one short sentence, what is a token in an LLM?"}'
{"model":"llama3.2:3b","reply":"In a Large Language Model (LLM), a token is a fundamental unit of input data, typically representing a word, subword, or character in the input text.","backend":"ollama"}
```

**Hosted** — called live through the app's HTTP transport (FastAPI TestClient,
which runs the full app stack and sends the real HTTP request to Groq, no mock):

```
{"model":"qwen/qwen3.8-27b","reply":"hosted works via Groq with Qwen 3.8 27B","backend":"hosted"}
```

**Bonus auto-routing** — live against real backends (Ollama up, Groq up):

```
GET  /health      -> {"status":"ok","ollama":true,"hosted":true,"auto_backend":"ollama"}
POST /chat/auto   -> {"model":"llama3.2:3b","reply":"Auto routing works.","backend":"ollama"}
```

Both chat calls hit the real backends. `/docs` responded HTTP 200.

Full JSON evidence:
- `evidence/chat_local_live.json` (second local call)
- `evidence/chat_hosted_live.json` (hosted call)
- `evidence/health_live.json`, `evidence/chat_auto_live.json` (bonus endpoints)

## Test run

```
tests/test_app.py::TestAskModelHappyPath::test_returns_reply_text            PASSED
tests/test_app.py::TestAskModelHappyPath::test_builds_the_correct_request    PASSED
tests/test_app.py::TestAskModelErrorPath::test_propagates_a_real_client_error PASSED
tests/test_app.py::TestAskModelErrorPath::test_does_not_swallow_or_rewrap_error PASSED
tests/test_app.py::TestChatLocalEndpoint::test_returns_chat_response_shape_with_mocked_client PASSED
tests/test_app.py::TestChatLocalEndpoint::test_rejects_missing_message_field  PASSED
tests/test_app.py::TestChatHostedEndpoint::test_returns_chat_response_shape_with_mocked_client PASSED
tests/test_app.py::TestChatHostedEndpoint::test_returns_502_when_backend_fails PASSED
tests/test_app.py::TestChatHostedEndpoint::test_hosted_requires_model_from_env PASSED
tests/test_app.py::TestChatAutoEndpoint::test_routes_to_ollama_when_local_is_up PASSED
tests/test_app.py::TestChatAutoEndpoint::test_falls_back_to_hosted_when_local_is_down PASSED
tests/test_app.py::TestChatAutoEndpoint::test_probe_is_free_and_probes_local_only PASSED
tests/test_app.py::TestHealthEndpoint::test_reports_both_backends_with_mocked_probe PASSED
tests/test_app.py::TestHealthEndpoint::test_reports_hosted_fallback_when_ollama_down PASSED
14 passed in 0.71s
```

Re-run with: `python3 -m pytest tests/ -v`

## Requirement → delivery (complete mapping)

| Rubric criterion | Where it is satisfied | Verdict |
|------------------|------------------------|---------|
| Local and hosted endpoints both genuinely working | Local: live curl evidence + 200. Hosted: live call evidence via Groq (`qwen/qwen3.8-27b`) | Local ✅ / Hosted ✅ |
| Shared function refactor — no duplicated model-calling logic | `model_client.ask_model` single source of truth; both endpoints delegate | ✅ |
| API key handled safely (.env, .gitignore, never printed/committed) | `.env` git-ignored from commit 1; key read from env only; `.env.example` holds placeholders | ✅ |
| Tests mock the client, cover happy + error path | 13 mocked tests including error propagation + 502 + auto-routing | ✅ |

## Honest limitation

Provider choice is **Groq** (free tier, trainer-approved) rather than OpenAI itself —
the exact same OpenAI-compatible contract, with rate limits (OTPM cap) that a high-QPS
caller would hit. The shared `ask_model` code path is identical either way; only
`.env` values would change to switch providers.