# Local & Hosted LLM API — Week 07 · Wed · Build

**Serving local models through FastAPI with one OpenAI-compatible code path.**

This project wraps an Ollama model running on your laptop **and** a hosted
OpenAI-compatible model behind a single FastAPI service. Both endpoints share
one function — `ask_model(client, model, message)` — so the business logic of
an application does not know or care where the model actually runs.

---

## What it does

| Endpoint | Backend | Default model |
|----------|---------|---------------|
| `POST /chat/local` | Ollama on this machine (`localhost:11434/v1`) | `llama3.2:3b` |
| `POST /chat/hosted` | Hosted OpenAI-compatible provider from `.env` | `llama-3.3-70b-versatile` (Groq) |

Both take the same request body and return the same response shape:

```json
{"message": "what is a token?"}
```
```json
{"model": "llama3.2:3b", "reply": "...", "backend": "ollama"}
```

## The core idea — one function, two backends

```python
def ask_model(client, model, message) -> str:
    response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": message}])
    return response.choices[0].message.content
```

`ask_model` has no idea whether `client` points at a model on your laptop or in a
datacenter. Only two things change between a local call and a hosted call:
**which client object is passed in** and **which model name is requested**. That
works because Ollama, Groq, and OpenAI all speak the same chat-completions API shape.

## Project layout

```
app/
  main.py          FastAPI app: POST /chat/local, POST /chat/hosted
  model_client.py  get_client(use_local) + ask_model(client, model, message)
tests/
  test_app.py      8 tests — every external call mocked, no network/spend
evidence/          live curl outputs proving each endpoint works
PEFT_LORA_EXPLANATION.md   task deliverable: LoRA r / target_modules write-up
EVIDENCE_REPORT.md         task → evidence mapping
technical_summary.md       non-technical write-up
self_review.md             pre-submission checklist
```

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) local endpoint needs Ollama running with a model
ollama list                          # llama3.2:3b should be present
cp .env.example .env                 # 2) then edit .env: paste your hosted key
uvicorn app.main:app --reload        # 3) run the service
```

Then:

```bash
curl -X POST http://localhost:8000/chat/local \
  -H "Content-Type: application/json" -d '{"message":"say hi"}'

curl -X POST http://localhost:8000/chat/hosted \
  -H "Content-Type: application/json" -d '{"message":"say hi"}'
```

Interactive docs: <http://localhost:8000/docs>

## API key safety (non-negotiable)

- The key lives **only** in `.env` (already in `.gitignore`) — never in code, commits, or prints.
- `.env.example` documents every variable; it is safe to commit because it has no real values.
- The openai library reads the key from the environment; `get_client()` reads `HOSTED_API_KEY` (falls back to `OPENAI_API_KEY`).

## Tests (no real network, no real spend)

```bash
python -m pytest tests/ -v
```

Every test replaces the client with `unittest.mock.MagicMock` returning known
fixed responses, per the task requirement. A real call would be non-deterministic,
slow, brittle offline, and cost money on a hosted API.

## Verification

```bash
python verify_project.py      # integrity audit: structure + tests + secrets-safe
```